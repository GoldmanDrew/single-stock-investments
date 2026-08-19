const OWNERS = new Set(["drew", "michael"]);
const SECURITY_TYPES = new Set(["STK", "ETF", "OPT", "WAR"]);
const SIDES = new Set(["BUY", "SELL"]);
const SYMBOL_PATTERN = /^[A-Z0-9][A-Z0-9.\-/ ]{0,23}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function emailSet(raw) {
  return new Set(String(raw || "")
    .split(/[\s,;]+/)
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean));
}

function boundedText(value, label, maximum, { required = true } = {}) {
  const text = String(value ?? "").trim();
  if (required && !text) throw new TypeError(`${label} is required.`);
  if (text.length > maximum) throw new TypeError(`${label} must be ${maximum} characters or fewer.`);
  return text;
}

function positiveDecimal(value, label, { integer = false } = {}) {
  const text = String(value ?? "").trim();
  if (!/^\d+(?:\.\d{1,6})?$/.test(text)) throw new TypeError(`${label} must be a positive number.`);
  const number = Number(text);
  if (!Number.isFinite(number) || number <= 0 || number > 1_000_000_000) {
    throw new TypeError(`${label} is outside the supported range.`);
  }
  if (integer && !Number.isInteger(number)) throw new TypeError(`${label} must be a whole number for options.`);
  return text;
}

export function portfolioOrderOwner(viewer, env) {
  const email = String(viewer?.email || "").trim().toLowerCase();
  if (!email) return null;

  // Access service tokens identify machines, not the human portfolio owner.
  if (viewer?.service_token) return null;

  if (email === "local-development") {
    const developmentOwner = String(env?.PORTFOLIO_DEVELOPMENT_OWNER || "").trim().toLowerCase();
    return OWNERS.has(developmentOwner) ? developmentOwner : null;
  }

  const drewEmails = emailSet(env?.PORTFOLIO_DREW_ACCESS_EMAILS);
  const michaelEmails = emailSet(env?.PORTFOLIO_MICHAEL_ACCESS_EMAILS);
  const isDrew = drewEmails.has(email);
  const isMichael = michaelEmails.has(email);
  if (isDrew && isMichael) throw new Error("Portfolio order identity is assigned to more than one owner.");
  if (isDrew) return "drew";
  if (isMichael) return "michael";
  return null;
}

export function validatePaperOrder(payload, authorizedOwner) {
  const owner = String(authorizedOwner || "").trim().toLowerCase();
  if (!OWNERS.has(owner)) throw new TypeError("This login is not authorized for paper order entry.");
  if (payload?.owner != null && String(payload.owner).trim().toLowerCase() !== owner) {
    throw new TypeError(`This login can only queue orders for the ${owner} portfolio.`);
  }
  if (payload?.mode != null && String(payload.mode).trim().toLowerCase() !== "paper") {
    throw new TypeError("Browser order entry is paper-only.");
  }
  if (payload?.transmitted === true || payload?.transmitted === 1) {
    throw new TypeError("Paper orders cannot be transmitted.");
  }

  const clientRequestId = boundedText(payload?.client_request_id, "Client request ID", 64);
  if (!UUID_PATTERN.test(clientRequestId)) throw new TypeError("Client request ID must be a UUID.");

  const symbol = boundedText(payload?.symbol, "Symbol", 24).toUpperCase();
  if (!SYMBOL_PATTERN.test(symbol)) throw new TypeError("Symbol contains unsupported characters.");
  const secType = boundedText(payload?.sec_type, "Security type", 8).toUpperCase();
  if (!SECURITY_TYPES.has(secType)) throw new TypeError("Security type must be stock, ETF, option, or warrant.");
  const side = boundedText(payload?.side, "Side", 4).toUpperCase();
  if (!SIDES.has(side)) throw new TypeError("Side must be buy or sell.");

  let conid = null;
  if (payload?.conid != null && String(payload.conid).trim()) {
    conid = Number(payload.conid);
    if (!Number.isInteger(conid) || conid <= 0) throw new TypeError("IB contract ID must be a positive integer.");
  }
  if (conid == null) throw new TypeError("IB contract ID is required for every paper order.");

  const quantity = positiveDecimal(payload?.quantity, "Quantity", { integer: secType === "OPT" });
  const limitPrice = positiveDecimal(payload?.limit_price, "Limit price");
  const rationale = boundedText(payload?.rationale, "Rationale", 500, { required: false });

  if (String(payload?.order_type || "LMT").toUpperCase() !== "LMT") {
    throw new TypeError("Paper order entry supports limit orders only.");
  }
  if (String(payload?.tif || "DAY").toUpperCase() !== "DAY") {
    throw new TypeError("Paper order entry supports DAY orders only.");
  }

  return {
    client_request_id: clientRequestId,
    owner,
    symbol,
    sec_type: secType,
    conid,
    side,
    quantity_decimal: quantity,
    limit_price_decimal: limitPrice,
    order_type: "LMT",
    tif: "DAY",
    currency: "USD",
    rationale,
  };
}

export function requirePaperOrderRequest(request) {
  const contentType = String(request.headers.get("content-type") || "").toLowerCase();
  if (!contentType.startsWith("application/json")) throw new TypeError("Paper orders require a JSON request.");
  if (request.headers.get("x-paper-order-mode") !== "paper") {
    throw new TypeError("Paper order confirmation header is missing.");
  }
  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin) throw new TypeError("Paper orders must come from this dashboard.");
  const fetchSite = String(request.headers.get("sec-fetch-site") || "same-origin").toLowerCase();
  if (!new Set(["same-origin", "same-site", "none"]).has(fetchSite)) {
    throw new TypeError("Cross-site paper order requests are not allowed.");
  }
}

export function ownerUniverseViolation(ticket, owner, strategyPayloads = []) {
  if (owner !== "michael") return null;
  const symbol = String(ticket?.symbol || "").toUpperCase();
  const conid = Number(ticket?.conid);
  if (ticket?.sec_type === "OPT" && /^SPX(?:W)?(?:\b| )/.test(symbol)) {
    return "SPX options belong to the SPX 0DTE strategy, not Michael's portfolio.";
  }
  for (const payload of strategyPayloads) {
    const producer = String(payload?.producer || "");
    for (const row of payload?.rows || []) {
      const rowSymbols = [row.symbol, row.underlying, ...(String(row.metrics?.symbols || "").split(/[, ]+/))]
        .map((value) => String(value || "").toUpperCase()).filter(Boolean);
      const sameContract = conid > 0 && Number(row.conid) === conid;
      const sameSymbol = rowSymbols.includes(symbol);
      if (producer === "spx_0dte" && ticket?.sec_type === "OPT" && (sameContract || sameSymbol)) {
        return "This contract belongs to the SPX 0DTE strategy, not Michael's portfolio.";
      }
      if (producer === "ls_risk" && (sameContract || sameSymbol)) {
        return "This instrument is in the LS-algo ETF/underlying universe and cannot be queued for Michael.";
      }
    }
  }
  return null;
}
