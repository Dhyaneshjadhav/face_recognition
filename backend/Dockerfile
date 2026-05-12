# ── Backend Dockerfile ───────────────────────────────────────────────
FROM python:3.11-slim

# opencv-python-headless only needs these minimal libs (already present in slim)
# No ffmpeg, no libgl1, no libglib2.0-0 required.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Data volume for SQLite + videos
RUN mkdir -p /data/uploads /data/processed

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
