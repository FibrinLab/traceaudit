// Cloudflare Pages Function: proxies /api/* from the static site to the service (Cloudflare Container or any host).
// Set API_ORIGIN in the Pages project's environment variables, e.g. https://traceaudit.<account>.workers.dev
export async function onRequest({ request, env }) {
  const origin = env.API_ORIGIN;
  if (!origin) {
    return new Response(JSON.stringify({ error: { code: "no_api", message: "API_ORIGIN is not configured for this site" } }),
      { status: 503, headers: { "content-type": "application/json" } });
  }
  const url = new URL(request.url);
  const target = origin.replace(/\/$/, "") + url.pathname + url.search;
  const headers = new Headers(request.headers);
  headers.delete("host");
  const init = { method: request.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
  const resp = await fetch(target, init);
  const out = new Headers(resp.headers);
  out.set("cache-control", "no-store");
  return new Response(resp.body, { status: resp.status, headers: out });
}
