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

## R2 storage

Set `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET` in `backend/.env`. A completed MP4 is uploaded to `videos/{job_id}.mp4`. The API still serves the video through its authenticated route and redirects to a signed R2 URL. If the upload fails, the job is marked failed with the error and the local output remains available on the jobs volume for recovery.

## Similar video suggestions

Run `docker compose --profile reuse up --build` and set `QDRANT_URL=http://qdrant:6333` plus `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). Prompt embeddings use Gemini's `models/gemini-embedding-001` model by default, so reuse works with Gemini keys without an OpenAI key. Qdrant stores embeddings and job IDs. SQLite stores prompts and job metadata.

Only requests with `"share_for_reuse":true` are indexed. Call `POST /api/suggestions` with a prompt and quality before generating. It returns up to five completed videos with a similarity score above `SIMILARITY_THRESHOLD`. The user can choose one or proceed to `POST /api/generate`. Similarity alone does not prove that a video answers the new prompt, so the backend does not silently replace a new request with a previous video. The frontend can show the original prompt and preview for this choice.

The default similarity threshold is 0.93 and should be measured against real prompts before relying on it. Suggestions are scoped by render quality. Sharing is off by default. Do not enable cross-user reuse for private prompts without adding user accounts, access rules, and a way to withdraw shared videos.

## Limits

This is a single-host setup with one sequential renderer. The API handles up to two generation jobs at a time. The renderer has no network, uses an unprivileged user, and has memory, CPU, and process limits, but it can access the shared jobs volume. An AST check catches malformed or obvious unsafe code; container isolation is the security boundary. The worker image contains Manim and LaTeX, so builds and renders can be large. Docker was not available in the development environment, so an end-to-end container render still needs verification on a machine with Docker.
