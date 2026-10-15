// Local UI fixture. Does not call a model or render a video.
// Start with: node tests/fixture-backend.mjs
import http from "node:http";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const id = "a".repeat(32);
const sharedId = "b".repeat(32);
let createdAt = 0;
let submitted = {};
const plan = {
  audience: "beginners", objective: "Understand why the squares on a right triangle's sides fit the Pythagorean theorem.",
  scope: "A 3-4-5 right triangle", steps: [
    { explanation: "Start with a right triangle whose legs measure 3 and 4.", visual_intent: "Draw the triangle." },
    { explanation: "Compare the areas of the three squares: 9 + 16 = 25.", visual_intent: "Reveal squares on each side." },
  ], takeaway: "The two leg squares have the same total area as the hypotenuse square.",
};
const storyboard = { title: "The Pythagorean theorem", beats: [
  { caption: "Start with a right triangle", animation_seconds: 1.2, hold_seconds: 2 },
  { caption: "9 + 16 = 25", animation_seconds: 1.2, hold_seconds: 3 },
] };
function job(jobId) {
  const shared = jobId === sharedId;
  const elapsed = shared ? 20_000 : Date.now() - createdAt;
  const stage = ["lesson_plan", "storyboard", "coding", "rendering", "completed"][Math.min(4, Math.floor(elapsed / 2500))];
  const failed = !shared && (submitted.prompt || "").includes("fixture-failure") && elapsed >= 5000;
  return {
    job_id: jobId, prompt: shared ? "A shared lesson about a 3-4-5 triangle." : submitted.prompt,
    quality: submitted.quality || "m", status: failed ? "failed" : elapsed >= 10_000 ? "succeeded" : "running",
    generation_stage: failed ? "coding" : stage, lesson_plan: elapsed >= 2500 ? plan : null,
    storyboard: elapsed >= 5000 ? storyboard : null,
    error: failed ? "Fixture render failed. Revise the request and try again." : null,
    share_for_reuse: shared || Boolean(submitted.share_for_reuse), reuse_error: null,
  };
}
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, "http://localhost");
  response.setHeader("Content-Type", "application/json");
  if (url.pathname === "/health") return response.end('{"ok":true}');
  if (request.headers["x-api-key"] !== "fixture-key") {
    response.writeHead(401); return response.end('{"detail":"Invalid API key."}');
  }
  if (url.pathname === "/api/generate" && request.method === "POST") {
    let body = "";
    for await (const chunk of request) body += chunk;
    submitted = JSON.parse(body); createdAt = Date.now();
    return response.end(JSON.stringify({ job_id: id }));
  }
  if (url.pathname === "/api/suggestions") {
    return response.end(JSON.stringify({ suggestions: [{ job_id: sharedId, prompt: "A shared lesson about a 3-4-5 triangle.", score: 0.95 }] }));
  }
  if (url.pathname === `/api/jobs/${id}` || url.pathname === `/api/jobs/${sharedId}`) {
    return response.end(JSON.stringify(job(url.pathname.split("/").at(-1))));
  }
  if (url.pathname.startsWith("/api/videos/")) {
    const file = readdirSync("videos").find((name) => name.endsWith(".mp4"));
    if (!file) { response.writeHead(404); return response.end('{"detail":"Add a local MP4 to videos for playback checks."}'); }
    const bytes = readFileSync(path.join("videos", file));
    const range = request.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
    response.setHeader("Content-Type", "video/mp4"); response.setHeader("Accept-Ranges", "bytes");
    if (range) {
      const start = Number(range[1]); const end = Math.min(Number(range[2] || bytes.length - 1), bytes.length - 1);
      response.writeHead(206, { "Content-Range": `bytes ${start}-${end}/${bytes.length}` });
      return response.end(bytes.subarray(start, end + 1));
    }
    return response.end(bytes);
  }
  response.writeHead(404); response.end('{"detail":"Job not found."}');
});
server.listen(8101, "127.0.0.1", () => console.log("UI fixture backend listening on 127.0.0.1:8101"));
