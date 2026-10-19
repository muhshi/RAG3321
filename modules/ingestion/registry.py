"""
Publication Registry Module.
Tracks downloaded and processed BPS publications in SQLite to prevent duplicate downloads.
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger
from config.settings import settings


class PublicationRegistry:
    """Manages ingestion state and deduplication of BPS publications."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.REGISTRY_DB_PATH
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes the SQLite schema for tracking publications."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS publications (
                    publication_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    release_date TEXT,
                    category TEXT,
                    pdf_url TEXT,
                    local_file_path TEXT,
                    file_size_bytes INTEGER DEFAULT 0,
                    download_status TEXT DEFAULT 'PENDING',
                    extraction_status TEXT DEFAULT 'PENDING',
                    total_tables_extracted INTEGER DEFAULT 0,
                    total_chunks_indexed INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pub_status 
                ON publications (download_status, extraction_status)
            """)
            conn.commit()
            logger.info(f"Initialized publication registry at {self.db_path}")

    def is_already_downloaded(self, publication_id: str) -> bool:
        """Checks if publication already exists and is marked as DOWNLOADED or PROCESSED."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT local_file_path, download_status FROM publications WHERE publication_id = ?",
                (publication_id,)
            )
            row = cursor.fetchone()
            if row and row["download_status"] in ("DOWNLOADED", "PROCESSED"):
                # Also verify physical file existence
                if row["local_file_path"] and Path(row["local_file_path"]).exists():
                    return True
            return False

    def register_or_update_metadata(self, meta: Dict[str, Any]) -> None:
        """Inserts or updates metadata for a discovered publication."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO publications (
                    publication_id, title, release_date, category, pdf_url,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(publication_id) DO UPDATE SET
                    title = excluded.title,
                    release_date = excluded.release_date,
                    category = excluded.category,
                    pdf_url = excluded.pdf_url,
                    updated_at = excluded.updated_at
            """, (
                meta["publication_id"],
                meta["title"],
                meta.get("release_date"),
                meta.get("category", "Umum"),
                meta.get("pdf_url"),
                now,
                now
            ))
            conn.commit()

    def mark_download_success(self, publication_id: str, file_path: str, file_size: int) -> None:
        """Marks publication download as successful with storage path."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE publications
                SET local_file_path = ?,
                    file_size_bytes = ?,
                    download_status = 'DOWNLOADED',
                    updated_at = ?
                WHERE publication_id = ?
            """, (file_path, file_size, now, publication_id))
            conn.commit()
            logger.info(f"Marked {publication_id} as DOWNLOADED -> {file_path}")

    def mark_download_failed(self, publication_id: str) -> None:
        """Marks publication download as failed."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE publications
                SET download_status = 'FAILED',
                    updated_at = ?
                WHERE publication_id = ?
            """, (now, publication_id))
            conn.commit()

    def mark_extraction_completed(self, publication_id: str, tables_count: int, chunks_count: int) -> None:
        """Updates registry after extraction and chunk indexing is complete."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE publications
                SET extraction_status = 'PROCESSED',
                    download_status = 'PROCESSED',
                    total_tables_extracted = ?,
                    total_chunks_indexed = ?,
                    updated_at = ?
                WHERE publication_id = ?
            """, (tables_count, chunks_count, now, publication_id))
            conn.commit()

    def is_already_extracted(self, publication_id: str) -> bool:
        """Checks if publication is already marked as PROCESSED in extraction."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT extraction_status FROM publications WHERE publication_id = ?",
                (publication_id,)
            )
            row = cursor.fetchone()
            if row and row["extraction_status"] == "PROCESSED":
                return True
            return False

    def get_pending_extractions(self) -> List[Dict[str, Any]]:
        """Returns publications that are downloaded but not yet extracted."""
        items: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM publications
                WHERE download_status IN ('DOWNLOADED', 'SUCCESS') AND extraction_status != 'PROCESSED'
            """)
            items = [dict(row) for row in cursor.fetchall()]

        # Also discover any local PDFs on disk that have not been extracted yet
        registered_paths = {it.get("local_file_path") for it in items}
        for pdf in settings.DEMAK_DATA_DIR.rglob("*.pdf"):
            if pdf.stat().st_size > 1000 and str(pdf) not in registered_paths:
                db_rec = self.get_record_by_path(str(pdf))
                if db_rec:
                    if db_rec.get("extraction_status") != "PROCESSED":
                        items.append(db_rec)
                    continue

                stem = pdf.stem
                clean_title = re.sub(r"^(3321\w*|\d{4}_\d{2}_[a-f0-9]+)_?", "", stem).strip("_")
                clean_title = clean_title.replace("_", " ").strip() or stem
                year = pdf.parent.parent.name if pdf.parent.parent.name.isdigit() else "2026"
                month = pdf.parent.name if pdf.parent.name.isdigit() else "01"
                rel_date = f"{year}-{month}-01"
                
                # Slugify title
                slug = re.sub(r"[^\w\s-]", "", clean_title.lower())
                slug = re.sub(r"[\s_-]+", "_", slug).strip("_")[:60]
                pub_id = f"{rel_date}_{slug}" if slug else f"{rel_date}_{stem}"

                if not self.is_already_extracted(pub_id):
                    if not any(it.get("publication_id") == pub_id for it in items):
                        items.append({
                            "publication_id": pub_id,
                            "title": clean_title,
                            "release_date": rel_date,
                            "category": "Statistik Umum",
                            "region": "Kabupaten Demak",
                            "local_file_path": str(pdf)
                        })

        return items

    def get_record_by_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Finds publication record by local_file_path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM publications WHERE local_file_path = ?", (file_path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_records(self) -> List[Dict[str, Any]]:
        """Returns all publication records in registry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM publications ORDER BY release_date DESC")
            return [dict(row) for row in cursor.fetchall()]
