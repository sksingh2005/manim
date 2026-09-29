# Manim CE worker: Python 3.11 + ffmpeg + cairo/pango + minimal LaTeX
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for Manim CE (cairo, pango, ffmpeg) + tiny TeX for Tex mobjects.
# texlive packages are heavy; keep minimal so Text works and simple Tex works.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    build-essential \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    dvisvgm \
    git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

# Both services use the same unprivileged UID for the shared render volume.
RUN useradd -m renderer && mkdir -p /tmp/manim-jobs /tmp/manim-state && chown -R renderer:renderer /app /tmp/manim-jobs /tmp/manim-state
USER renderer

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
