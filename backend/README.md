# Manim video backend

The API turns a prompt into Manim code. A separate renderer container produces the MP4. The renderer has no network access or LLM keys. Job records live in SQLite and video files live on a Docker volume. Cloudflare R2 and Qdrant are optional.

## Start

Copy `backend/.env.example` to `backend/.env`, add an LLM key, and set `API_KEY` before exposing the API. Then run:

```bash
docker compose up --build
```

The API listens on port 8000. Docker and a running Docker daemon are required. Set `OPENAI_API_KEY` for OpenAI code generation. Anthropic and Google code generation use their matching keys. The renderer timeout is 300 seconds in the Compose file; change that value alongside `RENDER_TIMEOUT_SEC` if needed.

For Gemini, a temporary per-minute 429 quota response makes the API wait 65 seconds and retry code generation up to two times. Set `LLM_RATE_LIMIT_RETRIES` and `LLM_RATE_LIMIT_WAIT_SEC` in `backend/.env` to change those bounds. A per-day quota error fails immediately because a short retry cannot clear it.

## Generate and retrieve

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" -H "x-api-key: YOUR_KEY" \
  -d '{"prompt":"Animate the Pythagorean theorem with squares on each side","quality":"m"}'
```

The response contains a `job_id`. Poll `GET /api/jobs/{job_id}` until the status is `succeeded` or `failed`, then fetch `GET /api/videos/{job_id}.mp4` with the API key. The video route returns the local file or redirects to a short lived R2 signed URL. `l`, `m`, and `h` select render quality. `k` requires `ALLOW_HIGH_QUALITY=true`.

Jobs that were queued or running when the API stopped resume after it starts again. Failed jobs retain their error in SQLite. The renderer writes results to the shared jobs volume, while SQLite is mounted only in the API container.

## Generation prompt and video quality

`app/prompts/manim_system.txt` is the shared system prompt for Gemini, OpenAI, and Anthropic. Edit this file to change lesson and design instructions. The generator reads it for each new generation and replaces only `{scene_name}`, so Python examples and formulas can keep literal braces. The path is relative to the generator module, independent of the working directory. A missing, empty, or placeholder-free file fails generation before contacting the model. The Dockerfile copies the prompt with `app`; rebuild the API image after editing it. Existing saved scenes and reused videos keep their original code.

The prompt asks for one accurate, scoped lesson across domains, with ordered explanatory beats, measured text and box layouts, clear arrow routes, readable font sizes, explicit animation durations, reading pauses, and a stable takeaway. It specifies a centered content rectangle with padding on all four sides: at least 12% of the frame width on each horizontal side and 12% of the frame height on each vertical side, with a minimum of 0.6 scene units. Titles and captions share this safe rectangle with the diagram. Connectors need clear corridors around boxes and text, separate lanes for return messages, and space between arrowheads, borders, and message labels. Crowded messages should appear sequentially. These margins help landscape playback on different screens; a portrait composition still requires a separate layout. The prompt retains the 5-25 second limit. Dense subjects should become a labeled overview or excerpt, rather than a rushed complete lesson.

These are model instructions, not a guarantee or an automated visual validator. The AST validator checks code structure and obvious unsafe operations. It does not verify the lesson, measure the rendered layout, enforce duration, or inspect transition frames. There is no automatic quality review or render-repair loop. A successful render still needs review before treating it as a correct lesson.

To evaluate a prompt revision, generate and watch videos for several subjects using the same provider, model, and render quality:

- Two-phase commit with a successful decision and the prepared-state blocking limitation.
- A historical timeline from supplied dates, with events in the correct order.
- A business process with a decision and its two outcomes.
- A language example showing a sentence before and after a grammatical change.
- A scientific mechanism with labeled parts and the direction of cause and effect.
- A mathematical example with a formula and its interpretation.
- Long actor names and a dense request that requires shortening the scope.

Check held frames and transitions for clipped or overlapping text, box padding, connector crossings, consistent roles, and captions that match the diagram. Time the complete video, including the final hold, and check that a beginner can read each beat. Check claims against appropriate references and record the original request, generated code, model, prompt revision, and observed problems. The generator tests verify file loading and system-message wiring with mocked models; they do not establish video quality.

## R2 storage

Set `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET` in `backend/.env`. A completed MP4 is uploaded to `videos/{job_id}.mp4`. The API still serves the video through its authenticated route and redirects to a signed R2 URL. If the upload fails, the job is marked failed with the error and the local output remains available on the jobs volume for recovery.

## Similar video suggestions

Run `docker compose --profile reuse up --build` and set `QDRANT_URL=http://qdrant:6333` plus `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). Prompt embeddings use Gemini's `models/gemini-embedding-001` model by default, so reuse works with Gemini keys without an OpenAI key. Qdrant stores embeddings and job IDs. SQLite stores prompts and job metadata.

Only requests with `"share_for_reuse":true` are indexed. Call `POST /api/suggestions` with a prompt and quality before generating. It returns up to five completed videos with a similarity score above `SIMILARITY_THRESHOLD`. The user can choose one or proceed to `POST /api/generate`. Similarity alone does not prove that a video answers the new prompt, so the backend does not silently replace a new request with a previous video. The frontend can show the original prompt and preview for this choice.

If a video rendered but embedding or Qdrant indexing failed, fix the configuration and call `POST /api/jobs/{job_id}/retry-reuse` with the API key. This indexes the existing completed video without rendering it again. Check `reuse_indexed` and `reuse_error` in the response.

The default similarity threshold is 0.93 and should be measured against real prompts before relying on it. Suggestions are scoped by render quality. Sharing is off by default. Do not enable cross-user reuse for private prompts without adding user accounts, access rules, and a way to withdraw shared videos.

## Limits

This is a single-host setup with one sequential renderer. The API handles up to two generation jobs at a time. The renderer has no network, uses an unprivileged user, and has memory, CPU, and process limits, but it can access the shared jobs volume. An AST check catches malformed or obvious unsafe code; container isolation is the security boundary. The worker image contains Manim and LaTeX, so builds and renders can be large. Docker was not available in the development environment, so an end-to-end container render still needs verification on a machine with Docker.
