import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { proxyBackend } from "../lib/backend.ts";

const originalFetch = globalThis.fetch;
const originalUrl = process.env.MANIM_API_URL;
const originalKey = process.env.MANIM_API_KEY;
const id = "a".repeat(32);
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalUrl === undefined) delete process.env.MANIM_API_URL;
  else process.env.MANIM_API_URL = originalUrl;
  if (originalKey === undefined) delete process.env.MANIM_API_KEY;
  else process.env.MANIM_API_KEY = originalKey;
});
function request(path, options = {}) {
  return new Request(`http://localhost:3000/api/backend/${path}`, options);
}
function post(body, origin = "http://localhost:3000") {
  return request("generate", { method: "POST", headers: { "Content-Type": "application/json", origin }, body });
}

test("forwards generation with the server key, without client credentials or cookies", async () => {
  process.env.MANIM_API_URL = "http://backend:8000";
  process.env.MANIM_API_KEY = "test-server-key";
  globalThis.fetch = async (url, options) => {
    assert.equal(String(url), "http://backend:8000/api/generate");
    assert.equal(options.headers.get("x-api-key"), "test-server-key");
    assert.equal(options.headers.get("cookie"), null);
    assert.equal(options.body, '{"prompt":"Explain gravity","share_for_reuse":false}');
    assert.equal(options.cache, "no-store");
    return Response.json({ job_id: id });
  };
  const input = post('{"prompt":"Explain gravity","share_for_reuse":false}');
  input.headers.set("x-api-key", "client-value");
  input.headers.set("cookie", "private=cookie");
  const result = await proxyBackend(input, ["generate"]);
  assert.deepEqual(await result.json(), { job_id: id });
  assert.equal(result.headers.get("x-api-key"), null);
  assert.equal(result.headers.get("cache-control"), "no-store");
});

test("rejects arbitrary paths, mismatched methods, cross-origin POSTs and oversized JSON before fetching", async () => {
  globalThis.fetch = async () => assert.fail("Unexpected backend call");
  assert.equal((await proxyBackend(request("health"), ["..", "secret"])).status, 404);
  assert.equal((await proxyBackend(post("{}"), ["health"])).status, 404);
  assert.equal((await proxyBackend(post("{}", "https://other.example"), ["generate"])).status, 403);
  assert.equal((await proxyBackend(post("x"), ["generate"])).status, 400);
  assert.equal((await proxyBackend(post(JSON.stringify({ prompt: "x".repeat(17_000) })), ["generate"])).status, 413);
  assert.equal((await proxyBackend(request("generate", { method: "POST", body: "{}" }), ["generate"])).status, 415);
});

test("preserves backend validation errors and missing job status", async () => {
  globalThis.fetch = async () => Response.json({ detail: "Job not found." }, { status: 404 });
  const result = await proxyBackend(request(`jobs/${id}`), ["jobs", id]);
  assert.equal(result.status, 404);
  assert.deepEqual(await result.json(), { detail: "Job not found." });
});

test("accepts the browser Host when Next normalizes request.url to localhost", async () => {
  globalThis.fetch = async () => Response.json({ job_id: id });
  const input = post("{}", "http://127.0.0.1:3000");
  input.headers.set("host", "127.0.0.1:3000");
  assert.equal((await proxyBackend(input, ["generate"])).status, 200);
});

test("streams partial video responses with byte-range metadata", async () => {
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.get("range"), "bytes=0-3");
    return new Response(new Uint8Array([0, 1, 2, 3]), {
      status: 206,
      headers: { "Content-Type": "video/mp4", "Content-Range": "bytes 0-3/10", "Accept-Ranges": "bytes" },
    });
  };
  const result = await proxyBackend(request(`videos/${id}.mp4`, { headers: { Range: "bytes=0-3" } }), ["videos", `${id}.mp4`]);
  assert.equal(result.status, 206);
  assert.equal(result.headers.get("content-range"), "bytes 0-3/10");
  assert.equal(result.headers.get("accept-ranges"), "bytes");
  assert.deepEqual([...new Uint8Array(await result.arrayBuffer())], [0, 1, 2, 3]);
});

test("follows storage redirects without leaking the backend API key", async () => {
  process.env.MANIM_API_KEY = "test-server-key";
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    if (calls === 1) {
      assert.equal(options.redirect, "manual");
      assert.equal(options.headers.get("x-api-key"), "test-server-key");
      return new Response(null, { status: 307, headers: { Location: "https://storage.example/video?signature=test" } });
    }
    assert.equal(String(url), "https://storage.example/video?signature=test");
    assert.equal(new Headers(options.headers).get("x-api-key"), null);
    assert.equal(new Headers(options.headers).get("range"), "bytes=0-3");
    return new Response("mp4", { headers: { "Content-Type": "video/mp4" } });
  };
  const result = await proxyBackend(request(`videos/${id}.mp4`, { headers: { Range: "bytes=0-3" } }), ["videos", `${id}.mp4`]);
  assert.equal(await result.text(), "mp4");
  assert.equal(calls, 2);
});

test("reports connection failure without exposing credentials or internal fetch errors", async () => {
  globalThis.fetch = async () => { throw new Error("private internal error"); };
  const result = await proxyBackend(request("health"), ["health"]);
  assert.equal(result.status, 503);
  assert.match((await result.json()).detail, /Cannot reach/);
});
