# Manim video backend

The API turns a prompt into Manim code. A separate renderer container produces the MP4. The renderer has no network access or LLM keys. Job records live in SQLite and video files live on a Docker volume. Cloudflare R2 and Qdrant are optional.

## Start

Copy `backend/.env.example` to `backend/.env`, add an LLM key, and set `API_KEY` before exposing the API. Then run:

```bash
docker compose up --build
```

The API listens on port 8000. Docker and a running Docker daemon are required. Set `OPENAI_API_KEY` for OpenAI code generation. Anthropic and Google code generation use their matching keys. The renderer timeout is 300 seconds in the Compose file; change that value alongside `RENDER_TIMEOUT_SEC` if needed.

For Gemini, a temporary per-minute 429 quota response makes the API wait 65 seconds and retry code generation up to two times. Set `LLM_RATE_LIMIT_RETRIES` and `LLM_RATE_LIMIT_WAIT_SEC` in `backend/.env` to change those bounds. A per-day quota error fails immediately because a short retry cannot clear it.

## Docker images

The Dockerfile has separate `api` and `renderer` targets, selected by Compose. The API installs only `requirements/api.txt`; it has no Manim, FFmpeg, LaTeX, or compiler toolchain. The renderer installs `requirements/renderer.txt` and the Cairo/Pango runtime libraries, fonts, FFmpeg, and LaTeX. It does not install web-server, model-provider, or cloud-storage packages. `requirements/common.txt` contains shared configuration dependencies. The root `requirements.txt` still installs both sets for local development.

Both targets use multi-stage builds. Compilers and headers stay in the renderer builder; the final image installs prebuilt wheels offline through temporary BuildKit mounts. Wheels and pip download caches are not copied into final images. Dependency manifests are copied before source files, so edits to code or prompts reuse the dependency layers. The allowlist in `backend/.dockerignore` excludes keys, `.env` files, tests, caches, local environments, and rendered videos from the build context. Add any new runtime subpackages to this allowlist when introducing them.

Both containers run as UID/GID 1000, use read-only roots and writable mounted job directories, drop Linux capabilities, and use an init process to reap child processes. The API has an HTTP health check and its SQLite volume is mounted only there. The renderer retains its disabled network, separate environment, and resource limits. Keep persistent job/state volumes when updating images. Do not use `docker compose down -v` to upgrade an existing deployment.

Build without restarting running services:

```bash
docker compose build api renderer
```

Test the built images without LLM keys or existing job volumes:

```bash
python backend/tests/docker_smoke.py
```

The smoke test uses disposable containers and anonymous volumes with the same read-only, non-root, no-network restrictions. It checks API health, provider imports, prompt files, SQLite writes, and a worker render with Text, arrows, and MathTex. BuildKit is required for cache and bind mounts. The default base is Python 3.11 on Debian Bookworm, pinned to a verified image digest; both builder and runtime use the same `PYTHON_IMAGE` argument. Refresh that digest deliberately for security updates, or supply a reviewed replacement with `--build-arg PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:...`. Direct dependencies keep their existing version constraints; transitive dependencies are not fully locked.

The renderer remains larger than the API because formula support requires LaTeX. Removing LaTeX would change the supported generated scenes. The first build downloads dependencies; later cached builds are faster. Keeping a builder cache uses host disk space even though those files are absent from the final images. Measure actual image sizes with `docker image ls`; layer sharing means their displayed sizes are not simply additive disk usage.

Measured on the local Linux/amd64 Docker build on October 9, 2026, using Docker's reported image size:

| Image | Before | After |
| --- | --- | --- |
| API | 3.166 GB | 0.594 GB |
| Renderer with LaTeX | 3.166 GB | 2.254 GB |

Sizes are decimal GB and can differ with platform or dependency updates. Both container smoke checks passed, including an actual H.264 render with MathTex. Provider modules were imported, but no live model calls were made. The existing Gemini dependency emitted a deprecation warning; its SDK migration is separate from these Docker changes.

## Generate and retrieve

On Windows, use `scripts/Generate-Video.ps1` from the repository root to submit,
poll and download as one operation:

```powershell
.\scripts\Generate-Video.ps1 -Prompt $prompt -Headers $headers -Open
```

It stops on a failed job and only downloads a succeeded job. A timeout means the
job is still pending; it is not reported after a known failure. Videos go into the
repository's `videos` folder even if your current directory is elsewhere. Pass
`-OutputDirectory` to choose another folder. Omit `-Open` to just save the file.

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" -H "x-api-key: YOUR_KEY" \
  -d '{"prompt":"Animate the Pythagorean theorem with squares on each side","quality":"m"}'
```

The response contains a `job_id`. Poll `GET /api/jobs/{job_id}` until the status is `succeeded` or `failed`, then fetch `GET /api/videos/{job_id}.mp4` with the API key. The video route returns the local file or redirects to a short lived R2 signed URL. `l`, `m`, and `h` select render quality. `k` requires `ALLOW_HIGH_QUALITY=true`.

Jobs that were queued or running when the API stopped resume after it starts again. Failed jobs retain their error in SQLite. The renderer writes results to the shared jobs volume, while SQLite is mounted only in the API container.

## Generation prompt and video quality

New storyboard proposals first have well-formed region centers shifted inside the 12% safe frame when needed. This preserves region sizes and cannot rescue oversized or malformed regions. Obstructed arrows get a bounded search for free ports and routes around the proposed regions, preserving their source, target and message. Impossible routes remain invalid. The backend still checks all collisions and route errors afterward. Saved validated storyboards are checked as stored rather than adjusted on resume.

New API generations use three model stages, with the same provider and model throughout:

1. `app/prompts/lesson_plan_system.txt` produces a structured lesson plan with its audience, objective, scope, facts, assumptions, example, ordered steps, misconceptions, limitations, and takeaway.
2. `app/prompts/storyboard_system.txt` turns the lesson into exact on-screen words, visible object regions, connector routes, transitions, and reading holds. The backend checks the JSON schema, step coverage and order, final takeaway, proposed geometry, and timing before proceeding.
3. `app/prompts/manim_system.txt` generates Python from the validated plan and storyboard. The existing AST validator checks that code before the render worker receives it.

The generator reads prompts for each new generation. It replaces only `{scene_name}` in the code prompt, so Python examples and formulas can keep literal braces. Paths are relative to the generator module, independent of the working directory. A missing file, or an empty or placeholder-free code prompt, fails generation before contacting the model. The Dockerfile copies all prompts with `app`; rebuild the API image after editing them. Existing saved scenes and reused videos keep their original code.

Before validating a new storyboard, the backend tries a bounded search for free space beside each arrow whose message label crowds another region or route. It moves only the label, preserving its text and dimensions, the diagram and routes. Fully valid label arrangements keep their positions. Crowded labels are assigned jointly, with a bounded search for nearby free positions so one misplaced label does not block the next. It also normalizes pacing: small actions get bounded animation time, intermediate beats within a lesson phase get no idle hold, and completed phases get a short reading pause. Overlong model allocations are reduced as well as short ones raised. Completed phases can use the calculated reading time when it fits the total budget; dense text must simplify when the whole lesson cannot fit. All geometry and timing checks still run afterward. If no safe placement or timing budget exists, the model must repair or simplify the proposal. Collision errors include the conflicting region bounds.

Each planning stage gets one repair attempt after a schema or storyboard validation error. Set `PLANNING_REPAIR_ATTEMPTS` to 0-2 to change this bound. Invalid plans fail the job before rendering; they do not silently fall back to direct code generation. Existing Gemini quota retries apply to every stage. Three model calls, plus any repairs or quota retries, cost more and take longer than the original single call.

Validated stages are saved as `lesson_plan.json` and `storyboard.json` in the job directory and in SQLite. `GET /api/jobs/{job_id}` exposes `lesson_plan`, `storyboard`, and `generation_stage`, which advances through `lesson_plan`, `storyboard`, `coding`, `rendering`, and `completed`. A failed job retains the stage and any completed plan for inspection. Jobs interrupted before code generation reuse their saved validated stages on restart. Older jobs can have null planning fields. Plans advance automatically; there is no manual plan-approval or editing UI yet.

The prompt asks for one accurate, scoped lesson across domains, with ordered explanatory beats, measured text and box layouts, clear arrow routes, readable font sizes, explicit animation durations, reading pauses, and a stable takeaway. It specifies a centered content rectangle with padding on all four sides: at least 12% of the frame width on each horizontal side and 12% of the frame height on each vertical side, with a minimum of 0.6 scene units. Titles and captions share this safe rectangle with the diagram. Connectors need clear corridors around boxes and text, separate lanes for return messages, and space between arrowheads, borders, and message labels. Crowded messages should appear sequentially. These margins help landscape playback on different screens; a portrait composition still requires a separate layout. The prompt retains the 5-25 second limit. Dense subjects should become a labeled overview or excerpt, rather than a rushed complete lesson.

Storyboard coordinates are fractions of the full frame, centered at the origin. Proposed object, title, caption, and message regions must fit inside the 12% safe margins. The validator rejects crowded regions, unknown arrow endpoints, arrows detached from their actors, connector segments through regions, crossings between connectors, missing lesson steps, insufficient reading holds, and planned durations outside 5-25 seconds. Clearance calculations use the default 16:9 Manim frame. Object regions are conservative rectangles, including labels; this can reject some visually acceptable curved or circular layouts.

These checks validate a proposal, not the rendered video. They do not measure actual font glyphs, inspect intermediate animation frames, confirm that generated code follows every storyboard coordinate, or verify factual claims. The AST validator checks code structure and obvious unsafe operations. There is no rendered-frame review or render-repair loop yet. A successful render still needs review before treating it as a correct lesson.

Pacing follows conceptual phases, identified by lesson_step. Small reveals and fades take about 0.4-0.7 seconds; meaningful arrows take 0.8-1.1 seconds. Beats sharing a lesson_step flow together with zero hold between small actions. The last beat of each phase normally gets a 1.5-3.5 second reading pause; the final frame normally gets 2.5-4 seconds. These are preferred ranges, not hard density limits. A completed phase may need a longer calculated reading hold, within the 25-second total and per-beat schema limits. Reading allowances accumulate newly introduced words across the phase and credit part of the time spent on its actions. Text must shorten when the complete timeline cannot fit, rather than failing solely because a phase needs more than the preferred pause. The backend trims overlong proposed durations and rejects idle holds inside a phase. Prompts ask for captions to appear alongside the actions, related status changes to share a play, and the title to use the first beat's budget. These changes apply to newly generated videos. Generated Python is still responsible for following the storyboard timing; rendered timing is not automatically verified.

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

This is a single-host setup with one sequential renderer. The API handles up to two generation jobs at a time. The renderer has no network, uses an unprivileged user, and has memory, CPU, and process limits, but it can access the shared jobs volume. An AST check catches malformed or obvious unsafe code; container isolation is the security boundary. The worker image contains Manim and LaTeX, so builds and renders can be large. The Docker smoke test covers a controlled render; generated videos still need visual and factual review.
