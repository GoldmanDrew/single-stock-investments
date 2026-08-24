// Ask the hub what a symbol resolves to.
//
// POST records a question; GET reads the hub's answer. Nothing here talks to
// IBKR, and nothing here can be made to: the browser's request is a row in D1
// that the bridge polls on its own schedule, from the trusted machine, holding
// the only credentials that reach the Gateway.
//
// Why this exists at all: an option conId is not something a person can type.
// Without a resolver, "options support" means asking a human to hand-enter a
// nine-digit broker identifier for a contract they cannot verify -- which is
// the single most dangerous field on an order ticket.

import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { portfolioOrderOwner } from "../../../_lib/paper-orders.js";
import { validateContractLookup } from "../../../_lib/contracts.js";

const privateHeaders = () => ({ "cache-control": "private, no-store" });

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    if (!owner) return json({ error: "This login is not mapped to a portfolio owner.", request_id: id }, 403, privateHeaders());

    const db = requireDatabase(context.env);
    const wanted = new URL(context.request.url).searchParams.get("lookup_id");
    const rows = wanted
      ? await db.prepare(`SELECT lookup_id,kind,symbol,sec_type,currency,exchange,expiry,strike_decimal,
            right_code,state,matches_json,error,created_at,updated_at
          FROM portfolio_contract_lookups WHERE lookup_id=? AND owner=?`).bind(wanted, owner).all()
      : await db.prepare(`SELECT lookup_id,kind,symbol,sec_type,currency,exchange,expiry,strike_decimal,
            right_code,state,matches_json,error,created_at,updated_at
          FROM portfolio_contract_lookups WHERE owner=? ORDER BY created_at DESC LIMIT 20`).bind(owner).all();

    return json({
      schema_version: "portfolio_contract_lookups.v1",
      command_plane: "python_private_only",
      lookups: (rows.results || []).map((row) => ({
        ...row,
        matches: row.matches_json ? JSON.parse(row.matches_json) : [],
        matches_json: undefined,
      })),
      request_id: id,
    }, 200, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    const body = await context.request.json().catch(() => null);
    if (!body) return json({ error: "A JSON body is required.", request_id: id }, 400, privateHeaders());

    let lookup;
    try {
      lookup = validateContractLookup(body, owner);
    } catch (error) {
      return json({ error: error.message, request_id: id }, 400, privateHeaders());
    }

    const db = requireDatabase(context.env);
    const run = await db.prepare(`SELECT account_alias FROM portfolio_source_runs
      WHERE source='ibkr' AND complete=1 ORDER BY as_of DESC LIMIT 1`).first();
    if (!run) {
      return json({ error: "No complete broker snapshot; the hub is not reachable.", request_id: id }, 409, privateHeaders());
    }

    // Collapse repeats. A typeahead fires on keystrokes, and a fresh row per
    // keystroke would put the bridge into a qualify loop against IBKR's pacing
    // limits for no benefit -- the answer to the same question does not change
    // minute to minute.
    const recent = await db.prepare(`SELECT lookup_id,state FROM portfolio_contract_lookups
      WHERE owner=? AND kind=? AND symbol=? AND sec_type=?
        AND IFNULL(expiry,'')=IFNULL(?,'') AND IFNULL(strike_decimal,'')=IFNULL(?,'')
        AND IFNULL(right_code,'')=IFNULL(?,'')
        AND created_at > datetime('now','-10 minutes')
      ORDER BY created_at DESC LIMIT 1`).bind(
      owner, lookup.kind, lookup.symbol, lookup.sec_type, lookup.expiry, lookup.strike, lookup.right,
    ).first();
    if (recent && recent.state !== "failed") {
      return json({
        schema_version: "portfolio_contract_lookups.v1",
        lookup_id: recent.lookup_id, state: recent.state, reused: true, request_id: id,
      }, 200, privateHeaders());
    }

    const now = new Date().toISOString();
    const key = crypto.randomUUID();
    await db.prepare(`INSERT INTO portfolio_contract_lookups
      (lookup_id,account_alias,owner,kind,symbol,sec_type,currency,exchange,expiry,strike_decimal,
       right_code,state,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,'requested',?,?)`).bind(
      key, run.account_alias, lookup.owner, lookup.kind, lookup.symbol, lookup.sec_type,
      lookup.currency, lookup.exchange, lookup.expiry, lookup.strike, lookup.right, now, now,
    ).run();

    return json({
      schema_version: "portfolio_contract_lookups.v1",
      lookup_id: key, state: "requested", reused: false,
      note: "Recorded for the private hub. The browser never contacts IBKR.",
      request_id: id,
    }, 201, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}
