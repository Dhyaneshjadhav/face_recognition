"""
Face detection and ROI drawing service.

Uses **OpenCV Haar Cascade** for face detection and **Pillow** for
drawing bounding boxes.  Video I/O is handled entirely by OpenCV —
no ffmpeg system package or imageio-ffmpeg needed.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Haar Cascade face detector (singleton) ────────────────────────────
_cascade: Optional[cv2.CascadeClassifier] = None


def _get_cascade() -> cv2.CascadeClassifier:
    global _cascade
    if _cascade is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _cascade = cv2.CascadeClassifier(cascade_path)
        if _cascade.empty():
            raise RuntimeError(f"Failed to load Haar cascade from: {cascade_path}")
    return _cascade


# ── Public helpers ────────────────────────────────────────────────────

def detect_face(frame_rgb: np.ndarray) -> Optional[dict]:
    """
    Detect the most prominent face in an RGB frame.

    Returns a dict with keys:
        x_min, y_min, x_max, y_max   – pixel coordinates of the AABB
        width, height                 – box dimensions
        confidence                    – detection score (neighbour count, normalised)
    or None if no face is found.
    """
    cascade = _get_cascade()
    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)

    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )

    if len(faces) == 0:
        return None

    # Take the largest face by area (assignment: assume 1 face)
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

    return {
        "x_min": int(x),
        "y_min": int(y),
        "x_max": int(x + w),
        "y_max": int(y + h),
        "width": int(w),
        "height": int(h),
        "confidence": 1.0,   # Haar cascade returns no score; use 1.0 as placeholder
    }


def draw_roi(frame_rgb: np.ndarray, roi: dict) -> np.ndarray:
    """
    Draw an axis-aligned bounding-box rectangle on *frame_rgb* using Pillow.

    Returns a new RGB numpy array with the box rendered.
    """
    img = Image.fromarray(frame_rgb)
    draw = ImageDraw.Draw(img)

    x_min, y_min = roi["x_min"], roi["y_min"]
    x_max, y_max = roi["x_max"], roi["y_max"]

    # Draw a 3-pixel-wide bright-green rectangle
    for offset in range(3):
        draw.rectangle(
            [x_min - offset, y_min - offset, x_max + offset, y_max + offset],
            outline=(0, 255, 100),
        )

    # Draw confidence label
    confidence = roi.get("confidence", 1.0)
    label = f"Face {confidence:.0%}"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Label background
    text_bbox = draw.textbbox((x_min, y_min - 22), label, font=font)
    draw.rectangle(text_bbox, fill=(0, 255, 100))
    draw.text((x_min, y_min - 22), label, fill=(0, 0, 0), font=font)

    return np.array(img)


# ── Video processing pipeline ────────────────────────────────────────

def process_video(
    input_path: str,
    output_path: str,
) -> Tuple[List[dict], dict]:
    """
    Read *input_path*, detect faces frame-by-frame, draw ROIs,
    and write the annotated video to *output_path*.

    Returns:
        roi_list   – per-frame ROI dicts (empty dict when no face detected)
        video_meta – fps, width, height, total_frames
    """
    logger.info("Reading video: %s", input_path)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    video_meta = {"fps": fps, "width": w, "height": h, "total_frames": total_frames}
    logger.info("Video: %dx%d, %.1f fps, %d frames", w, h, fps, total_frames)

    # Use mp4v codec — works universally with opencv-python-headless
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    roi_list: List[dict] = []
    idx = 0

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        # OpenCV reads BGR — convert to RGB for detection/drawing
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        roi = detect_face(frame_rgb)

        if roi is not None:
            annotated_rgb = draw_roi(frame_rgb, roi)
            roi_list.append({"frame_number": idx, "face_detected": True, **roi})
        else:
            annotated_rgb = frame_rgb
            roi_list.append({"frame_number": idx, "face_detected": False})

        # Convert back to BGR for VideoWriter
        annotated_bgr = cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)
        writer.write(annotated_bgr)

        idx += 1
        if idx % 50 == 0:
            logger.info("Processed %d / %d frames", idx, total_frames)

    cap.release()
    writer.release()

    # Patch total_frames if CAP_PROP_FRAME_COUNT was wrong (common with some codecs)
    video_meta["total_frames"] = idx

    logger.info("Processing complete — %d frames written to %s", idx, output_path)
    return roi_list, video_meta
