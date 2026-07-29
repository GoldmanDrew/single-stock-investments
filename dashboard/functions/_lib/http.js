const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "public, max-age=30, stale-while-revalidate=120",
  "x-content-type-options": "nosniff",
};

export function json(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...JSON_HEADERS, ...extraHeaders },
  });
}

export function failure(error, requestId) {
  console.error(JSON.stringify({
    message: "dashboard API request failed",
    request_id: requestId,
    error: error instanceof Error ? error.message : String(error),
  }));
  return json(
    {
      error: "The dashboard database could not complete this request.",
      request_id: requestId,
    },
    500,
    { "cache-control": "no-store" },
  );
}

export function requireDatabase(env) {
  if (!env?.DB) {
    throw new Error("Missing required D1 binding: DB");
  }
  return env.DB;
}

export function boundedLimit(raw, defaultValue = 50, maximum = 100) {
  const parsed = Number.parseInt(raw ?? "", 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return defaultValue;
  return Math.min(parsed, maximum);
}

export function requestId(request) {
  return request.headers.get("cf-ray") || crypto.randomUUID();
}
