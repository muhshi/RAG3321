"""
PDF Extraction Pipeline Orchestrator.
Coordinates table extraction and narrative text extraction for a publication PDF.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from modules.extraction.table_extractor import BPSTableExtractor
from modules.extraction.text_extractor import BPSTextExtractor


class PDFExtractionPipeline:
    """Master extractor combining tables and text extraction for BPS documents."""

    def __init__(self):
        self.table_extractor = BPSTableExtractor()
        self.text_extractor = BPSTextExtractor()

    def process_pdf(
        self, 
        pdf_path: Path, 
        metadata: Optional[Dict[str, Any]] = None,
        pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Executes full extraction pipeline on a PDF file:
        1. Extract all structured tables with multi-level headers and forward-filled cells.
        2. Extract layout-aware narrative text paragraphs with chapter context.
        3. Bundle into an enriched extraction result.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        meta = metadata or {}
        doc_title = meta.get("title", pdf_path.stem)
        pub_id = meta.get("publication_id", pdf_path.stem.split("_")[0])
        release_date = meta.get("release_date", "2026-01-01")
        category = meta.get("category", "Statistik Umum")
        region = meta.get("region", "Kabupaten Demak")

        logger.info(f"===> Starting extraction for document: [{pub_id}] {doc_title}")

        # 1. Extract Tables
        tables = self.table_extractor.extract_tables_from_pdf(pdf_path, pages_to_extract=pages)

        # 2. Extract Text Blocks
        texts = self.text_extractor.extract_text_chunks_from_pdf(pdf_path, pages_to_extract=pages)

        # 3. Assemble complete extraction payload
        extracted_doc = {
            "dokumen_id": pub_id,
            "dokumen_sumber": doc_title,
            "daerah": region,
            "kategori": category,
            "tanggal_publikasi": release_date,
            "tahun": release_date.split("-")[0] if "-" in release_date else "2026",
            "file_path": str(pdf_path),
            "total_tabel": len(tables),
            "total_teks": len(texts),
            "tabel_list": tables,
            "teks_list": texts
        }

        logger.info(
            f"Extraction completed for [{pub_id}]: "
            f"{len(tables)} tables, {len(texts)} narrative text blocks."
        )

        return extracted_doc
