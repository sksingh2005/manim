# Forma

Forma turns a written idea into a short animated explainer video. Describe what you want to teach, and Forma plans the lesson, builds a storyboard, and renders an animation you can preview and download.

It is built for educators, students, and creators who want to explain concepts visually without writing animation code.

## What it does

- Creates short explanatory animations from a text prompt.
- Plans the explanation and scene sequence before generating animation code.
- Shows generation progress and lets you preview and download the finished MP4.
- Supports 480p, 720p, and 1080p output in the studio.
- Saves job progress so you can reopen a video using its page URL.
- Optionally finds similar shared videos with Qdrant and stores finished videos in Cloudflare R2.

For example, ask: "Explain the Pythagorean theorem using a 3-4-5 triangle and squares on each side."

## How it works

1. Enter a request in the studio.
2. A language model creates a lesson plan and storyboard.
3. The backend validates the plan and generates Python animation code for Manim.
4. A separate renderer container produces the video.
5. Preview the result in the studio or download it as an MP4.

The frontend uses Next.js and React. The backend uses FastAPI, SQLite, and Manim. Videos are designed to run for about 5 to 25 seconds, so focused requests work best. Review generated explanations for accuracy before sharing them.

## Local setup

### Requirements

- Node.js 22.18 or newer.
- pnpm. The project specifies version 12.3.4 in `package.json`.
- Docker with Docker Compose and a running Docker engine.
- An API key for a supported language model provider: OpenAI, Anthropic, or Google Gemini.

Docker installs the backend's Python, Manim, FFmpeg, and LaTeX dependencies. You do not need to install those separately on your computer.

### 1. Clone the project

```bash
git clone https://github.com/sksingh2005/manim.git
cd manim
```

### 2. Configure the backend

Copy `backend/.env.example` to `backend/.env`. For the default OpenAI configuration, fill in:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your-openai-api-key
API_KEY=your-local-backend-key
```

`API_KEY` is a key you choose for access to the backend. It is separate from your model provider's API key. Leave the other settings at their defaults to start. For another provider, set `LLM_PROVIDER`, `LLM_MODEL`, and its matching API key.

From the repository root, start the backend and renderer:

```bash
docker compose up --build
```

The backend runs at `http://127.0.0.1:8000`. Keep this terminal running. The first build can take several minutes because the renderer includes the animation and formula-rendering tools.

### 3. Configure and start the frontend

Copy `.env.example` to `.env.local` in the repository root:

```dotenv
MANIM_API_URL=http://127.0.0.1:8000
MANIM_API_KEY=your-local-backend-key
```

Use the same value for `MANIM_API_KEY` as the backend's `API_KEY`. These settings stay on the server. Keep real keys out of Git and restart the frontend after changing them.

In a second terminal, run:

```bash
pnpm install
pnpm dev --hostname 127.0.0.1
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000) and choose **Open studio**. Enter a focused request, adjust **Options** if needed, and use the send button to generate a video.

### 4. Stop the project

Press `Ctrl+C` in the frontend terminal. Stop the backend containers with:

```bash
docker compose down
```

Job records and rendered videos remain in Docker volumes for the next run.

## Optional services

The basic setup works without cloud storage or video search.

- **Cloudflare R2:** Set the four `R2_*` values in `backend/.env` to upload completed videos.
- **Similar-video search:** Configure `QDRANT_URL` and a Gemini API key, then start Compose with the `reuse` profile. Sharing is opt-in in the studio.

See the [backend guide](backend/README.md) for provider configuration, API usage, optional services, and rendering limits.

## Development checks

```bash
pnpm lint
pnpm test
pnpm build
```

The frontend tests cover the backend proxy and use Node's built-in test runner. They do not call a model or generate a video.

The current setup is intended for local use. Add visitor authentication and rate limits before making the website public.
