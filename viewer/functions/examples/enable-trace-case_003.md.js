// The former example artefact was removed from the site on 29 Oct 2026. Functions run before the static asset cache,
// so this answers the old path at once instead of waiting for the edge cache to expire.
export function onRequest() {
  return new Response("Not found", { status: 404, headers: { "content-type": "text/plain", "cache-control": "no-store" } });
}
