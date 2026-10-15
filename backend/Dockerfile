# syntax=docker/dockerfile:1
# Keep build and runtime stages on the same Python ABI and Debian release.
# Production can override this with a reviewed image digest via --build-arg.
ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89

FROM ${PYTHON_IMAGE} AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache
WORKDIR /app
# Fixed IDs preserve write access to the volume shared by API and renderer.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp app \
    && mkdir -p /tmp/manim-jobs /tmp/manim-state \
    && chown app:app /tmp/manim-jobs /tmp/manim-state

FROM ${PYTHON_IMAGE} AS api-builder
WORKDIR /build
COPY requirements/common.txt requirements/api.txt ./requirements/
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --wheel-dir=/wheels -r requirements/api.txt

FROM ${PYTHON_IMAGE} AS renderer-builder
WORKDIR /build
# Headers and compilers are required to build pycairo/ManimPango, not to render.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libcairo2-dev \
        libpango1.0-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/common.txt requirements/renderer.txt ./requirements/
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --wheel-dir=/wheels -r requirements/renderer.txt

FROM runtime-base AS renderer
# Runtime libraries only. Retain LaTeX support for generated MathTex formulas.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dvisvgm \
        ffmpeg \
        fontconfig \
        fonts-dejavu-core \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        texlive-fonts-recommended \
        texlive-latex-base \
        texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*
# Read wheels from the builder without retaining a wheel archive layer.
RUN --mount=type=bind,from=renderer-builder,source=/wheels,target=/wheels \
    --mount=type=bind,from=renderer-builder,source=/build/requirements,target=/requirements \
    python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /requirements/renderer.txt
COPY app/__init__.py app/config.py app/sandbox.py app/worker.py ./app/
USER 1000:1000
CMD ["python", "-m", "app.worker"]

# Last stage is the lightweight API so a plain `docker build` has a safe default.
FROM runtime-base AS api
RUN --mount=type=bind,from=api-builder,source=/wheels,target=/wheels \
    --mount=type=bind,from=api-builder,source=/build/requirements,target=/requirements \
    python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /requirements/api.txt
COPY app ./app
USER 1000:1000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
