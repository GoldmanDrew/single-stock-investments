import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { privateJson, requirePortfolioViewer } from "../../../_lib/auth.js";
import { githubLogin, loadBook } from "../../../_lib/sleeves.js";

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return privateJson({ error: "Unauthorized.", request_id: id }, 401);
    const user = await githubLogin(context.request, context.env);
    if (!user) {
      return json({ error: "Sign in with GitHub to save notes.", request_id: id }, 401, {
        "cache-control": "no-store",
      });
    }
    const payload = await context.request.json();
    const owner = String(payload.owner || "");
    const ticker = String(payload.ticker || "").trim().toUpperCase();
    const body = String(payload.body || payload.thought_process || "").trim();
    const plc = String(payload.plc_thesis || "").trim();
    const years = Number(payload.holding_period_years);
    const conviction = Number(payload.conviction);
    if (!["drew", "michael"].includes(owner) || !ticker || !body || !plc) {
      return json({ error: "owner, ticker, thought process, and PLC sentence are required.", request_id: id }, 400);
    }
    if (!(years > 0) || ![1, 2, 3, 4, 5].includes(conviction)) {
      return json({ error: "holding period (years) and conviction 1-5 are required.", request_id: id }, 400);
    }
    const db = requireDatabase(context.env);
    const noteDate = String(payload.note_date || new Date().toISOString().slice(0, 10));
    await db.batch([
      db.prepare(`
        INSERT INTO sleeve_notes (
          owner, ticker, note_date, body, entry_price, shares, cost_usd,
          conviction, plc_score, plc_thesis, holding_period_years, cluster, author
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        owner, ticker, noteDate, body,
        payload.entry_price ?? null, payload.shares ?? null, payload.cost_usd ?? null,
        conviction, payload.plc_score ?? null, plc, years,
        payload.cluster || "idiosyncratic", user.login,
      ),
      db.prepare(`
        INSERT INTO sleeve_ideas (
          owner, ticker, side, status, cluster, conviction, plc_score, plc_thesis,
          holding_period_years, entry_price, shares, cost_usd, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(owner, ticker) DO UPDATE SET
          side = excluded.side,
          status = excluded.status,
          cluster = excluded.cluster,
          conviction = excluded.conviction,
          plc_score = excluded.plc_score,
          plc_thesis = excluded.plc_thesis,
          holding_period_years = excluded.holding_period_years,
          entry_price = excluded.entry_price,
          shares = excluded.shares,
          cost_usd = excluded.cost_usd,
          updated_at = CURRENT_TIMESTAMP
      `).bind(
        owner, ticker, payload.side || "BUY", payload.status || "idea",
        payload.cluster || "idiosyncratic", conviction, payload.plc_score ?? null, plc,
        years, payload.entry_price ?? null, payload.shares ?? null, payload.cost_usd ?? null,
      ),
    ]);
    const book = await loadBook(db, owner);
    return json({ ok: true, author: user.login, book, request_id: id }, 200, { "cache-control": "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}
