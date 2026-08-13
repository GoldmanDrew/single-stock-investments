const ALLOWED = new Set([
  "dgoldman", "goldmandrew", "mcricenti", "dsapienza", "dylansapienza", "dsap5131",
]);

function hex(bytes) {
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function verifySleeveHmac(request, env, body) {
  const expected = String(env?.SLEEVE_INGEST_TOKEN || "");
  const timestamp = request.headers.get("x-sleeve-timestamp") || "";
  const nonce = request.headers.get("x-sleeve-nonce") || "";
  const supplied = (request.headers.get("x-sleeve-signature") || "").toLowerCase();
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

export async function githubLogin(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.toLowerCase().startsWith("bearer ") ? header.slice(7).trim() : "";
  if (!token) return null;
  const res = await fetch("https://api.github.com/user", {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "magis-sleeves",
    },
  });
  if (!res.ok) return null;
  const user = await res.json();
  const login = String(user.login || "").toLowerCase();
  const extra = String(env?.SLEEVE_ALLOWED_LOGINS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  const allow = extra.length ? new Set([...ALLOWED, ...extra]) : ALLOWED;
  if (!allow.has(login)) return null;
  return { login: user.login, name: user.name || user.login };
}

export function emptyBook(owner) {
  const michael = owner === "michael";
  return {
    owner,
    display_name: michael ? "Michael" : "Drew",
    as_of: null,
    long_term: true,
    header: {
      equity_usd: michael ? null : 100000,
      extra_margin_usd: michael ? 0 : 100000,
      nav_usd: 0,
      gross_usd: 0,
      cash_usd: 0,
      buying_power_usd: michael ? 0 : 200000,
      open_names: 0,
      blurb: michael
        ? "Live Magis account after taking out the ls-algo universe and SPX 0DTE. Blacklist names Michael trades by hand stay here."
        : "Starts empty. New buys tagged DREW_SLEEVE on the local desk show up here. $100k equity plus $100k extra margin.",
    },
    positions: [],
    ideas: [],
    notes: [],
    fills: [],
    metrics: {
      completeness: 1,
      independence: { score: 1, mean_abs_corr: 0, pair_count: 0 },
      sleeve_xirr: null,
      max_drawdown: null,
      median_holding_years: null,
      open_names: 0,
      plc_events: 0,
      conviction_calibration: [1, 2, 3, 4, 5].map((conviction) => ({
        conviction, count: 0, avg_irr: null, plc_rate: null, median_years_held: null,
      })),
    },
    dry_run: true,
    allow_live: false,
    source: "empty",
  };
}

export async function loadBook(db, owner) {
  const book = emptyBook(owner);
  const [config, positions, notes, ideas, fills, cashflows] = await db.batch([
    db.prepare("SELECT * FROM sleeve_config WHERE owner = ?").bind(owner),
    db.prepare("SELECT * FROM sleeve_positions WHERE owner = ?").bind(owner),
    db.prepare("SELECT * FROM sleeve_notes WHERE owner = ? ORDER BY note_date DESC").bind(owner),
    db.prepare("SELECT * FROM sleeve_ideas WHERE owner = ?").bind(owner),
    db.prepare("SELECT * FROM sleeve_fills WHERE owner = ? ORDER BY filled_at DESC").bind(owner),
    db.prepare("SELECT * FROM sleeve_cashflows WHERE owner = ? ORDER BY date").bind(owner),
  ]);
  const cfg = config.results?.[0];
  if (cfg) {
    book.header.equity_usd = cfg.equity_usd;
    book.header.extra_margin_usd = cfg.extra_margin_usd;
    book.as_of = cfg.as_of;
  }
  const ideaMap = Object.fromEntries((ideas.results || []).map((row) => [row.ticker, row]));
  const notesByTicker = {};
  for (const note of notes.results || []) {
    (notesByTicker[note.ticker] ||= []).push(note);
  }
  let gross = 0;
  let cash = 0;
  book.positions = (positions.results || []).map((row) => {
    const idea = ideaMap[row.ticker] || {};
    const mv = Number(row.market_value || 0);
    if (row.classifier_reason === "cash") {
      cash += Math.abs(mv);
      return null;
    }
    gross += Math.abs(mv);
    return {
      ticker: row.ticker,
      side: Number(row.qty) >= 0 ? "BUY" : "SELL",
      status: idea.status || "filled",
      qty: row.qty,
      mark: row.mark,
      market_value: mv,
      entry_price: idea.entry_price,
      cost_usd: idea.cost_usd,
      cluster: idea.cluster || "idiosyncratic",
      conviction: idea.conviction,
      plc_score: idea.plc_score,
      plc_thesis: idea.plc_thesis,
      holding_period_years: idea.holding_period_years,
      classifier_reason: row.classifier_reason,
      notes: notesByTicker[row.ticker] || [],
      needs_thesis: !(notesByTicker[row.ticker] || []).length,
    };
  }).filter(Boolean);
  book.ideas = ideas.results || [];
  book.notes = notes.results || [];
  book.fills = fills.results || [];
  book.cashflows = cashflows.results || [];
  book.header.gross_usd = gross;
  book.header.cash_usd = cash;
  book.header.nav_usd = gross + cash;
  const equity = Number(book.header.equity_usd || (owner === "drew" ? 100000 : book.header.nav_usd));
  book.header.buying_power_usd = equity + Number(book.header.extra_margin_usd || 0) - gross;
  book.header.open_names = book.positions.length;
  const noted = new Set(book.notes.map((n) => n.ticker));
  book.metrics.completeness = book.positions.length
    ? book.positions.filter((p) => noted.has(p.ticker)).length / book.positions.length
    : 1;
  book.metrics.open_names = book.positions.length;
  const clusterCount = {};
  for (const pos of book.positions) {
    const key = pos.cluster || "idiosyncratic";
    clusterCount[key] = (clusterCount[key] || 0) + 1;
  }
  let same = 0;
  let pairs = 0;
  const clusters = book.positions.map((p) => p.cluster || "idiosyncratic");
  for (let i = 0; i < clusters.length; i += 1) {
    for (let j = i + 1; j < clusters.length; j += 1) {
      pairs += 1;
      if (clusters[i] === clusters[j]) same += 1;
    }
  }
  const meanAbs = pairs ? same / pairs : 0;
  book.metrics.independence = {
    score: Number((1 - meanAbs).toFixed(4)),
    mean_abs_corr: Number(meanAbs.toFixed(4)),
    pair_count: pairs,
    same_cluster_pairs: same,
  };
  book.source = "d1";
  return book;
}
