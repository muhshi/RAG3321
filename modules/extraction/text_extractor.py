"""
BPS Text & Narrative Extractor Module.
Extracts narrative chapters, executive summaries, and analytical descriptions
from BPS PDFs while filtering out header/footer noise and table zones.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import pdfplumber
from loguru import logger
from config.settings import settings


class BPSTextExtractor:
    """Extracts layout-aware textual narratives and chapter headings from BPS PDFs."""

    def __init__(self):
        # BPS header/footer regex filters
        self.ignore_patterns = [
            r"^https?://",
            r"^halaman\s+\d+",
            r"^\d+\s*$",
            r"badan\s+pusat\s+statistik",
            r"kabupaten\s+demak\s+dalam\s+angka",
            r"bupati\s+demak"
        ]

    def _is_header_or_footer(self, line: str, y0: float, y1: float, page_height: float) -> bool:
        """Determines if a text line is in the extreme top/bottom margins (header/footer)."""
        if y0 < 45 or y1 > (page_height - 45):
            return True
        for pat in self.ignore_patterns:
            if re.search(pat, line.strip(), re.IGNORECASE):
                return True
        return False

    def extract_text_chunks_from_pdf(
        self, 
        pdf_path: Path, 
        pages_to_extract: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts narrative text blocks, keeping track of active Chapters and Sections.
        """
        extracted_text_blocks: List[Dict[str, Any]] = []

        if not Path(pdf_path).exists():
            logger.error(f"PDF not found for text extraction: {pdf_path}")
            return extracted_text_blocks

        current_chapter = "Pengantar & Umum"
        current_section = "Umum"

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                max_pages = getattr(settings, "MAX_EXTRACT_PAGES", None)
                if pages_to_extract is not None:
                    page_indices = pages_to_extract
                elif max_pages:
                    page_indices = range(1, min(total_pages, max_pages) + 1)
                else:
                    page_indices = range(1, total_pages + 1)

                for page_num in page_indices:
                    if page_num > total_pages:
                        continue

                    page = pdf.pages[page_num - 1]
                    page_height = page.height
                    
                    # Extract words with layout information
                    words = page.extract_words(
                        keep_blank_chars=False,
                        extra_attrs=["size", "fontname"]
                    )
                    if not words:
                        continue

                    # Group words into lines
                    lines_by_top: Dict[int, List[Dict[str, Any]]] = {}
                    for w in words:
                        top_rounded = int(w["top"] / 3) * 3  # Cluster within 3 points
                        lines_by_top.setdefault(top_rounded, []).append(w)

                    # Sort lines vertically
                    sorted_tops = sorted(lines_by_top.keys())
                    current_paragraph: List[str] = []

                    for top_key in sorted_tops:
                        line_words = sorted(lines_by_top[top_key], key=lambda x: x["x0"])
                        line_text = " ".join([w["text"] for w in line_words]).strip()
                        avg_y0 = min(w["top"] for w in line_words)
                        avg_y1 = max(w["bottom"] for w in line_words)

                        if not line_text:
                            continue

                        # Check header/footer
                        if self._is_header_or_footer(line_text, avg_y0, avg_y1, page_height):
                            continue

                        # Check Chapter Header pattern (e.g. "BAB 1", "BAB I", "BAB 3 KEPENDUDUKAN")
                        chapter_match = re.match(r"^(BAB\s+[\dIVXLCDM]+[:\.\s\-]+[^\n]+)", line_text, re.IGNORECASE)
                        if chapter_match:
                            current_chapter = chapter_match.group(1).strip()
                            continue

                        # Check Sub-section Header (e.g. "1.1 Geografi dan Iklim", "3.2 Ketenagakerjaan")
                        section_match = re.match(r"^(\d+\.\d+\s+[A-Za-z\s]+)$", line_text)
                        if section_match:
                            current_section = section_match.group(1).strip()
                            continue

                        # Skip lines that are purely table headers or numeric columns
                        if re.match(r"^[\d\s\.,\-%]+$", line_text) and len(line_text.split()) > 3:
                            continue

                        # Detect paragraph continuation vs new paragraph
                        if line_text.endswith((".", ":", ";", "!")):
                            current_paragraph.append(line_text)
                            full_para_text = " ".join(current_paragraph).strip()
                            
                            if len(full_para_text) > 40:  # Ignore trivial noise
                                extracted_text_blocks.append({
                                    "halaman": page_num,
                                    "bab": current_chapter,
                                    "sub_bab": current_section,
                                    "tipe_konten": "teks_naratif",
                                    "teks": full_para_text
                                })
                            current_paragraph = []
                        else:
                            current_paragraph.append(line_text)

                    # Flush remaining line buffer for this page
                    if current_paragraph:
                        full_para_text = " ".join(current_paragraph).strip()
                        if len(full_para_text) > 40:
                            extracted_text_blocks.append({
                                "halaman": page_num,
                                "bab": current_chapter,
                                "sub_bab": current_section,
                                "tipe_konten": "teks_naratif",
                                "teks": full_para_text
                            })

            logger.info(f"Extracted {len(extracted_text_blocks)} narrative text blocks from {pdf_path.name}")

        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path.name}: {e}")

        return extracted_text_blocks
