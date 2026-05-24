/** GitHub OAuth helpers for static dashboard (device flow + PKCE via optional CORS proxy). */
(function (global) {
  const TOKEN_KEY = 'gh_oauth_token';
  const USER_KEY = 'gh_oauth_user';
  const LEGACY_TOKEN_KEY = 'gh_onboard_token';
  const PKCE_KEY = 'oauth_pkce_verifier';
  const RETURN_KEY = 'oauth_return';
  const DEVICE_KEY = 'oauth_device';

  /** Site root path (Pages deploy root = dashboard/), regardless of current page. */
  function basePath() {
    let path = global.location.pathname.replace(/\/index\.html$/i, '');
    path = path.replace(/\/oauth\/[^/]*$/i, '');
    return path.replace(/\/$/, '') || '';
  }

  function redirectUri() {
    return `${global.location.origin}${basePath()}/oauth/callback.html`;
  }

  function dashboardUrl() {
    const base = basePath();
    return `${global.location.origin}${base ? base + '/' : '/'}`;
  }

  function randomUrlSafe(bytes) {
    const arr = new Uint8Array(bytes);
    crypto.getRandomValues(arr);
    let bin = '';
    arr.forEach(b => { bin += String.fromCharCode(b); });
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  async function pkceChallenge(verifier) {
    const data = new TextEncoder().encode(verifier);
    const hash = await crypto.subtle.digest('SHA-256', data);
    let bin = '';
    new Uint8Array(hash).forEach(b => { bin += String.fromCharCode(b); });
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  let cachedConfig = null;

  async function loadConfig() {
    if (cachedConfig) return cachedConfig;
    const res = await fetch(`${basePath()}/data/oauth_config.json?${Date.now()}`);
    if (!res.ok) throw new Error('Missing oauth_config.json');
    cachedConfig = await res.json();
    return cachedConfig;
  }

  function proxyBase(cfg) {
    const url = (cfg.exchange_url || cfg.proxy_url || '').replace(/\/$/, '');
    return url || null;
  }

  async function githubOAuthPost(cfg, githubPath, payload) {
    const proxy = proxyBase(cfg);
    let url;
    if (proxy) {
      url = githubPath === '/login/device/code'
        ? `${proxy}/device/code`
        : `${proxy}/access_token`;
    } else {
      url = `https://github.com${githubPath}`;
    }

    const isDeviceCodeReq = githubPath === '/login/device/code';
    const headers = { Accept: 'application/json' };
    let body;
    if (isDeviceCodeReq) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(payload);
    } else {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      body = new URLSearchParams(Object.entries(payload).map(([k, v]) => [k, String(v)])).toString();
    }

    const res = await fetch(url, { method: 'POST', headers, body });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(text.slice(0, 200) || `OAuth HTTP ${res.status}`);
    }
    if (!res.ok && !data.error) {
      throw new Error(`OAuth HTTP ${res.status}: ${text.slice(0, 200)}`);
    }
    return data;
  }

  function getToken() {
    return global.localStorage.getItem(TOKEN_KEY)
      || global.localStorage.getItem(LEGACY_TOKEN_KEY)
      || '';
  }

  function getUser() {
    try {
      const raw = global.localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function clearAuth() {
    global.localStorage.removeItem(TOKEN_KEY);
    global.localStorage.removeItem(USER_KEY);
    global.localStorage.removeItem(LEGACY_TOKEN_KEY);
  }

  async function fetchUser(token) {
    const res = await fetch('https://api.github.com/user', {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
      },
    });
    if (!res.ok) return null;
    const u = await res.json();
    return { login: u.login, name: u.name || u.login, avatar: u.avatar_url };
  }

  async function saveToken(token) {
    global.localStorage.setItem(TOKEN_KEY, token);
    global.localStorage.removeItem(LEGACY_TOKEN_KEY);
    const user = await fetchUser(token);
    if (user) global.localStorage.setItem(USER_KEY, JSON.stringify(user));
    return user;
  }

  async function signIn(clientId, cfg) {
    if (!clientId) throw new Error('OAuth client_id not configured');
    if (!proxyBase(cfg)) {
      throw new Error(
        'OAUTH_PROXY_URL not configured. Deploy dashboard/oauth-proxy to Cloudflare and set the repo variable. See dashboard/oauth-proxy/README.md'
      );
    }

    const device = await githubOAuthPost(cfg, '/login/device/code', {
      client_id: clientId,
      scope: 'repo',
    });
    if (device.error) throw new Error(device.error_description || device.error);

    global.sessionStorage.setItem(DEVICE_KEY, JSON.stringify({
      device_code: device.device_code,
      interval: device.interval || 5,
      expires_in: device.expires_in || 900,
      client_id: clientId,
      started: Date.now(),
    }));

    return {
      user_code: device.user_code,
      verification_uri: device.verification_uri || 'https://github.com/login/device',
      interval: device.interval || 5,
    };
  }

  async function pollDeviceAuth(cfg) {
    const raw = global.sessionStorage.getItem(DEVICE_KEY);
    if (!raw) throw new Error('No device auth in progress');
    const dev = JSON.parse(raw);
    const elapsed = (Date.now() - dev.started) / 1000;
    if (elapsed > (dev.expires_in || 900)) {
      global.sessionStorage.removeItem(DEVICE_KEY);
      throw new Error('Device code expired — click Sign in again');
    }

    const data = await githubOAuthPost(cfg, '/login/oauth/access_token', {
      client_id: dev.client_id,
      device_code: dev.device_code,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    });

    if (data.error === 'authorization_pending') return { pending: true };
    if (data.error === 'slow_down') return { pending: true, slow: true };
    if (data.error) throw new Error(data.error_description || data.error);
    if (!data.access_token) throw new Error('No access_token in OAuth response');

    global.sessionStorage.removeItem(DEVICE_KEY);
    await saveToken(data.access_token);
    return { pending: false, token: data.access_token };
  }

  function cancelDeviceAuth() {
    global.sessionStorage.removeItem(DEVICE_KEY);
  }

  /** Legacy PKCE redirect callback (requires proxy for token exchange). */
  async function handleCallback(clientId, cfg) {
    const q = new URLSearchParams(global.location.search);
    const err = q.get('error');
    if (err) throw new Error(q.get('error_description') || err);
    const code = q.get('code');
    if (!code) throw new Error('No authorization code in callback URL');
    const verifier = global.sessionStorage.getItem(PKCE_KEY);
    if (!verifier) throw new Error('PKCE verifier missing — use Sign in with GitHub on the dashboard');

    const data = await githubOAuthPost(cfg, '/login/oauth/access_token', {
      client_id: clientId,
      code,
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    });
    if (data.error) throw new Error(data.error_description || data.error);
    if (!data.access_token) throw new Error('No access_token in OAuth response');

    global.sessionStorage.removeItem(PKCE_KEY);
    const ret = global.sessionStorage.getItem(RETURN_KEY) || dashboardUrl();
    global.sessionStorage.removeItem(RETURN_KEY);
    await saveToken(data.access_token);
    global.location.replace(ret);
  }

  async function refreshAuthUi(btn) {
    if (!btn) return;
    const token = getToken();
    const user = getUser();
    if (token && !user) {
      const u = await fetchUser(token);
      if (u) global.localStorage.setItem(USER_KEY, JSON.stringify(u));
      else clearAuth();
    }
    const u2 = getUser();
    if (getToken() && u2) {
      btn.textContent = `@${u2.login}`;
      btn.title = 'Signed in with GitHub — click to sign out';
      btn.dataset.signedIn = '1';
    } else {
      btn.textContent = 'Sign in with GitHub';
      btn.title = 'Authorize onboard workflow via GitHub OAuth';
      btn.dataset.signedIn = '0';
    }
  }

  global.MarvinOAuth = {
    loadConfig,
    getToken,
    getUser,
    clearAuth,
    signIn,
    pollDeviceAuth,
    cancelDeviceAuth,
    handleCallback,
    refreshAuthUi,
    redirectUri,
    dashboardUrl,
    proxyBase,
  };
})(window);
