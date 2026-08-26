"""
Table Cleaner Module for BPS Statistical Tables.
Handles multi-index header flattening, merged-row forward fill, and Indonesian BPS notation sanitization.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from loguru import logger


class TableCleaner:
    """Specialized data cleaner for BPS complex statistical tables."""

    @staticmethod
    def clean_cell_text(val: Any) -> str:
        """Removes internal newlines, extra spaces, and special artifacts from a cell."""
        if val is None:
            return ""
        s = str(val).strip()
        # Replace newlines and multiple spaces
        s = re.sub(r"\s+", " ", s)
        return s

    @classmethod
    def detect_header_rows(cls, raw_matrix: List[List[Any]], max_scan: int = 4) -> int:
        """
        Determines how many top rows constitute the multi-level header.
        Heuristic: Header rows usually contain non-numeric category labels,
        while data rows contain mostly numbers or district identifiers + numbers.
        """
        if not raw_matrix or len(raw_matrix) <= 1:
            return 1

        num_scan = min(len(raw_matrix) - 1, max_scan)
        header_depth = 1

        for r_idx in range(1, num_scan):
            row = raw_matrix[r_idx]
            cleaned_row = [cls.clean_cell_text(c) for c in row]
            
            # Count numeric-looking cells in the row
            num_numeric = sum(
                1 for c in cleaned_row 
                if re.match(r"^[\d\.,\-]+$", c) and len(c) > 0 and c != "-"
            )
            
            # If majority of non-empty cells are numeric, this is a data row, stop
            non_empty_count = sum(1 for c in cleaned_row if len(c) > 0)
            if non_empty_count > 0 and (num_numeric / non_empty_count) >= 0.5:
                break

            # If it's a sub-header (e.g. column labels like '(1)', '(2)', '(3)' or 'Laki-laki', 'Perempuan')
            header_depth = r_idx + 1

        return header_depth

    @classmethod
    def flatten_multi_index_headers(
        cls, 
        header_rows: List[List[Any]]
    ) -> List[str]:
        """
        Flattens multi-row headers into clean single column names.
        Example:
            Row 0: ['Kecamatan', 'Jumlah Penduduk', '']
            Row 1: ['', 'Laki-laki', 'Perempuan']
            Result: ['Kecamatan', 'Jumlah_Penduduk_Laki-laki', 'Jumlah_Penduduk_Perempuan']
        """
        if not header_rows:
            return []
        
        num_cols = max(len(r) for r in header_rows)
        # Pad shorter rows
        normalized_rows = []
        for row in header_rows:
            padded = list(row) + [""] * (num_cols - len(row))
            normalized_rows.append([cls.clean_cell_text(c) for c in padded])

        # Step 1: Forward-fill headers horizontally for merged top headers
        # E.g. ['Jumlah Penduduk', '', ''] -> ['Jumlah Penduduk', 'Jumlah Penduduk', 'Jumlah Penduduk']
        df_header = pd.DataFrame(normalized_rows)
        for r_idx in range(len(df_header)):
            curr_val = ""
            for c_idx in range(num_cols):
                val = df_header.iloc[r_idx, c_idx]
                if val:
                    # Ignore numbering rows like (1), (2), (3)
                    if not re.match(r"^\(\d+\)$", val):
                        curr_val = val
                elif curr_val:
                    df_header.iloc[r_idx, c_idx] = curr_val

        # Step 2: Combine vertically
        final_headers: List[str] = []
        for c_idx in range(num_cols):
            col_parts: List[str] = []
            for r_idx in range(len(df_header)):
                val = df_header.iloc[r_idx, c_idx].strip()
                # Skip numbering rows like (1), (2), (3) or duplicate tokens
                if not val or re.match(r"^\(\d+\)$", val):
                    continue
                if not col_parts or val.lower() != col_parts[-1].lower():
                    col_parts.append(val)

            if not col_parts:
                col_name = f"Kolom_{c_idx + 1}"
            else:
                col_name = "_".join(col_parts)

            # Clean and sanitize column name
            col_name = re.sub(r"[^\w\s-]", "", col_name)
            col_name = re.sub(r"[\s-]+", "_", col_name).strip("_")
            final_headers.append(col_name)

        # Handle duplicate column names if any
        seen: Dict[str, int] = {}
        unique_headers: List[str] = []
        for h in final_headers:
            if not h:
                h = "Kolom"
            if h in seen:
                seen[h] += 1
                unique_headers.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 1
                unique_headers.append(h)

        return unique_headers

    @classmethod
    def sanitize_indonesian_numeric(cls, val: Any) -> Any:
        """
        Converts Indonesian BPS numbers to standard floats/integers.
        - '-' -> 0
        - '...' / '…' -> None (N/A)
        - '1.234,50' -> 1234.50
        - '12.345' -> 12345
        - '10,5 %' -> 10.5
        """
        if val is None or pd.isna(val):
            return None

        s = str(val).strip()
        if not s:
            return None

        # BPS symbols
        if s in ("-", "–", "—", "- "):
            return 0
        if s in ("...", "…", "NA", "N/A", "null"):
            return None

        # Remove footnote markers like '1)', '*)', 'r', 'e' attached to numbers
        s_clean = re.sub(r"[a-zA-Z\*\(\)]", "", s).strip()
        s_clean = s_clean.replace("%", "").strip()

        # Check if it matches Indonesian decimal/thousands pattern
        # Indonesian: dot is thousands, comma is decimal (e.g. 1.234,56 or 123,4)
        if re.match(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$", s_clean):
            # Format: 1.234.567,89 -> 1234567.89
            s_std = s_clean.replace(".", "").replace(",", ".")
            try:
                f_val = float(s_std)
                return int(f_val) if f_val.is_integer() else f_val
            except ValueError:
                pass
        elif re.match(r"^-?\d+(,\d+)$", s_clean):
            # Format: 123,45 -> 123.45
            s_std = s_clean.replace(",", ".")
            try:
                f_val = float(s_std)
                return int(f_val) if f_val.is_integer() else f_val
            except ValueError:
                pass
        elif re.match(r"^-?\d+(\.\d+)?$", s_clean):
            # Format: 12345 or 123.45 (already standard)
            try:
                f_val = float(s_clean)
                return int(f_val) if f_val.is_integer() else f_val
            except ValueError:
                pass

        # If not cleanly numeric, return original cleaned string
        return cls.clean_cell_text(val)

    @classmethod
    def clean_table_dataframe(
        cls, 
        raw_matrix: List[List[Any]], 
        header_depth: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        Transforms raw extracted table matrix into a clean, structured pandas DataFrame:
        1. Multi-level header extraction & flattening
        2. Merged cell forward-fill on categorical columns
        3. Numeric conversion with BPS notation handling
        4. Trimming summary rows ('Jumlah' / 'Total') if needed
        """
        if not raw_matrix or len(raw_matrix) < 2:
            return None

        # Determine header depth if not explicitly provided
        if header_depth is None:
            header_depth = cls.detect_header_rows(raw_matrix)

        header_rows = raw_matrix[:header_depth]
        data_rows = raw_matrix[header_depth:]

        if not data_rows:
            return None

        # Flatten headers
        headers = cls.flatten_multi_index_headers(header_rows)
        num_cols = len(headers)

        # Pad or trim data rows to match header width
        normalized_data = []
        for r in data_rows:
            cleaned_r = [cls.clean_cell_text(c) for c in r]
            if len(cleaned_r) < num_cols:
                cleaned_r.extend([""] * (num_cols - len(cleaned_r)))
            elif len(cleaned_r) > num_cols:
                cleaned_r = cleaned_r[:num_cols]
            
            # Skip completely empty rows
            if any(cleaned_r):
                normalized_data.append(cleaned_r)

        if not normalized_data:
            return None

        df = pd.DataFrame(normalized_data, columns=headers)

        # Forward-fill (ffill) category/identifier columns (typically leftmost 1 or 2 columns)
        # E.g. Kecamatan, Kelompok Umur
        for col_idx in range(min(2, len(df.columns))):
            col_name = df.columns[col_idx]
            # Replace empty strings with NaN temporarily for ffill
            df[col_name] = df[col_name].replace("", np.nan).ffill().fillna("")

        # Sanitize numeric columns and values
        for col in df.columns:
            df[col] = df[col].apply(cls.sanitize_indonesian_numeric)

        # Drop columns that are completely empty / all NaN
        df = df.dropna(how="all", axis=1)

        return df
