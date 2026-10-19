"""
JSON Structure Builder Module for BPS RAG Pipeline.
Converts extracted statistical tables and narrative paragraphs into enriched,
context-injected 'RAG-Ready' JSON structures with semantic textual representations.
"""
import re
import hashlib
from typing import Dict, Any, List, Optional
from loguru import logger


class JSONStructureBuilder:
    """Transforms raw extraction outputs into RAG-optimized structured JSON objects."""

    def __init__(self):
        pass

    def _generate_chunk_id(self, prefix: str, doc_id: str, unique_str: str) -> str:
        """Generates a deterministic unique chunk ID."""
        hash_val = hashlib.md5(unique_str.encode()).hexdigest()[:10]
        return f"{prefix}_{doc_id}_{hash_val}"

    def _clean_column_label_for_speech(self, col_name: str) -> str:
        """Formats snake_case or raw column headers into readable Indonesian phrases."""
        clean = col_name.replace("_", " ")
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def _build_table_row_text_representation(
        self,
        row_dict: Dict[str, Any],
        judul_tabel: str,
        dokumen_sumber: str,
        tahun: str,
        satuan: str
    ) -> str:
        """
        Synthesizes a natural language statement from a table row.
        Example output:
        "Berdasarkan Tabel: 'Jumlah Penduduk Menurut Jenis Kelamin' (Kabupaten Demak Dalam Angka 2026, Tahun 2026):
         Pada Kecamatan Mranggen, nilai Jumlah Penduduk Laki-Laki adalah 105.432 Jiwa, nilai Jumlah Penduduk Perempuan adalah 104.521 Jiwa."
        """
        cols = list(row_dict.keys())
        if not cols:
            return ""

        # Identify index / categorical columns (typically 1st or 2nd column)
        # e.g., 'Kecamatan', 'Kelompok_Umur', 'Komoditas'
        index_col = cols[0]
        index_val = str(row_dict[index_col]).strip()

        # Handle secondary index if present (e.g. Kecamatan + Desa, or Kecamatan + Kelompok Usia)
        secondary_context = ""
        metric_start_idx = 1
        if len(cols) > 2 and isinstance(row_dict[cols[1]], str) and not re.match(r"^[\d\.,]+$", str(row_dict[cols[1]])):
            secondary_col = cols[1]
            secondary_val = str(row_dict[secondary_col]).strip()
            if secondary_val:
                secondary_context = f", {self._clean_column_label_for_speech(secondary_col)} '{secondary_val}'"
                metric_start_idx = 2

        # Extract metric statements
        metric_statements = []
        unit_suffix = f" {satuan}" if satuan and satuan != "N/A" else ""

        for col in cols[metric_start_idx:]:
            val = row_dict[col]
            if val is None or str(val).strip() == "" or str(val).lower() == "none":
                continue
            
            clean_col = self._clean_column_label_for_speech(col)
            # Format number if numeric
            if isinstance(val, (int, float)):
                val_formatted = f"{val:,}".replace(",", ".")
            else:
                val_formatted = str(val).strip()

            metric_statements.append(f"nilai {clean_col} adalah {val_formatted}{unit_suffix}")

        if not metric_statements:
            metrics_joined = "tidak ada rincian data angka."
        else:
            metrics_joined = ", ".join(metric_statements)

        clean_index_col = self._clean_column_label_for_speech(index_col)
        text_rep = (
            f"Berdasarkan {judul_tabel} ({dokumen_sumber}, Tahun {tahun}): "
            f"Pada {clean_index_col} '{index_val}'{secondary_context}, {metrics_joined}."
        )
        return text_rep

    def structure_table_chunks(
        self,
        table_obj: Dict[str, Any],
        doc_meta: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Converts a single extracted table into individual row-level RAG JSON chunks.
        """
        chunks: List[Dict[str, Any]] = []
        records = table_obj.get("records", [])
        judul_tabel = table_obj.get("judul_tabel", "Tabel Statistik")
        satuan = table_obj.get("satuan", "N/A")
        sumber = table_obj.get("sumber", "BPS")
        catatan = table_obj.get("catatan", "")
        halaman = table_obj.get("halaman", 1)
        tabel_id = table_obj.get("tabel_id", "t1")

        doc_id = doc_meta["dokumen_id"]
        doc_sumber = doc_meta["dokumen_sumber"]
        daerah = doc_meta["daerah"]
        kategori = doc_meta["kategori"]
        tanggal_publikasi = doc_meta["tanggal_publikasi"]
        tahun = doc_meta["tahun"]

        for r_idx, row in enumerate(records):
            # Generate semantic natural language representation
            text_rep = self._build_table_row_text_representation(
                row_dict=row,
                judul_tabel=judul_tabel,
                dokumen_sumber=doc_sumber,
                tahun=tahun,
                satuan=satuan
            )

            # Unique deterministic ID
            unique_key = f"{doc_id}_{tabel_id}_row_{r_idx}_{text_rep[:30]}"
            chunk_id = self._generate_chunk_id("tbl", doc_id, unique_key)

            chunk = {
                "chunk_id": chunk_id,
                "dokumen_id": doc_id,
                "dokumen_sumber": doc_sumber,
                "daerah": daerah,
                "kategori": kategori,
                "tanggal_publikasi": tanggal_publikasi,
                "tahun": tahun,
                "halaman": halaman,
                "tipe_konten": "tabel_baris",
                "tabel_id": tabel_id,
                "file_json_tabel": f"database/tables/{doc_id}/tabel_{tabel_id}.json",
                "file_json_dokumen": f"database/documents/{doc_id}.json",
                "judul_tabel": judul_tabel,
                "satuan": satuan,
                "sumber": sumber,
                "catatan": catatan,
                "data": row,
                "representasi_teks": text_rep
            }
            chunks.append(chunk)

        return chunks

    def structure_narrative_chunks(
        self,
        text_obj: Dict[str, Any],
        doc_meta: Dict[str, Any],
        idx: int
    ) -> Dict[str, Any]:
        """
        Structures a narrative paragraph into a contextual RAG chunk.
        """
        doc_id = doc_meta["dokumen_id"]
        doc_sumber = doc_meta["dokumen_sumber"]
        daerah = doc_meta["daerah"]
        kategori = doc_meta["kategori"]
        tanggal_publikasi = doc_meta["tanggal_publikasi"]
        tahun = doc_meta["tahun"]

        bab = text_obj.get("bab", "Pengantar")
        sub_bab = text_obj.get("sub_bab", "Umum")
        halaman = text_obj.get("halaman", 1)
        raw_text = text_obj.get("teks", "").strip()

        # Injected textual representation for semantic retrieval
        text_rep = f"[{doc_sumber} - {daerah} | {bab} - {sub_bab} (Hal. {halaman})]: {raw_text}"
        chunk_id = self._generate_chunk_id("txt", doc_id, f"{doc_id}_{halaman}_{idx}_{raw_text[:30]}")

        return {
            "chunk_id": chunk_id,
            "dokumen_id": doc_id,
            "dokumen_sumber": doc_sumber,
            "daerah": daerah,
            "kategori": kategori,
            "tanggal_publikasi": tanggal_publikasi,
            "tahun": tahun,
            "halaman": halaman,
            "tipe_konten": "teks_naratif",
            "file_json_naratif": f"database/narratives/{doc_id}/naratif_{idx+1}.json",
            "file_json_dokumen": f"database/documents/{doc_id}.json",
            "bab": bab,
            "sub_bab": sub_bab,
            "data": {
                "paragraf": raw_text
            },
            "representasi_teks": text_rep
        }

    def build_rag_chunks_from_extraction(
        self,
        extracted_doc: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Processes all extracted tables and text blocks in a document
        and returns a unified list of RAG-ready structured chunks.
        """
        doc_meta = {
            "dokumen_id": extracted_doc["dokumen_id"],
            "dokumen_sumber": extracted_doc["dokumen_sumber"],
            "daerah": extracted_doc["daerah"],
            "kategori": extracted_doc["kategori"],
            "tanggal_publikasi": extracted_doc["tanggal_publikasi"],
            "tahun": extracted_doc["tahun"],
        }

        all_chunks: List[Dict[str, Any]] = []

        # 1. Process Tables
        tables = extracted_doc.get("tabel_list", [])
        for tbl in tables:
            tbl_chunks = self.structure_table_chunks(tbl, doc_meta)
            all_chunks.extend(tbl_chunks)

        # 2. Process Narrative Texts
        texts = extracted_doc.get("teks_list", [])
        for idx, txt in enumerate(texts):
            txt_chunk = self.structure_narrative_chunks(txt, doc_meta, idx)
            all_chunks.append(txt_chunk)

        logger.info(
            f"Structured {len(all_chunks)} total RAG chunks for document "
            f"'{doc_meta['dokumen_sumber']}' ({len(tables)} tables, {len(texts)} texts)."
        )

        return all_chunks
