# Forma

Forma turns a written request into a short explanatory animation. The landing page introduces the product with a circle-to-wave motion study. The studio at `/studio` lets you create, preview, and download a video, with optional settings and lesson details collapsed. The shared dark theme and brand guidelines are recorded in [DESIGN.md](DESIGN.md).

The backend accepts a prompt, asks an LLM for a Manim scene, and queues it for an isolated renderer container. It stores job status in SQLite and the MP4 on a Docker volume. Cloudflare R2 storage and Qdrant video suggestions can be enabled separately. A user must opt in before their video is indexed for reuse, and another user chooses whether a suggested video fits their request.

See [backend/README.md](backend/README.md) for setup, API requests, storage, reuse, and current limits.

## Run the website locally

1. Configure and start the backend using [backend/README.md](backend/README.md).
2. Copy the root `.env.example` to `.env.local`. Set `MANIM_API_URL` to the API address and `MANIM_API_KEY` to the backend's `API_KEY`, if set. These are server settings. Do not prefix keys with `NEXT_PUBLIC_`. Restart Next.js after changing them.
3. Install dependencies with `pnpm install`, then run `pnpm dev --hostname 127.0.0.1`.
4. Open `http://127.0.0.1:3000`, then choose Open studio. Existing `/?job=...` links redirect to `/studio?job=...`.

The browser uses `/api/backend/...` on the same origin. Next.js forwards only the supported API routes and adds the backend key on the server, so no CORS configuration or browser key entry is needed. MP4s stream through this route with byte-range support for seeking. R2 redirects are fetched without the backend key.

Enter one focused request and select 480p, 720p, or 1080p. The form stays locked while that job is active. The page URL records its job ID so a refresh resumes status checks. Temporary status errors retry automatically; failed jobs show their error and unlock the form. The finished video includes its original request, plan, and storyboard when available. Older jobs without planning data still work. Review the rendered explanation before sharing.

Similar-video search is an explicit choice before generating. Read the original request and choose a preview; a match never silently replaces a new generation. Search requires the backend's optional Qdrant configuration. Sharing for reuse starts unchecked and requires the same configuration. Search being unavailable does not prevent an unshared generation.

This is a local, single-operator interface. The server key authenticates Next.js to the backend; it does not authenticate visitors to the website. Add visitor authentication, access rules, and rate limits before exposing the frontend publicly.

## Frontend checks

```bash
pnpm lint
pnpm test
pnpm build
```

The proxy tests use Node's built-in test runner and require Node 22.18 or newer. They cover route restrictions, cross-origin submissions, server credentials, backend errors, streaming ranges, and storage redirects.

For browser checks without model calls, run `node tests/fixture-backend.mjs`, then start a separate frontend with `MANIM_API_URL=http://127.0.0.1:8101`, `MANIM_API_KEY=fixture-key`, and a separate port such as `pnpm dev --port 3100 --hostname 127.0.0.1`. Set those variables only for that test process. The fixture simulates generation stages and plays the first local MP4 in `videos`, if present. Include `fixture-failure` in a prompt to exercise failure handling. Its lesson plans and video are test data, not generated results. Stop the fixture after checking the UI.
