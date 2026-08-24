// Validation for the order command channel.
//
// The rule this file exists to enforce: a browser request is *data*, never a
// command. Nothing here decides that an order should be placed. It only proves
// the request is well formed and that the person asking is who the Access login
// says they are, so the hub on the trusted machine can make the real decision.

const DECIMAL = /^[0-9]+(?:\.[0-9]+)?$/;
const EXPIRY = /^\d{8}$/;

// IBKR files ETFs as STK. "ETF" is not an IB secType, so a ticket carrying it
// fingerprints an instrument that does not exist -- the qualified contract comes
// back STK and the string the human approved names something else.
export const REQUEST_SEC_TYPES = new Set(["STK", "OPT"]);

export const REQUEST_STATES = new Set([
  "requested",    // browser wrote it; hub has not looked yet
  "drafting",     // hub claimed it
  "previewed",    // hub published live quote + margin, approval clock running
  "approved",     // human confirmed the exact contract inside the window
  "submitting",   // hub is transmitting
  "acknowledged", // broker has it
  "filled",
  "cancelled",
  "rejected",
  "expired",
]);

// States a human action may move a request into, and from where. The hub owns
// every other transition; the edge can only request and approve.
export const EDGE_TRANSITIONS = {
  approve: { from: new Set(["previewed"]), to: "approved" },
  cancel: { from: new Set(["requested", "previewed", "approved", "acknowledged"]), to: "cancel_requested" },
};

export const ORDER_MODES = new Set(["dry_run", "paper", "live"]);
const ACTIONS = new Set(["BUY", "SELL"]);
const TIFS = new Set(["DAY", "GTC", "IOC", "FOK"]);

export function validateOrderRequest(payload, authorizedOwner) {
  if (!authorizedOwner) {
    throw new TypeError("This login is not mapped to a portfolio owner.");
  }
  // Owner is taken from the verified Access identity, never from the body. A
  // client that sends one is trying to place an order for someone else.
  if (payload?.owner && payload.owner !== authorizedOwner) {
    throw new TypeError("Order owner does not match the authenticated login.");
  }
  const conid = Number(payload?.conid);
  if (!Number.isInteger(conid) || conid <= 0) {
    throw new TypeError("A qualified IB contract id is required.");
  }
  if (!ACTIONS.has(payload?.action)) {
    throw new TypeError("Action must be BUY or SELL.");
  }
  if (!DECIMAL.test(String(payload?.quantity ?? "")) || Number(payload.quantity) <= 0) {
    throw new TypeError("Quantity must be a positive decimal.");
  }
  if (!DECIMAL.test(String(payload?.limit_price ?? "")) || Number(payload.limit_price) <= 0) {
    throw new TypeError("Limit price must be a positive decimal.");
  }
  if (!ORDER_MODES.has(payload?.mode || "dry_run")) {
    throw new TypeError("Mode must be dry_run, paper, or live.");
  }
  if (payload?.tif && !TIFS.has(payload.tif)) {
    throw new TypeError("Unsupported time in force.");
  }
  if (!payload?.symbol || !payload?.sec_type) {
    throw new TypeError("Symbol and security type are required.");
  }
  const secType = String(payload.sec_type).trim().toUpperCase();
  if (!REQUEST_SEC_TYPES.has(secType)) {
    throw new TypeError("Security type must be STK or OPT (IBKR files ETFs as STK).");
  }

  const option = validateOptionIdentity(payload, secType);
  return {
    owner: authorizedOwner,
    conid,
    ...option,
    symbol: String(payload.symbol).trim().slice(0, 24),
    sec_type: secType,
    action: payload.action,
    quantity: String(payload.quantity),
    limit_price: String(payload.limit_price),
    currency: payload.currency ? String(payload.currency).trim().slice(0, 3).toUpperCase() : null,
    tif: payload.tif || "DAY",
    outside_rth: Boolean(payload.outside_rth),
    // The edge cannot promote a ticket to live on its own. Even a body that says
    // "live" only records an intent; the hub still needs its own live interlock
    // enabled and its kill switch off before anything transmits.
    mode: payload.mode || "dry_run",
    strategy: String(payload.strategy || "single_stock").trim().slice(0, 32),
    rationale: String(payload.rationale || "").slice(0, 500),
  };
}

/**
 * An approval is only meaningful if it names the exact contract that was
 * previewed and arrives before the hub's clock runs out. Both checks are
 * repeated on the hub against its own HMAC; this is the cheap first gate.
 */
export function validateApproval(row, payload, viewerEmail, now = new Date()) {
  if (!row) throw new TypeError("Unknown order request.");
  if (row.state !== "previewed") {
    throw new TypeError(`Only a previewed order can be approved (state: ${row.state}).`);
  }
  if (!row.contract_fingerprint || payload?.contract_fingerprint !== row.contract_fingerprint) {
    throw new TypeError("Approval does not match the previewed contract.");
  }
  if (!row.approval_expires_at || new Date(row.approval_expires_at) <= now) {
    throw new TypeError("The approval window has expired. Preview again.");
  }
  if (!viewerEmail) throw new TypeError("Authentication required.");
  return { approved_by: viewerEmail, approved_fingerprint: payload.contract_fingerprint };
}

/**
 * The exchange date in New York, as YYYYMMDD.
 *
 * Expiry is an exchange fact, so it has to be compared against the exchange's
 * calendar. Using the Worker's UTC date instead would reject a legitimate
 * next-session expiry every evening after 20:00 ET, and -- worse in the other
 * direction -- would call a contract "tomorrow" during the small hours when the
 * exchange still calls it today.
 */
export function exchangeToday(now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now).replace(/-/g, "");
}

/**
 * Option identity, and the refusals that only make sense for options.
 *
 * A stock ticket is identified by its conId alone. An option is not, in the
 * sense that matters here: the conId is correct but unreadable, so the identity
 * is carried alongside it and the fingerprint is built from the qualified
 * contract on the hub. What a human approves has to be something a human can
 * check.
 */
export function validateOptionIdentity(payload, secType, now = new Date()) {
  if (secType !== "OPT") {
    for (const field of ["expiry", "strike", "right"]) {
      if (payload?.[field] != null && String(payload[field]).trim() !== "") {
        throw new TypeError(`${field} only applies to an option ticket.`);
      }
    }
    return { expiry: null, strike: null, right: null, multiplier: null, trading_class: null, exchange: null, local_symbol: null };
  }

  const expiry = String(payload?.expiry ?? "").trim();
  if (!EXPIRY.test(expiry)) throw new TypeError("An option ticket needs an expiry as YYYYMMDD.");

  // Same-day expiry is refused outright, and not because it is hard.
  //
  // 0DTE on this account belongs to the SPX strategy, which has its own
  // executor, its own risk rails and its own client ID. An expiring contract
  // entered by hand through a web form has hours of life, no stop, and assigns
  // overnight if it finishes in the money. There is no version of this desk
  // where that is the right tool, so the refusal is unconditional rather than
  // a warning someone can click through.
  const today = exchangeToday(now);
  if (expiry < today) throw new TypeError("That option has already expired.");
  if (expiry === today) {
    throw new TypeError("Same-day expiry is not available here. 0DTE belongs to the SPX strategy.");
  }

  const strike = String(payload?.strike ?? "").trim();
  if (!DECIMAL.test(strike) || Number(strike) <= 0) throw new TypeError("Strike must be a positive decimal.");

  const right = String(payload?.right ?? "").trim().toUpperCase();
  if (!["P", "C"].includes(right)) throw new TypeError("Right must be P (put) or C (call).");

  // Contracts are indivisible; a fractional option order is a typo, and IBKR
  // would reject it after the ticket had already been previewed and approved.
  const quantity = String(payload?.quantity ?? "").trim();
  if (!/^\d+$/.test(quantity)) throw new TypeError("Option quantity must be a whole number of contracts.");

  // An option filled outside regular hours is filled against a book that barely
  // exists. The hub's price band would pass it, because the band is relative to
  // a midpoint that is itself meaningless at 04:00.
  if (payload?.outside_rth) throw new TypeError("Option orders may not be routed outside regular trading hours.");

  const multiplier = payload?.multiplier == null || String(payload.multiplier).trim() === ""
    ? null : String(payload.multiplier).trim();
  if (multiplier !== null && (!DECIMAL.test(multiplier) || Number(multiplier) <= 0)) {
    throw new TypeError("Multiplier must be a positive decimal.");
  }

  return {
    expiry, strike, right, multiplier,
    trading_class: payload?.trading_class ? String(payload.trading_class).trim().slice(0, 16).toUpperCase() : null,
    exchange: payload?.exchange ? String(payload.exchange).trim().slice(0, 16).toUpperCase() : null,
    local_symbol: payload?.local_symbol ? String(payload.local_symbol).replace(/\s+/g, " ").trim().slice(0, 64) : null,
  };
}
