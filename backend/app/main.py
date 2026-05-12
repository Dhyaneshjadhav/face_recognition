"""
FastAPI application — Face Detection Video Processing API.

Endpoints
---------
POST /api/upload        – Upload a video for face-detection processing
GET  /api/video/{id}    – Stream / download the processed video
GET  /api/roi/{id}      – Retrieve per-frame ROI (bounding-box) data
GET  /api/videos        – List all uploaded videos
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .database import create_tables, database, roi_data, videos
from .face_detector import process_video

# ── Configuration ─────────────────────────────────────────────────────
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data/uploads")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "/data/processed")
DATABASE_DIR = os.environ.get("DATABASE_DIR", "/data")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(DATABASE_DIR, exist_ok=True)
    create_tables()
    await database.connect()
    logger.info("Database connected, tables ready")
    yield
    # Shutdown
    await database.disconnect()


# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Face Detection Video API",
    description="Upload a video, detect faces, store ROI data, and retrieve the annotated feed.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 1. Upload endpoint ───────────────────────────────────────────────
@app.post("/api/upload", status_code=201)
async def upload_video(file: UploadFile = File(...)):
    """
    Accept a video file, run face detection on every frame,
    store ROI data in SQLite, and save the annotated video.
    """
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are accepted")

    # Save uploaded file
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    input_path = os.path.join(UPLOAD_DIR, unique_name)

    content = await file.read()
    with open(input_path, "wb") as f:
        f.write(content)

    logger.info("Saved upload: %s (%d bytes)", input_path, len(content))

    # Create DB record
    query = videos.insert().values(
        filename=unique_name,
        original_filename=file.filename or "unknown",
        status="processing",
    )
    video_id = await database.execute(query)

    try:
        # Process video
        output_name = f"processed_{unique_name}"
        output_path = os.path.join(PROCESSED_DIR, output_name)

        roi_list, video_meta = process_video(input_path, output_path)

        # Store ROI data
        for roi in roi_list:
            await database.execute(
                roi_data.insert().values(video_id=video_id, **roi)
            )

        # Update video record
        await database.execute(
            videos.update()
            .where(videos.c.id == video_id)
            .values(
                processed_filename=output_name,
                status="done",
                total_frames=video_meta["total_frames"],
                fps=video_meta["fps"],
                width=video_meta["width"],
                height=video_meta["height"],
            )
        )

        face_count = sum(1 for r in roi_list if r.get("face_detected"))

        return {
            "video_id": video_id,
            "status": "done",
            "total_frames": video_meta["total_frames"],
            "frames_with_face": face_count,
            "fps": video_meta["fps"],
            "resolution": f"{video_meta['width']}x{video_meta['height']}",
        }

    except Exception as exc:
        logger.exception("Processing failed for video %d", video_id)
        await database.execute(
            videos.update()
            .where(videos.c.id == video_id)
            .values(status="error")
        )
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")


# ── 2. Serve processed video ─────────────────────────────────────────
@app.get("/api/video/{video_id}")
async def serve_video(video_id: int):
    """Stream the processed (annotated) video file."""
    row = await database.fetch_one(
        videos.select().where(videos.c.id == video_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if row["status"] != "done":
        raise HTTPException(status_code=202, detail=f"Video is still {row['status']}")

    path = os.path.join(PROCESSED_DIR, row["processed_filename"])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Processed file missing")

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"processed_{row['original_filename']}",
    )


# ── 3. Serve ROI data ────────────────────────────────────────────────
@app.get("/api/roi/{video_id}")
async def serve_roi(video_id: int):
    """Return all per-frame ROI (bounding-box) data for a video."""
    row = await database.fetch_one(
        videos.select().where(videos.c.id == video_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Video not found")

    rows = await database.fetch_all(
        roi_data.select()
        .where(roi_data.c.video_id == video_id)
        .order_by(roi_data.c.frame_number)
    )

    return {
        "video_id": video_id,
        "original_filename": row["original_filename"],
        "status": row["status"],
        "total_frames": row["total_frames"],
        "fps": row["fps"],
        "resolution": f"{row['width']}x{row['height']}" if row["width"] else None,
        "roi_data": [
            {
                "frame_number": r["frame_number"],
                "face_detected": bool(r["face_detected"]),
                "bounding_box": {
                    "x_min": r["x_min"],
                    "y_min": r["y_min"],
                    "x_max": r["x_max"],
                    "y_max": r["y_max"],
                    "width": r["width"],
                    "height": r["height"],
                } if r["face_detected"] else None,
                "confidence": r["confidence"],
            }
            for r in rows
        ],
    }


# ── 4. List all videos ───────────────────────────────────────────────
@app.get("/api/videos")
async def list_videos():
    """List all uploaded videos and their processing status."""
    rows = await database.fetch_all(
        videos.select().order_by(videos.c.id.desc())
    )
    return [
        {
            "video_id": r["id"],
            "original_filename": r["original_filename"],
            "status": r["status"],
            "total_frames": r["total_frames"],
            "fps": r["fps"],
            "resolution": f"{r['width']}x{r['height']}" if r["width"] else None,
            "created_at": str(r["created_at"]) if r["created_at"] else None,
        }
        for r in rows
    ]
