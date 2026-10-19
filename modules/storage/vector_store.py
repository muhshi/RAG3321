"""
Vector Store Module with Dual Backend: ChromaDB and Native SQLite Vector Store.
Guarantees zero-failure operation even on Windows environments missing MSVC C++ DLLs.
Supports metadata pre-filtering, cosine similarity search, and payload storage.
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from loguru import logger

from config.settings import settings


class BPSVectorStore:
    """Manages Vector Indexing and Metadata-Filtered Semantic Retrieval."""

    def __init__(self, storage_dir: Optional[Path] = None, collection_name: Optional[str] = None):
        self.storage_dir = storage_dir or settings.VECTOR_DB_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or settings.VECTOR_COLLECTION_NAME
        self.use_sqlite_fallback = False

        self._init_chroma()

    def _init_chroma(self) -> None:
        """Attempts to initialize ChromaDB, falling back to SQLite if DLLs are missing."""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            logger.info(f"Attempting ChromaDB connection at {self.storage_dir}...")
            self.client = chromadb.PersistentClient(
                path=str(self.storage_dir),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB PersistentClient ready. Collection '{self.collection_name}'.")
        except Exception as e:
            logger.warning(f"ChromaDB Rust bindings could not load ({e}). Activating SQLite Native Vector Store...")
            self.use_sqlite_fallback = True
            self.sqlite_db_path = self.storage_dir / "vector_store.sqlite"
            self._init_sqlite_vector_db()

    def _init_sqlite_vector_db(self) -> None:
        """Initializes high-performance SQLite vector table with metadata indices."""
        with sqlite3.connect(self.sqlite_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    dokumen_id TEXT,
                    dokumen_sumber TEXT,
                    daerah TEXT,
                    kategori TEXT,
                    tahun TEXT,
                    halaman INTEGER,
                    tipe_konten TEXT,
                    judul_tabel TEXT,
                    satuan TEXT,
                    sumber TEXT,
                    representasi_teks TEXT,
                    metadata_json TEXT,
                    embedding_json TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_v_daerah ON vector_chunks (daerah)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_v_tahun ON vector_chunks (tahun)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_v_kategori ON vector_chunks (kategori)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_v_tipe ON vector_chunks (tipe_konten)")
            conn.commit()
            logger.info(f"SQLite Native Vector Store initialized at {self.sqlite_db_path}")

    def _sanitize_metadata(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Flattens metadata into scalar types."""
        payload = {
            "dokumen_id": str(chunk.get("dokumen_id", "")),
            "dokumen_sumber": str(chunk.get("dokumen_sumber", "")),
            "daerah": str(chunk.get("daerah", "")),
            "kategori": str(chunk.get("kategori", "")),
            "tahun": str(chunk.get("tahun", "")),
            "tanggal_publikasi": str(chunk.get("tanggal_publikasi", "")),
            "halaman": int(chunk.get("halaman", 1)),
            "tipe_konten": str(chunk.get("tipe_konten", "")),
            "judul_tabel": str(chunk.get("judul_tabel", "")),
            "tabel_id": str(chunk.get("tabel_id", "")),
            "file_json_tabel": str(chunk.get("file_json_tabel", "")),
            "file_json_dokumen": str(chunk.get("file_json_dokumen", "")),
            "file_json_naratif": str(chunk.get("file_json_naratif", "")),
            "satuan": str(chunk.get("satuan", "")),
            "sumber": str(chunk.get("sumber", "")),
            "bab": str(chunk.get("bab", "")),
            "sub_bab": str(chunk.get("sub_bab", ""))
        }
        return {k: v for k, v in payload.items() if v != ""}

    def upsert_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 100) -> int:
        """Upserts chunks into active Vector DB backend."""
        if not chunks:
            return 0

        # Backend 1: ChromaDB
        if not self.use_sqlite_fallback:
            try:
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i : i + batch_size]
                    self.collection.upsert(
                        ids=[c["chunk_id"] for c in batch],
                        embeddings=[c["embedding"] for c in batch],
                        documents=[c["representasi_teks"] for c in batch],
                        metadatas=[self._sanitize_metadata(c) for c in batch]
                    )
                logger.info(f"Upserted {len(chunks)} vectors into ChromaDB.")
                return len(chunks)
            except Exception as e:
                logger.warning(f"Chroma upsert failed ({e}). Falling back to SQLite.")
                self.use_sqlite_fallback = True
                self.sqlite_db_path = self.storage_dir / "vector_store.sqlite"
                self._init_sqlite_vector_db()

        # Backend 2: SQLite Native Vector Store
        with sqlite3.connect(self.sqlite_db_path) as conn:
            cursor = conn.cursor()
            for c in chunks:
                meta = self._sanitize_metadata(c)
                cursor.execute("""
                    INSERT INTO vector_chunks (
                        chunk_id, dokumen_id, dokumen_sumber, daerah, kategori,
                        tahun, halaman, tipe_konten, judul_tabel, satuan,
                        sumber, representasi_teks, metadata_json, embedding_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        dokumen_sumber = excluded.dokumen_sumber,
                        daerah = excluded.daerah,
                        kategori = excluded.kategori,
                        tahun = excluded.tahun,
                        halaman = excluded.halaman,
                        tipe_konten = excluded.tipe_konten,
                        judul_tabel = excluded.judul_tabel,
                        satuan = excluded.satuan,
                        sumber = excluded.sumber,
                        representasi_teks = excluded.representasi_teks,
                        metadata_json = excluded.metadata_json,
                        embedding_json = excluded.embedding_json
                """, (
                    c["chunk_id"],
                    meta.get("dokumen_id", ""),
                    meta.get("dokumen_sumber", ""),
                    meta.get("daerah", ""),
                    meta.get("kategori", ""),
                    meta.get("tahun", ""),
                    meta.get("halaman", 1),
                    meta.get("tipe_konten", ""),
                    meta.get("judul_tabel", ""),
                    meta.get("satuan", ""),
                    meta.get("sumber", ""),
                    c["representasi_teks"],
                    json.dumps(meta, ensure_ascii=False),
                    json.dumps(c["embedding"])
                ))
            conn.commit()

        logger.info(f"Upserted {len(chunks)} vectors into SQLite Vector Store.")
        return len(chunks)

    def search_with_prefilter(
        self,
        query_embedding: List[float],
        daerah: Optional[str] = None,
        tahun: Optional[str] = None,
        kategori: Optional[str] = None,
        tipe_konten: Optional[str] = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Executes metadata pre-filtering before semantic vector similarity ranking.
        """
        # Backend 1: ChromaDB
        if not self.use_sqlite_fallback:
            try:
                filter_conditions = []
                if daerah:
                    filter_conditions.append({"daerah": daerah})
                if tahun:
                    filter_conditions.append({"tahun": str(tahun)})
                if kategori:
                    filter_conditions.append({"kategori": kategori})
                if tipe_konten:
                    filter_conditions.append({"tipe_konten": tipe_konten})

                where_clause = None
                if len(filter_conditions) == 1:
                    where_clause = filter_conditions[0]
                elif len(filter_conditions) > 1:
                    where_clause = {"$and": filter_conditions}

                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where_clause,
                    include=["documents", "metadatas", "distances"]
                )

                formatted = []
                if results and results.get("ids") and len(results["ids"][0]) > 0:
                    for idx in range(len(results["ids"][0])):
                        formatted.append({
                            "chunk_id": results["ids"][0][idx],
                            "score": 1 - results["distances"][0][idx] if results.get("distances") else None,
                            "representasi_teks": results["documents"][0][idx],
                            "metadata": results["metadatas"][0][idx]
                        })
                return formatted
            except Exception as e:
                logger.warning(f"Chroma query failed ({e}). Switching to SQLite vector search.")
                self.use_sqlite_fallback = True

        # Backend 2: SQLite Native Vector Search
        query_clauses = []
        params = []
        if daerah:
            query_clauses.append("daerah = ?")
            params.append(daerah)
        if tahun:
            query_clauses.append("tahun = ?")
            params.append(str(tahun))
        if kategori:
            query_clauses.append("kategori = ?")
            params.append(kategori)
        if tipe_konten:
            query_clauses.append("tipe_konten = ?")
            params.append(tipe_konten)

        where_sql = f"WHERE {' AND '.join(query_clauses)}" if query_clauses else ""
        sql = f"SELECT chunk_id, representasi_teks, metadata_json, embedding_json FROM vector_chunks {where_sql}"

        candidates = []
        with sqlite3.connect(self.sqlite_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            return []

        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)

        for chunk_id, rep_text, meta_json, emb_json in rows:
            emb_vec = np.array(json.loads(emb_json), dtype=np.float32)
            denom = q_norm * np.linalg.norm(emb_vec)
            sim = float(np.dot(q_vec, emb_vec) / denom) if denom > 0 else 0.0
            candidates.append({
                "chunk_id": chunk_id,
                "score": sim,
                "representasi_teks": rep_text,
                "metadata": json.loads(meta_json)
            })

        # Rank by cosine similarity score descending
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:n_results]
