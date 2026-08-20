// Validation for the order command channel.
//
// The rule this file exists to enforce: a browser request is *data*, never a
// command. Nothing here decides that an order should be placed. It only proves
// the request is well formed and that the person asking is who the Access login
// says they are, so the hub on the trusted machine can make the real decision.

const DECIMAL = /^[0-9]+(?:\.[0-9]+)?$/;

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
  return {
    owner: authorizedOwner,
    conid,
    symbol: String(payload.symbol).trim().slice(0, 24),
    sec_type: String(payload.sec_type).trim().slice(0, 12),
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
