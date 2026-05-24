/** GitHub OAuth (PKCE) helpers for static dashboard — no client secret required. */
(function (global) {
  const TOKEN_KEY = 'gh_oauth_token';
  const USER_KEY = 'gh_oauth_user';
  const LEGACY_TOKEN_KEY = 'gh_onboard_token';
  const PKCE_KEY = 'oauth_pkce_verifier';
  const RETURN_KEY = 'oauth_return';

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

  async function loadConfig() {
    const res = await fetch(`${basePath()}/data/oauth_config.json?${Date.now()}`);
    if (!res.ok) throw new Error('Missing oauth_config.json');
    return res.json();
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

  async function signIn(clientId) {
    if (!clientId) throw new Error('OAuth client_id not configured');
    const verifier = randomUrlSafe(32);
    const challenge = await pkceChallenge(verifier);
    global.sessionStorage.setItem(PKCE_KEY, verifier);
    global.sessionStorage.setItem(RETURN_KEY, global.location.href);
    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri(),
      scope: 'repo',
      state: randomUrlSafe(16),
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });
    global.location.href = `https://github.com/login/oauth/authorize?${params}`;
  }

  async function handleCallback(clientId) {
    const q = new URLSearchParams(global.location.search);
    const err = q.get('error');
    if (err) throw new Error(q.get('error_description') || err);
    const code = q.get('code');
    if (!code) throw new Error('No authorization code in callback URL');
    const verifier = global.sessionStorage.getItem(PKCE_KEY);
    if (!verifier) throw new Error('PKCE verifier missing — start sign-in again from the dashboard');

    const body = new URLSearchParams({
      client_id: clientId,
      code,
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    });
    const res = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: { Accept: 'application/json' },
      body,
    });
    const data = await res.json();
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
    handleCallback,
    refreshAuthUi,
    redirectUri,
    dashboardUrl,
  };
})(window);
