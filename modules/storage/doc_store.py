"""
Document Store Module (NoSQL / JSON repository).
Stores full extracted document metadata, raw tables, and RAG chunk JSONs.
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger
from config.settings import settings


class DocumentStore:
    """Manages the full-text JSON document database repository."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or settings.DOCUMENT_DB_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_storage_exists()

    def _ensure_storage_exists(self) -> None:
        """Initializes the JSON storage file if it doesn't exist."""
        if not self.storage_path.exists():
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"documents": {}}, f, indent=2, ensure_ascii=False)
            logger.info(f"Initialized Document DB at {self.storage_path}")

    def _read_db(self) -> Dict[str, Any]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading Document DB: {e}")
            return {"documents": {}}

    def _write_db(self, data: Dict[str, Any]) -> None:
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_document(
        self,
        doc_id: str,
        doc_metadata: Dict[str, Any],
        chunks: List[Dict[str, Any]]
    ) -> None:
        """
        Saves or updates a complete publication document and its structured chunks.
        Note: Strips large binary vector embeddings before saving to JSON document DB
        to keep storage clean and lightweight.
        """
        db = self._read_db()

        # Clean chunk representation for JSON document DB (remove embeddings array)
        clean_chunks = []
        for c in chunks:
            c_copy = {k: v for k, v in c.items() if k != "embedding"}
            clean_chunks.append(c_copy)

        db["documents"][doc_id] = {
            "metadata": doc_metadata,
            "total_chunks": len(clean_chunks),
            "chunks": clean_chunks
        }

        self._write_db(db)
        logger.info(f"Successfully saved document [{doc_id}] ({len(clean_chunks)} chunks) into Document DB.")

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document and all its chunks by document ID."""
        db = self._read_db()
        return db["documents"].get(doc_id)

    def list_documents(self) -> List[Dict[str, Any]]:
        """Returns metadata for all indexed documents in the repository."""
        db = self._read_db()
        return [
            {"dokumen_id": k, **v.get("metadata", {})}
            for k, v in db["documents"].items()
        ]
