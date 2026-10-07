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

New API generations use three model stages, with the same provider and model throughout:

1. `app/prompts/lesson_plan_system.txt` produces a structured lesson plan with its audience, objective, scope, facts, assumptions, example, ordered steps, misconceptions, limitations, and takeaway.
2. `app/prompts/storyboard_system.txt` turns the lesson into exact on-screen words, visible object regions, connector routes, transitions, and reading holds. The backend checks the JSON schema, step coverage and order, final takeaway, proposed geometry, and timing before proceeding.
3. `app/prompts/manim_system.txt` generates Python from the validated plan and storyboard. The existing AST validator checks that code before the render worker receives it.

The generator reads prompts for each new generation. It replaces only `{scene_name}` in the code prompt, so Python examples and formulas can keep literal braces. Paths are relative to the generator module, independent of the working directory. A missing file, or an empty or placeholder-free code prompt, fails generation before contacting the model. The Dockerfile copies all prompts with `app`; rebuild the API image after editing them. Existing saved scenes and reused videos keep their original code.

Each planning stage gets one repair attempt after a schema or storyboard validation error. Set `PLANNING_REPAIR_ATTEMPTS` to 0-2 to change this bound. Invalid plans fail the job before rendering; they do not silently fall back to direct code generation. Existing Gemini quota retries apply to every stage. Three model calls, plus any repairs or quota retries, cost more and take longer than the original single call.

Validated stages are saved as `lesson_plan.json` and `storyboard.json` in the job directory and in SQLite. `GET /api/jobs/{job_id}` exposes `lesson_plan`, `storyboard`, and `generation_stage`, which advances through `lesson_plan`, `storyboard`, `coding`, `rendering`, and `completed`. A failed job retains the stage and any completed plan for inspection. Jobs interrupted before code generation reuse their saved validated stages on restart. Older jobs can have null planning fields. Plans advance automatically; there is no manual plan-approval or editing UI yet.

The prompt asks for one accurate, scoped lesson across domains, with ordered explanatory beats, measured text and box layouts, clear arrow routes, readable font sizes, explicit animation durations, reading pauses, and a stable takeaway. It specifies a centered content rectangle with padding on all four sides: at least 12% of the frame width on each horizontal side and 12% of the frame height on each vertical side, with a minimum of 0.6 scene units. Titles and captions share this safe rectangle with the diagram. Connectors need clear corridors around boxes and text, separate lanes for return messages, and space between arrowheads, borders, and message labels. Crowded messages should appear sequentially. These margins help landscape playback on different screens; a portrait composition still requires a separate layout. The prompt retains the 5-25 second limit. Dense subjects should become a labeled overview or excerpt, rather than a rushed complete lesson.

Storyboard coordinates are fractions of the full frame, centered at the origin. Proposed object, title, caption, and message regions must fit inside the 12% safe margins. The validator rejects crowded regions, unknown arrow endpoints, arrows detached from their actors, connector segments through regions, crossings between connectors, missing lesson steps, insufficient reading holds, and planned durations outside 5-25 seconds. Clearance calculations use the default 16:9 Manim frame. Object regions are conservative rectangles, including labels; this can reject some visually acceptable curved or circular layouts.

These checks validate a proposal, not the rendered video. They do not measure actual font glyphs, inspect intermediate animation frames, confirm that generated code follows every storyboard coordinate, or verify factual claims. The AST validator checks code structure and obvious unsafe operations. There is no rendered-frame review or render-repair loop yet. A successful render still needs review before treating it as a correct lesson.

To evaluate a prompt revision, generate and watch videos for several subjects using the same provider, model, and render quality:

- Two-phase commit with a successful decision and the prepared-state blocking limitation.
- A historical timeline from supplied dates, with events in the correct order.
- A business process with a decision and its two outcomes.
- A language example showing a sentence before and after a grammatical change.
- A scientific mechanism with labeled parts and the direction of cause and effect.
- A mathematical example with a formula and its interpretation.
- Long actor names and a dense request that requires shortening the scope.

Check held frames and transitions for clipped or overlapping text, box padding, connector crossings, consistent roles, and captions that match the diagram. Time the complete video, including the final hold, and check that a beginner can read each beat. Check claims against appropriate references and record the original request, generated code, model, prompt revision, and observed problems. Backend tests exercise stage ordering, bounded repairs, planned geometry and timing, saved-plan resumption, and job-status fields with mocked models and worker results. They do not establish video quality.

## R2 storage

Set `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET` in `backend/.env`. A completed MP4 is uploaded to `videos/{job_id}.mp4`. The API still serves the video through its authenticated route and redirects to a signed R2 URL. If the upload fails, the job is marked failed with the error and the local output remains available on the jobs volume for recovery.

## Similar video suggestions

Run `docker compose --profile reuse up --build` and set `QDRANT_URL=http://qdrant:6333` plus `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). Prompt embeddings use Gemini's `models/gemini-embedding-001` model by default, so reuse works with Gemini keys without an OpenAI key. Qdrant stores embeddings and job IDs. SQLite stores prompts and job metadata.

Only requests with `"share_for_reuse":true` are indexed. Call `POST /api/suggestions` with a prompt and quality before generating. It returns up to five completed videos with a similarity score above `SIMILARITY_THRESHOLD`. The user can choose one or proceed to `POST /api/generate`. Similarity alone does not prove that a video answers the new prompt, so the backend does not silently replace a new request with a previous video. The frontend can show the original prompt and preview for this choice.

If a video rendered but embedding or Qdrant indexing failed, fix the configuration and call `POST /api/jobs/{job_id}/retry-reuse` with the API key. This indexes the existing completed video without rendering it again. Check `reuse_indexed` and `reuse_error` in the response.

The default similarity threshold is 0.93 and should be measured against real prompts before relying on it. Suggestions are scoped by render quality. Sharing is off by default. Do not enable cross-user reuse for private prompts without adding user accounts, access rules, and a way to withdraw shared videos.

## Limits

This is a single-host setup with one sequential renderer. The API handles up to two generation jobs at a time. The renderer has no network, uses an unprivileged user, and has memory, CPU, and process limits, but it can access the shared jobs volume. An AST check catches malformed or obvious unsafe code; container isolation is the security boundary. The worker image contains Manim and LaTeX, so builds and renders can be large. Docker was not available in the development environment, so an end-to-end container render still needs verification on a machine with Docker.
