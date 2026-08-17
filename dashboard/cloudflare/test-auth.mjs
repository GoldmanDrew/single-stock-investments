import assert from "node:assert/strict";
import test from "node:test";

import { validateAccessClaims, verifyAccessJwt } from "../functions/_lib/auth.js";

const env = {
  CF_ACCESS_TEAM_DOMAIN: "https://example.cloudflareaccess.com",
  CF_ACCESS_AUD: "portfolio-audience",
};

test("accepts a current app token for the configured issuer and audience", () => {
  const payload = validateAccessClaims({
    iss: "https://example.cloudflareaccess.com",
    aud: ["portfolio-audience"],
    exp: 2_000,
    nbf: 900,
    type: "app",
  }, env, 1_000);
  assert.equal(payload.type, "app");
});

test("rejects an audience mismatch", () => {
  assert.throws(() => validateAccessClaims({
    iss: "https://example.cloudflareaccess.com",
    aud: ["wrong"],
    exp: 2_000,
    type: "app",
  }, env, 1_000), /audience mismatch/);
});

test("rejects an expired token", () => {
  assert.throws(() => validateAccessClaims({
    iss: "https://example.cloudflareaccess.com",
    aud: ["portfolio-audience"],
    exp: 800,
    type: "app",
  }, env, 1_000), /expired/);
});

test("verifies the Access RS256 signature against the matching JWKS key", async () => {
  const pair = await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  );
  const publicJwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  publicJwk.kid = "test-key";
  publicJwk.alg = "RS256";
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const header = encode({ alg: "RS256", kid: "test-key" });
  const payload = encode({ iss: env.CF_ACCESS_TEAM_DOMAIN, aud: [env.CF_ACCESS_AUD], exp: Math.floor(Date.now() / 1000) + 300, type: "app", email: "viewer@example.com" });
  const message = `${header}.${payload}`;
  const signature = Buffer.from(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", pair.privateKey, new TextEncoder().encode(message))).toString("base64url");
  const viewer = await verifyAccessJwt(`${message}.${signature}`, env, async () => new Response(JSON.stringify({ keys: [publicJwk] }), { status: 200 }));
  assert.equal(viewer.email, "viewer@example.com");
});
