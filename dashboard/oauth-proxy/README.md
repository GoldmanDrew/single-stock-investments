# Marvin OAuth proxy (Cloudflare Worker)

GitHub Pages cannot call `github.com/login/oauth/access_token` from the browser (CORS). This worker forwards OAuth requests server-side.

## One-time deploy (~2 min)

1. [Cloudflare account](https://dash.cloudflare.com/sign-up) (free)
2. Install Wrangler: `npm install -g wrangler` (or use `npx wrangler`)
3. Login: `npx wrangler login`
4. Deploy from this folder:

```powershell
cd dashboard/oauth-proxy
npx wrangler deploy
```

5. Copy the worker URL (e.g. `https://marvin-oauth-proxy.yourname.workers.dev`)
6. Set GitHub repo variable **`OAUTH_PROXY_URL`** to that URL (no trailing slash)
7. Redeploy dashboard (push to main or run **Deploy Dashboard** workflow)

## OAuth App

Enable **Device Flow** on your OAuth App (github.com/settings/developers → your app → Device Flow checkbox).

Callback URL is still required but device flow is primary; keep:
`https://goldmandrew.github.io/single-stock-investments/oauth/callback.html`

## Repo variables

| Variable | Example |
|----------|---------|
| `OAUTH_CLIENT_ID` | `Ov23li...` |
| `OAUTH_PROXY_URL` | `https://marvin-oauth-proxy.yourname.workers.dev` |
