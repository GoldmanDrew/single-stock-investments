import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";

const MAX_BODY_BYTES = 512_000;
const SCOPES = new Set(["market", "sector", "security"]);
const DIRECTIONS = new Set(["positive_bubble", "negative_bubble", "none"]);
const COMPONENT_ID = /^[a-z][a-z0-9_]{1,63}$/;

function hex(bytes) {
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function authorized(request, env, body) {
  const expected = String(env?.MARKET_RISK_INGEST_TOKEN || "");
  const timestamp = request.headers.get("x-market-risk-timestamp") || "";
  const nonce = request.headers.get("x-market-risk-nonce") || "";
  const supplied = (request.headers.get("x-market-risk-signature") || "").toLowerCase();
  const timestampNumber = Number(timestamp);
  if (expected.length < 24 || !/^\d{10}$/.test(timestamp)
      || !/^[a-f0-9]{32}$/.test(nonce) || !/^[a-f0-9]{64}$/.test(supplied)
      || !Number.isFinite(timestampNumber)
      || Math.abs(Date.now() / 1000 - timestampNumber) > 300) return false;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(expected), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const prefix = encoder.encode(`${timestamp}\n${nonce}\n`);
  const message = new Uint8Array(prefix.byteLength + body.byteLength);
  message.set(prefix, 0);
  message.set(new Uint8Array(body), prefix.byteLength);
  const computed = hex(new Uint8Array(await crypto.subtle.sign("HMAC", key, message)));
  const left = encoder.encode(computed);
  const right = encoder.encode(supplied);
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0 ? { nonce, timestamp } : false;
}

function compact(value) {
  return JSON.stringify(value);
}

function finite(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function alertSeverity(state) {
  return {
    observe: "low",
    critical: "medium",
    stress: "high",
    exhaustion_candidate: "high",
    confirmed_exhaustion: "critical",
  }[state] || "low";
}

function alertReasons(row) {
  const scores = row.scores || {};
  const confirmation = row.confirmation || {};
  const reasons = [];
  if (finite(scores.pressure) >= 70) reasons.push("pressure_extreme");
  if (finite(scores.panic) >= 70) reasons.push("panic_extreme");
  if (finite(scores.exhaustion) >= 45) reasons.push("exhaustion_evidence");
  for (const [key, passed] of Object.entries(confirmation)) {
    if (passed) reasons.push(`confirmation:${key}`);
  }
  return reasons.length ? reasons : [`state:${row.state}`];
}

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const body = await context.request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return json({ error: "Payload too large.", request_id: id }, 413);
    }
    const authorization = await authorized(context.request, context.env, body);
    if (!authorization) {
      return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, {
        "cache-control": "no-store",
      });
    }
    let payload;
    try {
      payload = JSON.parse(new TextDecoder().decode(body));
    } catch (_) {
      return json({ error: "Invalid JSON.", request_id: id }, 400);
    }
    const criticality = Array.isArray(payload.criticality) ? payload.criticality : [];
    const flow = Array.isArray(payload.flow) ? payload.flow : [];
    const components = Array.isArray(payload.components) ? payload.components : [];
    if (criticality.length + flow.length + components.length > 500) {
      return json({ error: "Too many snapshots.", request_id: id }, 400);
    }

    const db = requireDatabase(context.env);
    const nonceInsert = await db.prepare(`
      INSERT OR IGNORE INTO market_risk_ingest_nonces (nonce) VALUES (?)
    `).bind(authorization.nonce).run();
    if (Number(nonceInsert.meta?.changes || 0) !== 1) {
      return json({ error: "Replay rejected.", request_id: id }, 409, {
        "cache-control": "no-store",
      });
    }
    // Nonce retention is deploy-time only (prune_cloudflare_d1.py). Do not DELETE
    // on the hot ingest path — same full-scan trap as portfolio_ingest_nonces.
    const statements = [];
    const receivedAt = new Date().toISOString();
    for (const row of criticality) {
      if (!SCOPES.has(row.scope) || !DIRECTIONS.has(row.direction)
          || !row.symbol || !row.as_of || !row.model_version) {
        return json({ error: "Invalid criticality snapshot.", request_id: id }, 400);
      }
      const confidence = row.confidence || {};
      const criticalTime = row.critical_time || {};
      statements.push(db.prepare(`
        INSERT INTO criticality_snapshots (
          scope, symbol, as_of, horizon, model_version, direction,
          criticality_score, positive_confidence, negative_confidence,
          qualified_confidence, tc_p10_days, tc_median_days, tc_p90_days,
          fit_count, qualified_count, source, entitlement_mode,
          quality_state, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (scope, symbol, as_of, horizon, model_version)
        DO UPDATE SET
          direction=excluded.direction,
          criticality_score=excluded.criticality_score,
          positive_confidence=excluded.positive_confidence,
          negative_confidence=excluded.negative_confidence,
          qualified_confidence=excluded.qualified_confidence,
          tc_p10_days=excluded.tc_p10_days,
          tc_median_days=excluded.tc_median_days,
          tc_p90_days=excluded.tc_p90_days,
          fit_count=excluded.fit_count,
          qualified_count=excluded.qualified_count,
          source=excluded.source,
          entitlement_mode=excluded.entitlement_mode,
          quality_state=excluded.quality_state,
          payload_json=excluded.payload_json
      `).bind(
        row.scope, String(row.symbol).toUpperCase(), row.as_of,
        row.horizon || "multi", row.model_version, row.direction,
        finite(row.score) || 0, finite(confidence.positive) || 0,
        finite(confidence.negative) || 0, finite(confidence.qualified) || 0,
        finite(criticalTime.p10), finite(criticalTime.median), finite(criticalTime.p90),
        Number(row.fit_count || 0), Number(row.qualified_count || 0),
        row.source || null, row.entitlement_mode || "estimated",
        row.quality_state || row.status || "limited", compact(row),
      ));
    }
    for (const row of flow) {
      if (!SCOPES.has(row.scope) || !row.symbol || !row.as_of
          || !row.model_version || !row.state) {
        return json({ error: "Invalid flow snapshot.", request_id: id }, 400);
      }
      const scores = row.scores || {};
      const volTarget = row.vol_target || {};
      statements.push(db.prepare(`
        INSERT INTO flow_stress_snapshots (
          scope, symbol, as_of, model_version, state, pressure_score,
          panic_score, exhaustion_score, liquidity_score, breadth_score,
          vol_target_pressure_low, vol_target_pressure_high, source,
          entitlement_mode, quality_state, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (scope, symbol, as_of, model_version)
        DO UPDATE SET
          state=excluded.state,
          pressure_score=excluded.pressure_score,
          panic_score=excluded.panic_score,
          exhaustion_score=excluded.exhaustion_score,
          liquidity_score=excluded.liquidity_score,
          breadth_score=excluded.breadth_score,
          vol_target_pressure_low=excluded.vol_target_pressure_low,
          vol_target_pressure_high=excluded.vol_target_pressure_high,
          source=excluded.source,
          entitlement_mode=excluded.entitlement_mode,
          quality_state=excluded.quality_state,
          payload_json=excluded.payload_json
      `).bind(
        row.scope, String(row.symbol).toUpperCase(), row.as_of,
        row.model_version, row.state, finite(scores.pressure),
        finite(scores.panic), finite(scores.exhaustion), finite(scores.liquidity),
        finite(scores.breadth),
        finite(volTarget.estimated_exposure_reduction_pct_low),
        finite(volTarget.estimated_exposure_reduction_pct_high),
        row.source || null, row.entitlement_mode || "estimated",
        row.quality_state || "limited", compact(row),
      ));

      const openAlert = await db.prepare(`
        SELECT alert_id
        FROM market_risk_alerts
        WHERE scope = ? AND symbol = ? AND closed_at IS NULL
        ORDER BY opened_at DESC
        LIMIT 1
      `).bind(row.scope, String(row.symbol).toUpperCase()).first();
      if (row.state === "normal") {
        if (openAlert?.alert_id) {
          statements.push(db.prepare(`
            UPDATE market_risk_alerts
            SET updated_at = ?, closed_at = ?, state = 'resolved', payload_json = ?
            WHERE alert_id = ?
          `).bind(receivedAt, receivedAt, compact(row), openAlert.alert_id));
        }
      } else {
        const reasons = alertReasons(row);
        if (openAlert?.alert_id) {
          statements.push(db.prepare(`
            UPDATE market_risk_alerts
            SET updated_at = ?, state = ?, severity = ?, model_version = ?,
                reason_codes_json = ?, payload_json = ?
            WHERE alert_id = ?
          `).bind(
            receivedAt, row.state, alertSeverity(row.state), row.model_version,
            compact(reasons), compact(row), openAlert.alert_id,
          ));
        } else {
          statements.push(db.prepare(`
            INSERT INTO market_risk_alerts (
              alert_id, scope, symbol, opened_at, updated_at, state, severity,
              model_version, reason_codes_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          `).bind(
            crypto.randomUUID(), row.scope, String(row.symbol).toUpperCase(),
            receivedAt, receivedAt, row.state, alertSeverity(row.state),
            row.model_version, compact(reasons), compact(row),
          ));
        }
      }
    }
    for (const row of components) {
      if (!COMPONENT_ID.test(String(row.component || ""))
          || !SCOPES.has(row.scope) || !row.symbol || !row.as_of
          || !row.cadence || !row.source || !row.model_version
          || !row.entitlement_mode || !row.quality_state) {
        return json({ error: "Invalid component snapshot.", request_id: id }, 400);
      }
      statements.push(db.prepare(`
        INSERT INTO market_risk_component_snapshots (
          component, scope, symbol, as_of, cadence, source, model_version,
          entitlement_mode, quality_state, score, value, unit, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (component, scope, symbol, as_of, source, model_version)
        DO UPDATE SET
          cadence=excluded.cadence,
          entitlement_mode=excluded.entitlement_mode,
          quality_state=excluded.quality_state,
          score=excluded.score,
          value=excluded.value,
          unit=excluded.unit,
          payload_json=excluded.payload_json
      `).bind(
        row.component, row.scope, String(row.symbol).toUpperCase(), row.as_of,
        row.cadence, row.source, row.model_version, row.entitlement_mode,
        row.quality_state, finite(row.score), finite(row.value), row.unit || null,
        compact(row),
      ));
    }
    const symbols = [...new Set([
      ...criticality.map((row) => String(row.symbol || "").toUpperCase()),
      ...flow.map((row) => String(row.symbol || "").toUpperCase()),
      ...components.map((row) => String(row.symbol || "").toUpperCase()),
    ].filter(Boolean))];
    const generatedAt = payload.generated_at || null;
    const generatedMs = Date.parse(generatedAt || "");
    statements.push(db.prepare(`
      INSERT INTO market_risk_ingest_runs (
        request_id, received_at, generated_at, source, criticality_count,
        flow_count, component_count, symbols_json, status, latency_ms, payload_bytes
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?)
    `).bind(
      id, receivedAt, generatedAt, payload.source || null,
      criticality.length, flow.length, components.length, compact(symbols),
      Number.isFinite(generatedMs) ? Math.max(0, Date.now() - generatedMs) : null,
      body.byteLength,
    ));
    if (statements.length) await db.batch(statements);
    return json({
      accepted: {
        criticality: criticality.length,
        flow: flow.length,
        components: components.length,
      },
      request_id: id,
    }, 202, { "cache-control": "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}
