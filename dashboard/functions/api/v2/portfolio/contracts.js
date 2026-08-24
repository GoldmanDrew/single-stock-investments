// The contract cache: every conId this account has held or the hub has resolved.
//
// This is the half of contract autofill that needs no Gateway at all. It reads
// what is already known, so it answers instantly, it answers on a weekend when
// `ibc.service` is legitimately down (CLAUDE.md rule 8), and it costs IBKR
// nothing. The live resolver in contract-lookups.js is the fallback for
// something that has never been seen -- which, for options, is most things.
//
// It is a convenience, never an authority. The hub re-qualifies every contract
// at preview time, so a stale row here costs one redundant qualify call.

import { boundedLimit, failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { portfolioOrderOwner } from "../../../_lib/paper-orders.js";

const privateHeaders = () => ({ "cache-control": "private, no-store" });

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    if (!owner) return json({ error: "This login is not mapped to a portfolio owner.", request_id: id }, 403, privateHeaders());

    const url = new URL(context.request.url);
    const query = String(url.searchParams.get("q") || "").trim().toUpperCase();
    const secType = String(url.searchParams.get("sec_type") || "").trim().toUpperCase();
    const limit = boundedLimit(url.searchParams.get("limit"), 20, 50);
    if (query.length < 1) {
      return json({
        schema_version: "portfolio_contracts.v1", query, contracts: [], request_id: id,
      }, 200, privateHeaders());
    }

    // Prefix before substring: typing "MS" should offer MSFT before it offers
    // something that merely contains MS. LIKE with an escaped pattern, because
    // a symbol may legitimately contain '.' or '-' and must not be read as a
    // wildcard by anything downstream.
    const pattern = `${query.replace(/[%_]/g, "")}%`;
    const contains = `%${query.replace(/[%_]/g, "")}%`;
    const filters = ["(symbol LIKE ? OR local_symbol LIKE ? OR description LIKE ?)"];
    const binds = [pattern, pattern, contains];
    if (secType) { filters.push("sec_type=?"); binds.push(secType); }

    const rows = await db_all(context, `SELECT conid,symbol,local_symbol,sec_type,currency,exchange,
        primary_exchange,trading_class,expiry,strike_decimal,right_code,multiplier_decimal,
        description,source,last_seen_at
      FROM portfolio_contracts WHERE ${filters.join(" AND ")}
      ORDER BY (symbol = ?) DESC, (symbol LIKE ?) DESC, last_seen_at DESC
      LIMIT ?`, [...binds, query, pattern, limit]);

    return json({
      schema_version: "portfolio_contracts.v1",
      query,
      // Naming the source matters: a cache hit is not proof the contract is
      // still tradeable, and the UI says so rather than implying a live check.
      note: "Previously resolved or held contracts. The hub re-qualifies before pricing.",
      contracts: rows,
      request_id: id,
    }, 200, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}

async function db_all(context, sql, binds) {
  const db = requireDatabase(context.env);
  const result = await db.prepare(sql).bind(...binds).all();
  return result.results || [];
}
