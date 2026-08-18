"""
সিম্পল SQLite ডেটাবেস লেয়ার। শুরুতে MVP-র জন্য SQLite যথেষ্ট —
পরে চাইলে Postgres/pgvector-এ মাইগ্রেট করা যাবে।
"""
import sqlite3
import json
import time
import uuid
from contextlib import contextmanager

DB_PATH = "shikhi.db"


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                link TEXT NOT NULL,
                professional TEXT NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'processing',
                transcript TEXT,
                error TEXT,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                FOREIGN KEY(video_id) REFERENCES videos(id)
            )
        """)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_video(link: str, professional: str, topic: str) -> dict:
    video_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO videos (id, link, professional, topic, status, created_at) VALUES (?, ?, ?, ?, 'processing', ?)",
            (video_id, link, professional, topic, time.time()),
        )
        conn.commit()
    return {"id": video_id, "link": link, "professional": professional, "topic": topic, "status": "processing"}


def update_video_status(video_id: str, status: str, transcript: str = None, error: str = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE videos SET status = ?, transcript = COALESCE(?, transcript), error = ? WHERE id = ?",
            (status, transcript, error, video_id),
        )
        conn.commit()


def list_videos() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, link, professional, topic, status, error FROM videos ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]


def get_video(video_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None


def add_chunks(video_id: str, chunks: list[str], embeddings: list[list[float]]):
    with get_conn() as conn:
        for text, emb in zip(chunks, embeddings):
            conn.execute(
                "INSERT INTO chunks (id, video_id, text, embedding) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), video_id, text, json.dumps(emb)),
            )
        conn.commit()


def get_all_chunks_with_meta() -> list[dict]:
    """সব chunk + প্যারেন্ট ভিডিওর metadata (professional, topic) একসাথে ফেরত দেয়।"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT c.text, c.embedding, v.professional, v.topic, v.link
            FROM chunks c JOIN videos v ON c.video_id = v.id
            WHERE v.status = 'ready'
        """).fetchall()
        return [dict(r) for r in rows]
