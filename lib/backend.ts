// Imported only by the route handler. Never expose these settings as NEXT_PUBLIC_*.
const ID = "[a-f0-9]{32}";
const routes = {
  GET: new RegExp(`^(health|jobs/${ID}|videos/${ID}\\.mp4)$`),
  POST: new RegExp(`^(generate|suggestions|jobs/${ID}/retry-reuse)$`),
};

function error(detail: string, status: number) {
  return Response.json({ detail }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function proxyBackend(request: Request, segments: string[]) {
  const path = segments.join("/");
  const method = request.method as keyof typeof routes;
  if (!routes[method]?.test(path)) return error("Endpoint not found.", 404);
  if (method === "POST") {
    const origin = request.headers.get("origin");
    // Next.js can normalize request.url to localhost when bound to 127.0.0.1.
    // Host retains the authority the browser actually used.
    const expectedOrigin = new URL(request.url);
    const host = request.headers.get("host");
    if (host) expectedOrigin.host = host;
    if (origin && origin !== expectedOrigin.origin) {
      return error("This request must come from the video workspace.", 403);
    }
    if (!request.headers.get("content-type")?.includes("application/json")) {
      return error("Send the request as JSON.", 415);
    }
  }

  let body: string | undefined;
  if (method === "POST") {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 16_384) {
          await reader.cancel();
          return error("Request is too large. Keep the prompt under 2,000 characters.", 413);
        }
        chunks.push(value);
      }
    }
    body = Buffer.concat(chunks).toString("utf8");
    try { JSON.parse(body); }
    catch { return error("The request contains invalid JSON.", 400); }
  }

  try {
    const base = new URL(process.env.MANIM_API_URL || "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(base.protocol)) {
      return error("The backend address must use HTTP or HTTPS.", 503);
    }
    const upstream = new URL(path === "health" ? "/health" : `/api/${path}`, base);
    const headers = new Headers();
    if (process.env.MANIM_API_KEY) headers.set("x-api-key", process.env.MANIM_API_KEY);
    if (body !== undefined) headers.set("Content-Type", "application/json");
    const range = request.headers.get("range");
    if (path.startsWith("videos/") && range) headers.set("Range", range);
    const signal = AbortSignal.any([request.signal, AbortSignal.timeout(120_000)]);
    let result = await fetch(upstream, {
      method, headers, body, cache: "no-store", redirect: "manual", signal,
    });

    // Fetch R2 separately so the backend API key never reaches video storage.
    if (path.startsWith("videos/") && [301, 302, 303, 307, 308].includes(result.status)) {
      const location = result.headers.get("location");
      if (!location) return error("Video storage did not return a download address.", 502);
      const videoUrl = new URL(location, upstream);
      if (!["http:", "https:"].includes(videoUrl.protocol)) return error("Invalid video address.", 502);
      await result.body?.cancel();
      result = await fetch(videoUrl, {
        headers: range ? { Range: range } : {}, cache: "no-store", signal,
      });
    }

    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "content-range", "accept-ranges", "content-disposition"]) {
      const value = result.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(result.body, { status: result.status, headers: responseHeaders });
  } catch {
    return error("Cannot reach the video backend. Check that the API is running, then try again.", 503);
  }
}
