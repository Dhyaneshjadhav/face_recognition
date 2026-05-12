"""
Database module for storing ROI (Region of Interest) data from face detection.

Uses SQLite — an embedded relational database that is ideal for structured
bounding-box data (frame_number, x, y, width, height, confidence) where
each row maps 1-to-1 to a video frame.  No external database server is
required, which keeps the container footprint minimal.
"""

import os
import sqlalchemy
from databases import Database

DATABASE_DIR = os.environ.get("DATABASE_DIR", "/data")
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_DIR}/roi_data.db"

# async database driver
database = Database(DATABASE_URL)

# SQLAlchemy metadata for schema definition
metadata = sqlalchemy.MetaData()

# ── videos table ──────────────────────────────────────────────────────
videos = sqlalchemy.Table(
    "videos",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("filename", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("original_filename", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("processed_filename", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("status", sqlalchemy.String, default="pending"),  # pending | processing | done | error
    sqlalchemy.Column("total_frames", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("fps", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("width", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("height", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=sqlalchemy.func.now()),
)

# ── roi_data table ────────────────────────────────────────────────────
roi_data = sqlalchemy.Table(
    "roi_data",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("video_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("videos.id"), nullable=False),
    sqlalchemy.Column("frame_number", sqlalchemy.Integer, nullable=False),
    sqlalchemy.Column("face_detected", sqlalchemy.Boolean, default=False),
    sqlalchemy.Column("x_min", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("y_min", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("x_max", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("y_max", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("width", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("height", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("confidence", sqlalchemy.Float, nullable=True),
)


def create_tables() -> None:
    """Create all tables (sync helper used at startup)."""
    engine = sqlalchemy.create_engine(
        DATABASE_URL.replace("+aiosqlite", ""),
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    engine.dispose()
