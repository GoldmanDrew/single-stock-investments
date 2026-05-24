/**
 * CORS proxy for GitHub OAuth token/device endpoints (static Pages cannot call github.com/login/*).
 * Deploy: npx wrangler deploy
 * Set repo variable OAUTH_PROXY_URL to the worker URL (e.g. https://marvin-oauth-proxy.USER.workers.dev)
 */
const ALLOW_ORIGINS = new Set([
  'https://goldmandrew.github.io',
  'http://localhost:8080',
  'http://127.0.0.1:8080',
]);

function corsHeaders(origin) {
  const allow = origin && ALLOW_ORIGINS.has(origin) ? origin : 'https://goldmandrew.github.io';
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
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
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'method_not_allowed' }), { status: 405, headers });
    }

    const url = new URL(request.url);
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
    } catch (e) {
      return new Response(JSON.stringify({ error: 'proxy_failed', message: String(e) }), {
        status: 502,
        headers,
      });
    }
  },
};
