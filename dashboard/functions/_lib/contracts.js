// Contract resolution: validation for the question, and storage for the answer.
//
// The rule this file exists to keep: a conId is a broker fact, and the browser
// never states one. It may ask "what is MSFT" or "what XSP puts expire in
// January"; the hub answers from IBKR and writes the answer back. Anything here
// that looks like it produces a conId is only ever reading one the hub already
// published.

const SYMBOL_PATTERN = /^[A-Z0-9][A-Z0-9.\-/ ]{0,23}$/;
const EXPIRY_PATTERN = /^\d{8}$/;                 // YYYYMMDD, as IBKR states it
const DECIMAL = /^\d+(?:\.\d{1,6})?$/;

// STK covers ETFs at IBKR; "ETF" is not an IB secType and a ticket carrying it
// would fingerprint an instrument that does not exist. OPT is the reason this
// whole path exists -- nobody types an option conId.
export const LOOKUP_SEC_TYPES = new Set(["STK", "OPT"]);
export const LOOKUP_KINDS = new Set(["contract", "option_chain", "option_contract"]);
export const LOOKUP_STATES = new Set(["requested", "resolving", "resolved", "failed"]);

export function validateContractLookup(payload, authorizedOwner) {
  if (!authorizedOwner) throw new TypeError("This login is not mapped to a portfolio owner.");

  const kind = String(payload?.kind || "contract").trim();
  if (!LOOKUP_KINDS.has(kind)) throw new TypeError("Unsupported lookup kind.");

  const symbol = String(payload?.symbol || "").trim().toUpperCase();
  if (!SYMBOL_PATTERN.test(symbol)) throw new TypeError("A symbol is required.");

  const secType = String(payload?.sec_type || (kind === "contract" ? "STK" : "OPT")).trim().toUpperCase();
  if (!LOOKUP_SEC_TYPES.has(secType)) {
    throw new TypeError("Security type must be STK or OPT (IBKR files ETFs as STK).");
  }
  if (kind !== "contract" && secType !== "OPT") {
    throw new TypeError("Chain and option lookups require sec_type OPT.");
  }

  const expiry = payload?.expiry == null ? null : String(payload.expiry).trim();
  if (expiry !== null && !EXPIRY_PATTERN.test(expiry)) {
    throw new TypeError("Expiry must be YYYYMMDD.");
  }
  const strike = payload?.strike == null || String(payload.strike).trim() === ""
    ? null : String(payload.strike).trim();
  if (strike !== null && !DECIMAL.test(strike)) throw new TypeError("Strike must be a positive number.");

  const right = payload?.right == null || String(payload.right).trim() === ""
    ? null : String(payload.right).trim().toUpperCase();
  if (right !== null && !["P", "C"].includes(right)) throw new TypeError("Right must be P or C.");

  // A single option contract is only identified once all three are pinned. A
  // partially specified one would resolve to many conIds, and picking one for
  // the user is exactly the guess this design refuses to make.
  if (kind === "option_contract" && (!expiry || !strike || !right)) {
    throw new TypeError("An option contract needs expiry, strike and right.");
  }

  return {
    kind, symbol, sec_type: secType, expiry, strike, right,
    currency: payload?.currency ? String(payload.currency).trim().slice(0, 3).toUpperCase() : "USD",
    exchange: payload?.exchange ? String(payload.exchange).trim().slice(0, 16).toUpperCase() : "SMART",
    owner: authorizedOwner,
  };
}

/**
 * Every match the hub publishes, normalised. Anything the hub did not send is
 * absent rather than guessed -- a blank multiplier is a fact about the answer,
 * and inventing 100 for it would be the kind of silent default that makes an
 * option ticket lie about its own size.
 */
export function normalizeMatches(raw, limit = 400) {
  if (!Array.isArray(raw)) return [];
  const matches = [];
  // The default bound is about the picker -- a list of four hundred contracts is
  // not a list anyone reads. Seeding the cache from a position snapshot passes a
  // higher bound, because silently forgetting holdings would make the symbol box
  // quietly incomplete in exactly the way that is hardest to notice.
  for (const row of raw.slice(0, limit)) {
    const conid = Number(row?.conid ?? row?.conId);
    if (!Number.isInteger(conid) || conid <= 0) continue;
    matches.push({
      conid,
      symbol: text(row?.symbol, 24),
      local_symbol: text(row?.local_symbol ?? row?.localSymbol, 64),
      sec_type: text(row?.sec_type ?? row?.secType, 8),
      currency: text(row?.currency, 3),
      exchange: text(row?.exchange, 16),
      primary_exchange: text(row?.primary_exchange ?? row?.primaryExchange, 16),
      trading_class: text(row?.trading_class ?? row?.tradingClass, 16),
      expiry: text(row?.expiry ?? row?.lastTradeDateOrContractMonth, 8),
      strike_decimal: number(row?.strike ?? row?.strike_decimal),
      right_code: text(row?.right ?? row?.right_code, 1),
      multiplier_decimal: number(row?.multiplier ?? row?.multiplier_decimal),
      min_tick: number(row?.min_tick ?? row?.minTick),
      description: text(row?.description ?? row?.longName, 120),
    });
  }
  return matches;
}

function text(value, maximum) {
  if (value == null) return null;
  const cleaned = String(value).replace(/\s+/g, " ").trim();
  return cleaned ? cleaned.slice(0, maximum) : null;
}

function number(value) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? String(parsed) : null;
}

/**
 * Remember every contract the hub has resolved or the account has held.
 *
 * This is what lets the symbol box answer on a weekend. `ibc.service` is a
 * session service that is legitimately down outside market days, so a lookup
 * that needs the Gateway returns nothing then; the cache still does. It is
 * never authoritative -- the hub re-qualifies at preview time regardless -- so
 * a stale row costs a redundant qualify, not a wrong order.
 */
export async function rememberContracts(db, matches, source) {
  const rows = matches.filter((row) => row.conid && row.symbol && row.sec_type);
  if (!rows.length) return 0;
  const now = new Date().toISOString();
  // Chunked, because this runs over a whole position snapshot. One batch of a
  // few thousand statements is how an ingest that has always worked starts
  // failing the day the book grows, and it would fail *after* the snapshot rows
  // were already written.
  const CHUNK = 50;
  for (let index = 0; index < rows.length; index += CHUNK) {
    await writeChunk(db, rows.slice(index, index + CHUNK), source, now);
  }
  return rows.length;
}

async function writeChunk(db, rows, source, now) {
  await db.batch(rows.map((row) => db.prepare(`INSERT INTO portfolio_contracts
    (conid,symbol,local_symbol,sec_type,currency,exchange,primary_exchange,trading_class,
     expiry,strike_decimal,right_code,multiplier_decimal,description,source,first_seen_at,last_seen_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(conid) DO UPDATE SET
      symbol=excluded.symbol,
      local_symbol=COALESCE(excluded.local_symbol, portfolio_contracts.local_symbol),
      currency=COALESCE(excluded.currency, portfolio_contracts.currency),
      exchange=COALESCE(excluded.exchange, portfolio_contracts.exchange),
      primary_exchange=COALESCE(excluded.primary_exchange, portfolio_contracts.primary_exchange),
      trading_class=COALESCE(excluded.trading_class, portfolio_contracts.trading_class),
      expiry=COALESCE(excluded.expiry, portfolio_contracts.expiry),
      strike_decimal=COALESCE(excluded.strike_decimal, portfolio_contracts.strike_decimal),
      right_code=COALESCE(excluded.right_code, portfolio_contracts.right_code),
      multiplier_decimal=COALESCE(excluded.multiplier_decimal, portfolio_contracts.multiplier_decimal),
      description=COALESCE(excluded.description, portfolio_contracts.description),
      last_seen_at=excluded.last_seen_at`).bind(
    row.conid, row.symbol, row.local_symbol, row.sec_type, row.currency, row.exchange,
    row.primary_exchange, row.trading_class, row.expiry, row.strike_decimal, row.right_code,
    row.multiplier_decimal, row.description, source, now, now,
  )));
}
