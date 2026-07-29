/**
 * CORS proxy for GitHub OAuth token/device endpoints (static Pages cannot call github.com/login/*).
 * Deploy: npx wrangler deploy
 * Set repo variable OAUTH_PROXY_URL to the worker URL (e.g. https://marvin-oauth-proxy.USER.workers.dev)
 */
const PROXY_VERSION = '2026-07-29';

// Magis Cloudflare Pages project currently serves on the assigned *.pages.dev host.
const DEFAULT_ORIGIN = 'https://single-stock-investments-2wt.pages.dev';

const ALLOW_ORIGINS = new Set([
  DEFAULT_ORIGIN,
  'https://single-stock-investments.pages.dev',
  'https://magis-capital-partners.github.io',
  'https://goldmandrew.github.io',
  'http://localhost:8080',
  'http://127.0.0.1:8080',
  'http://localhost:8765',
  'http://127.0.0.1:8765',
]);

function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (ALLOW_ORIGINS.has(origin)) return true;
  try {
    const host = new URL(origin).hostname;
    return (
      host === 'single-stock-investments.pages.dev' ||
      host === 'single-stock-investments-2wt.pages.dev' ||
      host.endsWith('.single-stock-investments.pages.dev') ||
      host.endsWith('.single-stock-investments-2wt.pages.dev')
    );
  } catch (_e) {
    return false;
  }
}

function corsHeaders(origin) {
  // Echo the request origin when allowlisted so browser CORS checks pass.
  const allow = isAllowedOrigin(origin) ? origin : DEFAULT_ORIGIN;
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
    Vary: 'Origin',
  };
}

async function forwardToGitHub(githubPath, request) {
  const contentType = request.headers.get('Content-Type') || 'application/json';
  const body = await request.text();
  const gh = await fetch(`https://github.com${githubPath}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': contentType,
    },
    body,
  });
  return gh.text();
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const headers = { 'Content-Type': 'application/json', ...corsHeaders(origin) };

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);
    if (request.method === 'GET' && (url.pathname === '/health' || url.pathname.endsWith('/health'))) {
      return new Response(
        JSON.stringify({
          ok: true,
          version: PROXY_VERSION,
          allowed_origins: [...ALLOW_ORIGINS],
        }),
        { status: 200, headers },
      );
    }

    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'method_not_allowed' }), { status: 405, headers });
    }

    let githubPath;
    if (url.pathname === '/device/code' || url.pathname.endsWith('/device/code')) {
      githubPath = '/login/device/code';
    } else if (url.pathname === '/access_token' || url.pathname.endsWith('/access_token')) {
      githubPath = '/login/oauth/access_token';
    } else {
      return new Response(JSON.stringify({ error: 'not_found' }), { status: 404, headers });
    }

    try {
      const text = await forwardToGitHub(githubPath, request);
      return new Response(text, { status: 200, headers });
    } catch (_e) {
      return new Response(JSON.stringify({ error: 'proxy_failed' }), {
        status: 502,
        headers,
      });
    }
  },
};
