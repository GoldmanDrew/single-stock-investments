import { onRequestPost } from "../functions/api/v1/market-risk/ingest.js";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/api/v1/market-risk/ingest") {
      return new Response("Not found.", { status: 404 });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed.", {
        status: 405,
        headers: { allow: "POST" },
      });
    }
    return onRequestPost({ request, env });
  },
};
