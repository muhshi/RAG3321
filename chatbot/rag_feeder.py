"""
RAG Feeder Module for BPS AI Chatbot.
Acts as the bridge between BPS Vector Database (Chroma/SQLite), granular JSON tables,
and the AI Chatbot context window.
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

from config.settings import settings
from chatbot.config import bot_config
from chatbot.prompt_templates import format_rag_context
from modules.storage.vector_store import BPSVectorStore
from modules.vectorization.embedder import VectorEmbedder


class RAGFeeder:
    """
    Retrieves and feeds relevant BPS publication data (tables and narratives)
    into the AI Chatbot context.
    """

    def __init__(
        self,
        vector_store: Optional[BPSVectorStore] = None,
        embedder: Optional[VectorEmbedder] = None
    ):
        self.vector_store = vector_store or BPSVectorStore()
        self.embedder = embedder or VectorEmbedder()

    def warm_up(self) -> None:
        """Pre-loads the embedding model into memory in the background."""
        try:
            self.embedder._init_model()
        except Exception as e:
            logger.warning(f"[RAGFeeder] Pre-warming embedder encountered: {e}")

    def _extract_year_from_query(self, query: str) -> Optional[str]:
        """Detects 4-digit years in query (e.g. 2018-2026) for optional pre-filtering."""
        match = re.search(r"\b(201[0-9]|202[0-9])\b", query)
        return match.group(1) if match else None

    def _load_granular_table_preview(self, json_path_str: str, max_rows: int = 20) -> Optional[str]:
        """
        Reads granular table JSON directly from disk and formats it into
        a readable Markdown table for the LLM.
        """
        if not json_path_str:
            return None

        # Resolve path relative to project root if needed
        table_path = Path(json_path_str)
        if not table_path.is_absolute():
            table_path = settings.PROJECT_ROOT / table_path

        if not table_path.exists():
            return None

        try:
            with open(table_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            columns = data.get("kolom", [])
            records = data.get("records", [])
            satuan = data.get("satuan", "N/A")
            sumber = data.get("sumber", "BPS")

            if not columns or not records:
                return None

            # Render markdown table header
            clean_cols = [c.replace("_", " ") for c in columns]
            lines = [
                f"Satuan: {satuan} | Sumber: {sumber}",
                "| " + " | ".join(clean_cols) + " |",
                "| " + " | ".join(["---"] * len(clean_cols)) + " |"
            ]

            # Render limited rows
            for row in records[:max_rows]:
                row_vals = [str(row.get(col, "")).replace("\n", " ").strip() for col in columns]
                lines.append("| " + " | ".join(row_vals) + " |")

            if len(records) > max_rows:
                lines.append(f"... (dan {len(records) - max_rows} baris lainnya)")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to read table JSON at {table_path}: {e}")
            return None

    def _fast_sql_table_search(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Executes sub-5ms SQL index search on 21,368 tables in database/tables_index.db.
        Uses balanced multi-category retrieval to ensure no topic (meat, fish, rice, veg)
        gets starved or drowned out by year sorting.
        """
        db_path = settings.DATABASE_DIR / "tables_index.db"
        if not db_path.exists():
            return []

        import sqlite3
        ym = re.search(r"\b(201[0-9]|202[0-9])\b", query)
        year = ym.group(1) if ym else None

        ql = query.lower()
        # Normalize informal terms & typos
        ql = ql.replace("panggan", "pangan").replace("terdikit", "tersedikit").replace("banya", "banyak")

        kec = None
        for k in ['mranggen', 'sayung', 'karangawen', 'guntur', 'bonang', 'wedung', 'mijen', 'gajah', 'karanganyar', 'karangtengah', 'karang tengah', 'wonosalam', 'dempet', 'kebonagung']:
            if k in ql:
                kec = k.title()
                break
        if not kec and 'demak' in ql:
            kec = 'Demak'

        is_ranking = any(w in ql for w in ['terbanyak', 'tertinggi', 'terbesar', 'tersedikit', 'terdikit', 'terendah', 'paling', 'urutan', 'peringkat', 'mana'])
        categories = []

        # 1. Fishery
        if any(w in ql for w in ['ikan', 'perikanan', 'pelelangan', 'tambak', 'nelayan', 'udang', 'bandeng']):
            categories.append(('perikanan', ['perikanan', 'pelelangan', 'tambak', 'nelayan', 'ikan laut', 'ikan darat', 'ikan air', 'budidaya tambak', 'budidaya ikan', 'udang', 'bandeng']))

        # 2. Livestock / Meat
        if any(w in ql for w in ['daging', 'ternak', 'unggas', 'ayam', 'sapi', 'kambing', 'potong', 'pemotongan', 'rph']):
            categories.append(('peternakan', ['ternak', 'daging', 'pemotongan', 'potong', 'populasi ternak', 'unggas', 'rph']))

        # 3. Agriculture / Crops / Food Crops (Tanaman Pangan)
        if any(w in ql for w in ['padi', 'beras', 'gabah', 'panen', 'palawija', 'jagung', 'pangan', 'bahan pangan', 'tanaman pangan', 'pertanian', 'tani', 'hasil bumi', 'sembako']):
            categories.append(('tanaman_pangan', ['tanaman pangan', 'padi', 'panen', 'luas panen', 'produksi padi', 'palawija', 'jagung']))

        # 4. Horticulture / Vegetables
        if any(w in ql for w in ['sayur', 'hortikultura', 'cabai', 'bawang', 'buah', 'tomat', 'terung', 'kangkung']):
            categories.append(('hortikultura', ['sayur', 'hortikultura', 'cabai', 'bawang', 'buah']))

        # 5. Education
        if any(w in ql for w in ['sekolah', 'pendidikan', 'murid', 'guru', 'sd', 'smp', 'sma']):
            categories.append(('pendidikan', ['pendidikan', 'sekolah', 'murid', 'guru']))

        # 6. Health
        if any(w in ql for w in ['sehat', 'kesehatan', 'puskesmas', 'dokter', 'tenaga kesehatan']):
            categories.append(('kesehatan', ['kesehatan', 'puskesmas', 'tenaga kesehatan']))

        # 7. Population
        if any(w in ql for w in ['penduduk', 'kependudukan', 'jiwa', 'warga', 'kelahiran', 'kematian']):
            categories.append(('kependudukan', ['penduduk', 'kependudukan', 'sex ratio', 'kelahiran']))

        # 8. Poverty
        if any(w in ql for w in ['miskin', 'kemiskinan']):
            categories.append(('kemiskinan', ['kemiskinan', 'garis kemiskinan']))

        # 9. Macro Economy / PDRB (only if explicitly asked or no agro/livestock category present)
        if any(w in ql for w in ['pdrb', 'gdp', 'pertumbuhan ekonomi', 'inflasi', 'upah', 'gaji']):
            categories.append(('ekonomi', ['pdrb', 'per kapita', 'pengeluaran', 'upah', 'pertumbuhan ekonomi']))
        elif any(w in ql for w in ['pendapatan', 'penghasilan']) and not categories:
            categories.append(('ekonomi', ['pdrb', 'per kapita', 'pengeluaran', 'upah']))

        if not (year or kec or categories):
            return []

        try:
            results = []
            seen_paths = set()
            with sqlite3.connect(db_path, timeout=5) as conn:
                c = conn.cursor()
                per_cat_limit = max(3, limit // max(1, len(categories)))

                for cat_name, terms in categories:
                    sql = "SELECT table_path, doc_id, doc_title, tahun, kecamatan, judul_tabel FROM tables_catalog WHERE 1=1"
                    params = []

                    if cat_name != 'pendidikan':
                        sql += " AND judul_tabel NOT LIKE '%pendidikan%' AND judul_tabel NOT LIKE '%kepemilikan%' AND judul_tabel NOT LIKE '%diartikan%'"

                    if cat_name in ['perikanan', 'peternakan', 'tanaman_pangan', 'hortikultura']:
                        sql += " AND doc_title NOT LIKE '%Produk Domestik Regional Bruto%' AND doc_title NOT LIKE '%PDRB%'"

                    if year:
                        sql += " AND (tahun = ? OR doc_title LIKE ? OR judul_tabel LIKE ?)"
                        params.extend([year, f"%{year}%", f"%{year}%"])

                    if kec and kec != 'Demak':
                        sql += " AND (kecamatan LIKE ? OR doc_title LIKE ? OR doc_title LIKE '%Kabupaten Demak%')"
                        params.extend([f"%{kec}%", f"%{kec}%"])

                    conds = " OR ".join(["judul_tabel LIKE ?" for _ in terms])
                    sql += f" AND ({conds})"
                    params.extend([f"%{t}%" for t in terms])

                    # Prioritize exact kecamatan matches first, or ranking/comparative tables across kecamatan
                    if kec and kec != 'Demak':
                        sql += " ORDER BY (CASE WHEN kecamatan LIKE ? OR doc_title LIKE ? THEN 0 ELSE 1 END), tahun DESC"
                        params.extend([f"%{kec}%", f"%{kec}%"])
                    elif is_ranking:
                        sql += " ORDER BY (CASE WHEN judul_tabel LIKE '%kecamatan%' THEN 0 ELSE 1 END), tahun DESC"
                    else:
                        sql += " ORDER BY tahun DESC"

                    sql += f" LIMIT {per_cat_limit}"
                    c.execute(sql, params)
                    for r in c.fetchall():
                        tbl_path = r[0]
                        if tbl_path not in seen_paths:
                            seen_paths.add(tbl_path)
                            results.append({
                                "table_path": r[0],
                                "doc_id": r[1],
                                "doc_title": r[2],
                                "tahun": r[3],
                                "kecamatan": r[4],
                                "judul_tabel": r[5]
                            })
                return results
        except Exception as e:
            logger.debug(f"[RAGFeeder] Fast SQL search error: {e}")
            return []

    def feed_context(
        self,
        query: str,
        daerah: Optional[str] = None,
        tahun: Optional[str] = None,
        kategori: Optional[str] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Retrieves relevant statistical knowledge and compiles a feedable context package.
        Uses Hybrid Search: Sub-5ms SQL Table Indexer + Dense ChromaDB Vector Store.
        """
        top_k = top_k or bot_config.TOP_K_CHUNKS
        threshold = score_threshold if score_threshold is not None else bot_config.SCORE_THRESHOLD
        
        # Auto-detect year if not explicitly passed
        detected_year = tahun or self._extract_year_from_query(query)

        enriched_blocks = []
        citations = []
        seen_citations = set()
        seen_table_paths = set()

        # Step -1: Institutional BPS Profile & Leadership Match
        ql_lower = query.lower().replace("damak", "demak")
        if any(w in ql_lower for w in ['kepala bps', 'pimpinan bps', 'nama kepala', 'ketua bps', 'pejabat bps', 'siapa kepala', 'pemimpin bps']):
            leadership_chunk = {
                "chunk_id": "bps_leadership_profile",
                "score": 1.0,
                "dokumen_sumber": "Profil Pejabat Struktural BPS Kabupaten Demak (Publikasi Resmi BPS 2024-2025)",
                "tahun": "2025",
                "halaman": "Kata Pengantar & Profil Pimpinan",
                "daerah": "Kabupaten Demak",
                "kategori": "Profil Kelembagaan",
                "tipe_konten": "profil_pimpinan",
                "judul_tabel": "Profil Kepala BPS Kabupaten Demak",
                "representasi_teks": "Profil Kepala BPS Kabupaten Demak",
                "konten_lengkap": (
                    "PROFIL RESMI PIMPINAN BADAN PUSAT STATISTIK (BPS) KABUPATEN DEMAK:\n"
                    "1. Kepala BPS Kabupaten Demak saat ini (Tahun 2025 - Sekarang): Bapak Khomarudin, S.ST.\n"
                    "   (Tercatat secara resmi dalam Publikasi 'Kabupaten Demak Dalam Angka 2025' Halaman 9 dan 'Indikator Kesejahteraan Rakyat Kabupaten Demak 2025' Halaman 7).\n"
                    "2. Kepala BPS Kabupaten Demak periode sebelumnya (Tahun 2022 - 2024): Bapak Henri Wagiyanto, S.Pt., M.Ec.Dev., M.A.\n"
                    "   (Tercatat dalam 'Laporan Kinerja BPS Kabupaten Demak 2023' dan 'Indikator Kesejahteraan Rakyat Kabupaten Demak 2023-2024').\n"
                    "3. Kasubbag Umum: Moh Saiful Hidayah Brotowiyono, S.Si., M.M."
                ),
                "file_json_tabel": ""
            }
            enriched_blocks.append(leadership_chunk)
            citations.append({
                "dokumen": "Kabupaten Demak Dalam Angka 2025",
                "dokumen_sumber": "Kabupaten Demak Dalam Angka 2025",
                "tahun": "2025",
                "halaman": "Kata Pengantar (Hal. 9)",
                "judul_tabel": "Profil Kepala BPS Kabupaten Demak",
                "tipe": "profil_pimpinan",
                "tipe_konten": "profil_pimpinan"
            })

        # Step 0: Sub-5ms Direct Table Metadata Search from SQLite
        sql_tables = self._fast_sql_table_search(query, limit=5)
        for st in sql_tables:
            tbl_path = st["table_path"]
            preview = self._load_granular_table_preview(tbl_path, max_rows=bot_config.MAX_TABLE_ROWS_IN_CONTEXT)
            if preview:
                seen_table_paths.add(tbl_path)
                enriched_blocks.append({
                    "chunk_id": f"sql_{st['doc_id']}",
                    "score": 0.99,
                    "dokumen_sumber": st["doc_title"],
                    "tahun": st["tahun"],
                    "halaman": "Tabel Data",
                    "daerah": "Kabupaten Demak",
                    "kategori": "Data Statistik",
                    "tipe_konten": "tabel_lengkap",
                    "judul_tabel": st["judul_tabel"],
                    "representasi_teks": f"Tabel {st['judul_tabel']} ({st['doc_title']}, Tahun {st['tahun']})",
                    "konten_lengkap": preview,
                    "file_json_tabel": tbl_path
                })
                cit_key = f"{st['doc_title']}_{st['judul_tabel']}"
                if cit_key not in seen_citations:
                    seen_citations.add(cit_key)
                    citations.append({
                        "dokumen": st["doc_title"],
                        "tahun": st["tahun"],
                        "halaman": "Tabel Lengkap",
                        "judul_tabel": st["judul_tabel"],
                        "tipe": "tabel_lengkap"
                    })

        # 1. Generate dense query embedding
        logger.debug(f"[RAGFeeder] Vectorizing query: '{query}'")
        query_vector = self.embedder.generate_embeddings([query])[0]

        # 2. Search Vector Database with optional metadata pre-filtering
        results = self.vector_store.search_with_prefilter(
            query_embedding=query_vector,
            daerah=daerah,
            tahun=detected_year,
            kategori=kategori,
            n_results=top_k
        )

        # If strict year filter returned 0 results, retry without year filter as fallback
        if not results and detected_year:
            logger.info(f"[RAGFeeder] No results with year={detected_year}. Falling back to general search...")
            results = self.vector_store.search_with_prefilter(
                query_embedding=query_vector,
                daerah=daerah,
                tahun=None,
                kategori=kategori,
                n_results=top_k
            )

        for res in results:
            score = res.get("score")
            # If score exists and is below threshold, skip
            if score is not None and score < threshold:
                continue

            meta = res.get("metadata", {})
            tipe_konten = meta.get("tipe_konten", "teks")
            table_json_path = meta.get("file_json_tabel")
            
            # Enrich content: Read granular table if available
            full_content = None
            if bot_config.INCLUDE_FULL_TABLE_JSON and "tabel" in tipe_konten and table_json_path:
                full_content = self._load_granular_table_preview(
                    table_json_path,
                    max_rows=bot_config.MAX_TABLE_ROWS_IN_CONTEXT
                )

            if not full_content:
                full_content = res.get("representasi_teks", "")

            block_info = {
                "chunk_id": res.get("chunk_id"),
                "score": score,
                "dokumen_sumber": meta.get("dokumen_sumber", "Publikasi BPS"),
                "tahun": meta.get("tahun", "-"),
                "halaman": meta.get("halaman", "-"),
                "daerah": meta.get("daerah", "Kabupaten Demak"),
                "kategori": meta.get("kategori", "-"),
                "tipe_konten": tipe_konten,
                "judul_tabel": meta.get("judul_tabel", ""),
                "representasi_teks": res.get("representasi_teks", ""),
                "konten_lengkap": full_content,
                "file_json_tabel": table_json_path
            }
            enriched_blocks.append(block_info)

            # Build clean citation
            cit_key = f"{meta.get('dokumen_sumber')}_{meta.get('halaman')}_{meta.get('judul_tabel')}"
            if cit_key not in seen_citations:
                seen_citations.add(cit_key)
                citations.append({
                    "dokumen": meta.get("dokumen_sumber", "BPS"),
                    "tahun": meta.get("tahun", "-"),
                    "halaman": meta.get("halaman", "-"),
                    "judul_tabel": meta.get("judul_tabel", ""),
                    "tipe": tipe_konten
                })

        # 4. Format context text for prompt
        context_text = format_rag_context(enriched_blocks)

        logger.info(f"[RAGFeeder] Feeding {len(enriched_blocks)} chunks to AI Chatbot for query: '{query}'")

        return {
            "context_text": context_text,
            "chunks": enriched_blocks,
            "citations": citations,
            "total_retrieved": len(enriched_blocks)
        }
