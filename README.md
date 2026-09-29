# Manim video

This project is building a website that turns a written request into a Manim animation. The backend is the current focus. The Next.js frontend is still the starter app.

The backend accepts a prompt, asks an LLM for a Manim scene, and queues it for an isolated renderer container. It stores job status in SQLite and the MP4 on a Docker volume. Cloudflare R2 storage and Qdrant video suggestions can be enabled separately. A user must opt in before their video is indexed for reuse, and another user chooses whether a suggested video fits their request.

See [backend/README.md](backend/README.md) for setup, API requests, storage, reuse, and current limits.
