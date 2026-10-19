"""
Document Store Module (NoSQL / JSON repository).
Stores structured JSON data across three granular tiers:
1. Per-Table JSON files: `database/tables/{doc_id}/tabel_{tabel_id}.json`
2. Per-Document JSON files: `database/documents/{doc_id}.json` (1 PDF = 1 JSON file)
3. Per-Narrative JSON files: `database/narratives/{doc_id}/naratif_{idx}.json`
Also maintains a centralized master catalog index to guarantee backward compatibility.
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger
from config.settings import settings


class DocumentStore:
    """
    Manages the granular JSON document database repository:
    - 1 file JSON per tabel (hemat token & anti-halusinasi)
    - 1 file JSON per dokumen PDF
    - Vektor linking langsung ke file JSON tabel
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        documents_dir: Optional[Path] = None,
        tables_dir: Optional[Path] = None,
        narratives_dir: Optional[Path] = None
    ):
        self.storage_path = storage_path or settings.DOCUMENT_DB_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if storage_path and not documents_dir:
            self.documents_dir = self.storage_path.parent / "documents"
            self.tables_dir = self.storage_path.parent / "tables"
            self.narratives_dir = self.storage_path.parent / "narratives"
        else:
            self.documents_dir = documents_dir or settings.DOCUMENTS_DIR
            self.tables_dir = tables_dir or settings.TABLES_DIR
            self.narratives_dir = narratives_dir or settings.NARRATIVES_DIR

        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        self.narratives_dir.mkdir(parents=True, exist_ok=True)

        self._ensure_storage_exists()

    def _ensure_storage_exists(self) -> None:
        """Initializes the master catalog JSON if it doesn't exist."""
        if not self.storage_path.exists():
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"documents": {}}, f, indent=2, ensure_ascii=False)
            logger.info(f"Initialized Document DB Master Catalog at {self.storage_path}")

    def _read_db(self) -> Dict[str, Any]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading Document DB Catalog: {e}")
            return {"documents": {}}

    def _write_db(self, data: Dict[str, Any]) -> None:
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _slugify(self, text: str) -> str:
        """Converts strings to clean snake_case filenames."""
        import re
        text = str(text).lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "_", text)
        return text.strip("_")

    def save_table_json(
        self,
        doc_id: str,
        table_meta: Dict[str, Any],
        table_chunks: List[Dict[str, Any]],
        doc_metadata: Dict[str, Any]
    ) -> Path:
        """
        Saves a single table as a standalone JSON file with a descriptive name.
        """
        doc_tables_dir = self.tables_dir / doc_id
        doc_tables_dir.mkdir(parents=True, exist_ok=True)

        tabel_id = table_meta.get("tabel_id", "t1")
        judul_slug = self._slugify(table_meta.get("judul_tabel", ""))[:35]
        t_filename = f"tabel_{tabel_id}_{judul_slug}.json" if judul_slug else f"tabel_{tabel_id}.json"
        table_file_path = doc_tables_dir / t_filename

        # Collect row representations and chunk IDs
        text_reps = [c.get("representasi_teks", "") for c in table_chunks]
        chunk_ids = [c.get("chunk_id", "") for c in table_chunks]

        payload = {
            "tabel_id": tabel_id,
            "judul_tabel": table_meta.get("judul_tabel", "Tabel Statistik"),
            "dokumen_id": doc_id,
            "dokumen_sumber": doc_metadata.get("dokumen_sumber", ""),
            "daerah": doc_metadata.get("daerah", settings.DEFAULT_REGION),
            "kategori": doc_metadata.get("kategori", "Statistik Umum"),
            "tahun": str(doc_metadata.get("tahun", "")),
            "tanggal_publikasi": str(doc_metadata.get("tanggal_publikasi", "")),
            "halaman": table_meta.get("halaman", 1),
            "satuan": table_meta.get("satuan", "N/A"),
            "sumber": table_meta.get("sumber", "BPS"),
            "catatan": table_meta.get("catatan", ""),
            "kolom": table_meta.get("kolom", []),
            "total_baris": len(table_meta.get("records", [])),
            "records": table_meta.get("records", []),
            "representasi_teks_baris": text_reps,
            "chunk_ids": chunk_ids,
            "file_json": f"database/tables/{doc_id}/{t_filename}"
        }

        with open(table_file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        return table_file_path

    def save_narrative_json(
        self,
        doc_id: str,
        text_meta: Dict[str, Any],
        idx: int,
        chunk: Dict[str, Any],
        doc_metadata: Dict[str, Any]
    ) -> Path:
        """
        Saves a single narrative block as a standalone JSON file with a descriptive name.
        """
        doc_narr_dir = self.narratives_dir / doc_id
        doc_narr_dir.mkdir(parents=True, exist_ok=True)

        bab_slug = self._slugify(text_meta.get("bab", "bab"))[:30]
        n_filename = f"naratif_{idx}_{bab_slug}.json" if bab_slug else f"naratif_{idx}.json"
        narr_file_path = doc_narr_dir / n_filename

        payload = {
            "naratif_id": f"n{idx}",
            "dokumen_id": doc_id,
            "dokumen_sumber": doc_metadata.get("dokumen_sumber", ""),
            "daerah": doc_metadata.get("daerah", settings.DEFAULT_REGION),
            "kategori": doc_metadata.get("kategori", "Statistik Umum"),
            "tahun": str(doc_metadata.get("tahun", "")),
            "halaman": text_meta.get("halaman", 1),
            "bab": text_meta.get("bab", "Pengantar"),
            "sub_bab": text_meta.get("sub_bab", "Umum"),
            "paragraf": text_meta.get("teks", ""),
            "representasi_teks": chunk.get("representasi_teks", ""),
            "chunk_id": chunk.get("chunk_id", ""),
            "file_json": f"database/narratives/{doc_id}/{n_filename}"
        }

        with open(narr_file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        return narr_file_path

    def save_document(
        self,
        doc_id: str,
        doc_metadata: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        extracted_doc: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Saves or updates a complete publication document across all storage tiers:
        1. Standalone JSON for each table (`database/tables/{doc_id}/tabel_{tabel_id}.json`)
        2. Standalone JSON for each narrative block (`database/narratives/{doc_id}/naratif_{idx}.json`)
        3. Standalone JSON for the PDF document (`database/documents/{doc_id}.json`)
        4. Updates Master Catalog Index (`database/bps_documents.json`)
        """
        clean_chunks = []
        for c in chunks:
            c_copy = {k: v for k, v in c.items() if k != "embedding"}
            clean_chunks.append(c_copy)

        # ---------------------------------------------------------------------
        # 1. Process and Save Per-Table JSON files
        # ---------------------------------------------------------------------
        table_files_meta = []
        
        if extracted_doc and extracted_doc.get("tabel_list"):
            # Use raw extraction tables if provided
            for tbl in extracted_doc["tabel_list"]:
                t_id = tbl.get("tabel_id", "t1")
                # Find matching chunks
                t_chunks = [
                    c for c in clean_chunks 
                    if c.get("tipe_konten") == "tabel_baris" and (c.get("tabel_id") == t_id or c.get("judul_tabel") == tbl.get("judul_tabel"))
                ]
                saved_path = self.save_table_json(doc_id, tbl, t_chunks, doc_metadata)
                table_files_meta.append({
                    "tabel_id": t_id,
                    "judul_tabel": tbl.get("judul_tabel", ""),
                    "halaman": tbl.get("halaman", 1),
                    "total_baris": len(tbl.get("records", [])),
                    "file_json": str(saved_path.as_posix())
                })
        else:
            # Reconstruct table groups from clean_chunks
            table_groups: Dict[str, List[Dict[str, Any]]] = {}
            for c in clean_chunks:
                if c.get("tipe_konten") == "tabel_baris":
                    t_id = c.get("tabel_id") or "t1"
                    table_groups.setdefault(t_id, []).append(c)

            for t_id, t_chunks in table_groups.items():
                first = t_chunks[0]
                records = [c.get("data", {}) for c in t_chunks if isinstance(c.get("data"), dict)]
                tbl_meta = {
                    "tabel_id": t_id,
                    "judul_tabel": first.get("judul_tabel", "Tabel Statistik"),
                    "halaman": first.get("halaman", 1),
                    "satuan": first.get("satuan", "N/A"),
                    "sumber": first.get("sumber", "BPS"),
                    "catatan": first.get("catatan", ""),
                    "kolom": list(records[0].keys()) if records else [],
                    "records": records
                }
                saved_path = self.save_table_json(doc_id, tbl_meta, t_chunks, doc_metadata)
                table_files_meta.append({
                    "tabel_id": t_id,
                    "judul_tabel": tbl_meta["judul_tabel"],
                    "halaman": tbl_meta["halaman"],
                    "total_baris": len(records),
                    "file_json": str(saved_path.as_posix())
                })

        # ---------------------------------------------------------------------
        # 2. Process and Save Per-Narrative JSON files
        # ---------------------------------------------------------------------
        narrative_files_meta = []
        if extracted_doc and extracted_doc.get("teks_list"):
            for idx, txt in enumerate(extracted_doc["teks_list"], 1):
                # Matching chunk
                n_chunk = next(
                    (c for c in clean_chunks if c.get("tipe_konten") == "teks_naratif" and c.get("bab") == txt.get("bab")),
                    {"representasi_teks": txt.get("teks", ""), "chunk_id": f"txt_{doc_id}_{idx}"}
                )
                saved_path = self.save_narrative_json(doc_id, txt, idx, n_chunk, doc_metadata)
                narrative_files_meta.append({
                    "naratif_id": f"n{idx}",
                    "bab": txt.get("bab", ""),
                    "sub_bab": txt.get("sub_bab", ""),
                    "halaman": txt.get("halaman", 1),
                    "file_json": str(saved_path.as_posix())
                })
        else:
            narr_chunks = [c for c in clean_chunks if c.get("tipe_konten") == "teks_naratif"]
            for idx, c in enumerate(narr_chunks, 1):
                txt_meta = {
                    "bab": c.get("bab", "Pengantar"),
                    "sub_bab": c.get("sub_bab", "Umum"),
                    "halaman": c.get("halaman", 1),
                    "teks": c.get("data", {}).get("paragraf", "") if isinstance(c.get("data"), dict) else ""
                }
                saved_path = self.save_narrative_json(doc_id, txt_meta, idx, c, doc_metadata)
                narrative_files_meta.append({
                    "naratif_id": f"n{idx}",
                    "bab": txt_meta["bab"],
                    "sub_bab": txt_meta["sub_bab"],
                    "halaman": txt_meta["halaman"],
                    "file_json": str(saved_path.as_posix())
                })

        # ---------------------------------------------------------------------
        # 3. Save Dedicated Document JSON File (1 PDF = 1 File JSON)
        # ---------------------------------------------------------------------
        doc_file_path = self.documents_dir / f"{doc_id}.json"
        doc_json_payload = {
            "dokumen_id": doc_id,
            "dokumen_sumber": doc_metadata.get("dokumen_sumber", ""),
            "daerah": doc_metadata.get("daerah", settings.DEFAULT_REGION),
            "kategori": doc_metadata.get("kategori", "Statistik Umum"),
            "tahun": str(doc_metadata.get("tahun", "")),
            "tanggal_publikasi": str(doc_metadata.get("tanggal_publikasi", "")),
            "file_pdf_path": str(doc_metadata.get("file_path", "")),
            "total_tabel": len(table_files_meta),
            "total_teks": len(narrative_files_meta),
            "total_chunks": len(clean_chunks),
            "daftar_tabel": table_files_meta,
            "daftar_teks": narrative_files_meta,
            "chunks": clean_chunks
        }
        with open(doc_file_path, "w", encoding="utf-8") as f:
            json.dump(doc_json_payload, f, indent=2, ensure_ascii=False)

        # ---------------------------------------------------------------------
        # 4. Update Central Master Catalog
        # ---------------------------------------------------------------------
        db = self._read_db()
        db["documents"][doc_id] = {
            "metadata": doc_metadata,
            "total_chunks": len(clean_chunks),
            "total_tabel": len(table_files_meta),
            "total_teks": len(narrative_files_meta),
            "file_json_dokumen": str(doc_file_path.as_posix()),
            "daftar_tabel": table_files_meta,
            "chunks": clean_chunks
        }
        self._write_db(db)

        logger.info(
            f"Successfully saved [{doc_id}]: "
            f"1 Document JSON ({doc_file_path.name}), "
            f"{len(table_files_meta)} Table JSONs, "
            f"{len(narrative_files_meta)} Narrative JSONs."
        )

        return doc_json_payload

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document by document ID (first from dedicated file, then catalog)."""
        doc_file = self.documents_dir / f"{doc_id}.json"
        if doc_file.exists():
            try:
                with open(doc_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading document file {doc_file}: {e}")

        db = self._read_db()
        return db["documents"].get(doc_id)

    def get_table(self, doc_id: str, tabel_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific table's standalone JSON file."""
        tbl_file = self.tables_dir / doc_id / f"tabel_{tabel_id}.json"
        if tbl_file.exists():
            try:
                with open(tbl_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading table file {tbl_file}: {e}")
        return None

    def list_documents(self) -> List[Dict[str, Any]]:
        """Returns metadata for all indexed documents in the repository."""
        results = []
        doc_files = list(self.documents_dir.glob("*.json"))
        if doc_files:
            for f in doc_files:
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                        results.append({
                            "dokumen_id": data.get("dokumen_id", f.stem),
                            "dokumen_sumber": data.get("dokumen_sumber", ""),
                            "daerah": data.get("daerah", ""),
                            "tahun": data.get("tahun", ""),
                            "total_tabel": data.get("total_tabel", 0),
                            "total_chunks": data.get("total_chunks", 0),
                            "file_json": str(f.as_posix())
                        })
                except Exception:
                    pass
            return results

        db = self._read_db()
        return [
            {"dokumen_id": k, **v.get("metadata", {})}
            for k, v in db["documents"].items()
        ]

    def list_tables(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns a list of all saved table JSON files across all or specific documents."""
        results = []
        search_dirs = [self.tables_dir / doc_id] if doc_id else list(self.tables_dir.iterdir())
        for d in search_dirs:
            if d.is_dir():
                for tf in d.glob("*.json"):
                    try:
                        with open(tf, "r", encoding="utf-8") as fp:
                            t_data = json.load(fp)
                            results.append({
                                "tabel_id": t_data.get("tabel_id"),
                                "judul_tabel": t_data.get("judul_tabel"),
                                "dokumen_id": t_data.get("dokumen_id"),
                                "dokumen_sumber": t_data.get("dokumen_sumber"),
                                "tahun": t_data.get("tahun"),
                                "total_baris": t_data.get("total_baris"),
                                "file_path": str(tf.as_posix())
                            })
                    except Exception:
                        pass
        return results
