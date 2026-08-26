"""
BPS Table Extractor Module.
Extracts complex tables from BPS PDFs using pdfplumber, captures contextual
titles, footnotes, and units, and transforms them into cleaned DataFrames.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pdfplumber
import pandas as pd
from loguru import logger

from modules.extraction.table_cleaner import TableCleaner


class BPSTableExtractor:
    """Extracts and contextualizes tables from BPS publication PDFs."""

    def __init__(self):
        self.cleaner = TableCleaner()

    def _extract_table_context(
        self, 
        page: pdfplumber.page.Page, 
        table_bbox: Tuple[float, float, float, float]
    ) -> Dict[str, str]:
        """
        Extracts metadata surrounding a table on a PDF page:
        - Table title (above the table)
        - Unit / Satuan (e.g., '(Jiwa)', '(Rupiah)', '(Ton)')
        - Source / Footnotes (below the table)
        """
        x0, top, x1, bottom = table_bbox
        page_height = page.height
        page_width = page.width

        # 1. Look for Table Title above the table (top region: y in [0, top])
        above_crop = page.crop((0, max(0, top - 120), page_width, top))
        above_text = above_crop.extract_text(layout=False) or ""

        table_title = "Tabel Statistik"
        unit = "N/A"

        # Regex to capture BPS table naming pattern (e.g., "Tabel 3.1.1 Jumlah Penduduk...")
        title_match = re.search(
            r"(Tabel|Table)\s+[\d\.]+\s*[:\.]?\s*[^\n]+(?:\n[^\n]+)?",
            above_text,
            re.IGNORECASE
        )
        if title_match:
            table_title = re.sub(r"\s+", " ", title_match.group(0)).strip()
        else:
            # Fallback to the last line above the table
            lines = [l.strip() for l in above_text.splitlines() if l.strip()]
            if lines:
                table_title = lines[-1]

        # Extract unit / satuan e.g. '(Jiwa)', '(Persen)', '(Hektar)'
        unit_match = re.search(r"/\s*([A-Za-z\s%]+)|\(([A-Za-z\s%]+)\)", table_title)
        if unit_match:
            unit = (unit_match.group(1) or unit_match.group(2) or "").strip()

        # 2. Look for Source / Notes below the table (bottom region: y in [bottom, bottom + 80])
        below_crop = page.crop((0, bottom, page_width, min(page_height, bottom + 90)))
        below_text = below_crop.extract_text(layout=False) or ""

        source = "BPS"
        notes = ""

        for line in below_text.splitlines():
            line_str = line.strip()
            if re.search(r"^Sumber\s*[:\.]|^Source\s*[:\.]", line_str, re.IGNORECASE):
                source = re.sub(r"^Sumber\s*[:\.]\s*|^Source\s*[:\.]\s*", "", line_str, flags=re.IGNORECASE).strip()
            elif re.search(r"^Catatan\s*[:\.]|^Note\s*[:\.]", line_str, re.IGNORECASE):
                notes = re.sub(r"^Catatan\s*[:\.]\s*|^Note\s*[:\.]\s*", "", line_str, flags=re.IGNORECASE).strip()

        return {
            "judul_tabel": table_title,
            "satuan": unit,
            "sumber": source,
            "catatan": notes
        }

    def extract_tables_from_pdf(
        self, 
        pdf_path: Path, 
        pages_to_extract: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts all tables from a BPS publication PDF.
        Returns a list of structured table objects with DataFrame and metadata.
        """
        extracted_tables: List[Dict[str, Any]] = []

        if not Path(pdf_path).exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return extracted_tables

        logger.info(f"Opening PDF for table extraction: {pdf_path.name}")

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                page_indices = pages_to_extract if pages_to_extract is not None else range(1, total_pages + 1)

                for page_num in page_indices:
                    if page_num > total_pages:
                        continue
                    
                    page = pdf.pages[page_num - 1]
                    # Find tables with pdfplumber table finder
                    found_tables = page.find_tables(
                        table_settings={
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "lines",
                            "snap_tolerance": 3,
                            "join_tolerance": 3,
                            "edge_min_length": 10,
                            "min_words_vertical": 2
                        }
                    )

                    # If no explicit line tables, try text-based heuristic
                    if not found_tables:
                        found_tables = page.find_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                                "snap_tolerance": 4
                            }
                        )

                    for t_idx, tbl in enumerate(found_tables):
                        raw_matrix = tbl.extract()
                        if not raw_matrix or len(raw_matrix) < 2:
                            continue

                        # Clean and transform
                        cleaned_df = self.cleaner.clean_table_dataframe(raw_matrix)
                        if cleaned_df is None or cleaned_df.empty or len(cleaned_df.columns) < 2:
                            continue

                        # Extract context around bounding box
                        context = self._extract_table_context(page, tbl.bbox)

                        table_obj = {
                            "tabel_id": f"p{page_num}_t{t_idx + 1}",
                            "halaman": page_num,
                            "judul_tabel": context["judul_tabel"],
                            "satuan": context["satuan"],
                            "sumber": context["sumber"],
                            "catatan": context["catatan"],
                            "kolom": list(cleaned_df.columns),
                            "jumlah_baris": len(cleaned_df),
                            "dataframe": cleaned_df,
                            "records": cleaned_df.to_dict(orient="records"),
                            "bbox": tbl.bbox
                        }
                        extracted_tables.append(table_obj)

            logger.info(f"Successfully extracted {len(extracted_tables)} tables from {pdf_path.name}")

        except Exception as e:
            logger.error(f"Error extracting tables from {pdf_path.name}: {e}")

        return extracted_tables
