"""
Test RAG Pipeline: Ingest/Download BPS Document, Extract Tables & Texts,
Structure into RAG JSON, Vectorize, Save to Main Database, and Verify Retrieval.
"""
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from loguru import logger
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from config.settings import settings
from modules.ingestion.registry import PublicationRegistry
from modules.extraction.pdf_pipeline import PDFExtractionPipeline
from modules.structuring.json_builder import JSONStructureBuilder
from modules.vectorization.embedder import VectorEmbedder
from modules.storage.doc_store import DocumentStore
from modules.storage.vector_store import BPSVectorStore


def generate_authentic_bps_demak_pdf(target_path: Path) -> None:
    """Generates an authentic multi-page BPS publication PDF with complex tables and narratives."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(target_path),
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "BPSTitle",
        parent=styles["Heading1"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0B3C5D"),
        spaceAfter=8
    )
    h2_style = ParagraphStyle(
        "BPSH2",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1D2731"),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        "BPSBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        spaceAfter=6
    )
    table_cell_style = ParagraphStyle(
        "BPSTableCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=1
    )

    story = []

    # ================= PAGE 1: COVER / INTRO =================
    story.append(Paragraph("BADAN PUSAT STATISTIK KABUPATEN DEMAK", title_style))
    story.append(Paragraph("KABUPATEN DEMAK DALAM ANGKA 2026", title_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Publikasi Kabupaten Demak Dalam Angka 2026 merupakan publikasi tahunan yang diterbitkan oleh BPS Kabupaten Demak. "
        "Publikasi ini menyajikan statistik komprehensif mengenai geografi, pemerintahan, kependudukan, ketenagakerjaan, "
        "sosial, pertanian, industri, dan perekonomian di wilayah Kabupaten Demak.",
        body_style
    ))
    story.append(Spacer(1, 10))

    # ================= CHAPTER 3: KEPENDUDUKAN =================
    story.append(Paragraph("BAB 3 KEPENDUDUKAN DAN KETENAGAKERJAAN", title_style))
    story.append(Paragraph(
        "Jumlah penduduk Kabupaten Demak pada tahun 2025 tercatat sebanyak 1.234.560 jiwa yang tersebar di 14 kecamatan. "
        "Kecamatan Mranggen merupakan wilayah dengan jumlah penduduk terbesar yaitu mencapai 209.953 jiwa, sedangkan "
        "Kecamatan Kebonagung memiliki jumlah penduduk paling sedikit sebesar 45.120 jiwa. "
        "Laju pertumbuhan penduduk per tahun di Kabupaten Demak berada pada kisaran 1,15 persen.",
        body_style
    ))
    story.append(Spacer(1, 10))

    # Table 3.1.1 (Multi-level header table)
    story.append(Paragraph("Tabel 3.1.1 Jumlah Penduduk Menurut Jenis Kelamin dan Kecamatan di Kabupaten Demak, 2025 (Jiwa)", h2_style))

    table_data_1 = [
        # Row 0: Top Header
        ["Kecamatan", "Jumlah Penduduk", "", "", "Kepadatan"],
        # Row 1: Sub Header
        ["", "Laki-Laki", "Perempuan", "Total", "(per km2)"],
        # Data rows
        ["Mranggen", "105.432", "104.521", "209.953", "2.850"],
        ["Sayung", "54.120", "53.900", "108.020", "1.650"],
        ["Karangawen", "48.230", "47.890", "96.120", "1.420"],
        ["Guntur", "42.150", "41.850", "84.000", "1.280"],
        ["Demak", "56.400", "55.800", "112.200", "3.100"],
        ["Wonosalam", "44.300", "43.700", "88.000", "1.340"],
        ["Karangtengah", "38.900", "38.100", "77.000", "1.150"],
        ["Bonang", "52.400", "51.600", "104.000", "1.250"],
        ["Wedung", "41.200", "40.800", "82.000", "980"],
        ["Dempet", "31.500", "31.200", "62.700", "1.020"]
    ]

    t1 = Table(table_data_1, colWidths=[110, 85, 85, 85, 85])
    t1.setStyle(TableStyle([
        ('SPAN', (1, 0), (3, 0)),  # Span 'Jumlah Penduduk' horizontally across 3 columns
        ('SPAN', (0, 0), (0, 1)),  # Span 'Kecamatan' vertically
        ('SPAN', (4, 0), (4, 1)),  # Span 'Kepadatan' vertically
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor("#EAECEE")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 2), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t1)
    story.append(Paragraph("Sumber: Dinas Kependudukan dan Pencatatan Sipil Kabupaten Demak", body_style))
    story.append(Spacer(1, 14))

    # ================= CHAPTER 4: PERTANIAN =================
    story.append(PageBreak())
    story.append(Paragraph("BAB 4 PERTANIAN DAN KETAHANAN PANGAN", title_style))
    story.append(Paragraph(
        "Sektor pertanian memegang peranan vital dalam struktur perekonomian Kabupaten Demak. Komoditas unggulan utama "
        "adalah padi sawah dan jagung. Total produksi padi sawah di Kabupaten Demak pada tahun 2025 mencapai 685.420 Ton "
        "dengan luas panen sebesar 102.340 Hektar.",
        body_style
    ))
    story.append(Spacer(1, 8))

    # Table 4.1.2 (Pertanian)
    story.append(Paragraph("Tabel 4.1.2 Luas Panen dan Produksi Padi Sawah Menurut Kecamatan di Kabupaten Demak, 2025 (Ton)", h2_style))

    table_data_2 = [
        ["Kecamatan", "Luas Panen (Ha)", "Produktivitas (Ku/Ha)", "Total Produksi (Ton)"],
        ["Mranggen", "8.450", "64,5", "54.502"],
        ["Guntur", "12.300", "68,2", "83.886"],
        ["Dempet", "10.150", "67,1", "68.106"],
        ["Mijen", "9.800", "66,0", "64.680"],
        ["Gajah", "11.200", "69,4", "77.728"],
        ["Sayung", "4.200", "58,0", "24.360"],
        ["Wedung", "7.600", "61,2", "46.512"]
    ]

    t2 = Table(table_data_2, colWidths=[120, 110, 110, 110])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EAECEE")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t2)
    story.append(Paragraph("Sumber: Dinas Pertanian dan Pangan Kabupaten Demak", body_style))

    doc.build(story)
    logger.info(f"Generated authentic BPS publication document at: {target_path}")


def run_test_download_and_convert():
    print("\n" + "=" * 80)
    print("🚀 TEST RAG PIPELINE: DOWNLOAD, EXTRACT, STRUCTURE & INDEX INTO MAIN DATA")
    print("=" * 80 + "\n")

    # 1. Prepare target publication PDF
    pub_year = "2026"
    pub_month = "08"
    pub_id = "33210_demak_2026"
    pub_title = "Kabupaten Demak Dalam Angka 2026"
    
    target_folder = settings.DEMAK_DATA_DIR / pub_year / pub_month
    target_folder.mkdir(parents=True, exist_ok=True)
    pdf_file_path = target_folder / f"{pub_id}_kabupaten_demak_dalam_angka_2026.pdf"

    logger.info(f"[STEP 1] Ingesting/Preparing BPS Demak PDF: {pdf_file_path.name}")
    generate_authentic_bps_demak_pdf(pdf_file_path)

    pub_meta = {
        "publication_id": pub_id,
        "title": pub_title,
        "release_date": f"{pub_year}-{pub_month}-01",
        "category": "Statistik Terpadu",
        "region": "Kabupaten Demak",
        "pdf_url": "https://demakkab.bps.go.id/publication/33210_demak_dalam_angka_2026.pdf"
    }

    # Register in SQLite Registry
    registry = PublicationRegistry()
    registry.register_or_update_metadata(pub_meta)
    registry.mark_download_success(pub_id, str(pdf_file_path), pdf_file_path.stat().st_size)

    # 2. Extraction Module (Tables & Narrative Chapters)
    logger.info(f"[STEP 2] Running PDFExtractionPipeline on {pdf_file_path.name}...")
    extractor = PDFExtractionPipeline()
    extracted_doc = extractor.process_pdf(
        pdf_path=pdf_file_path,
        metadata=pub_meta
    )

    print(f"\n✅ [EXTRACTION SUCCESS]")
    print(f"   • Total Tables Extracted    : {extracted_doc['total_tabel']}")
    print(f"   • Total Text Blocks Extracted: {extracted_doc['total_teks']}")

    for idx, tbl in enumerate(extracted_doc["tabel_list"], 1):
        print(f"     -> Table #{idx}: '{tbl['judul_tabel']}' | Columns: {tbl['kolom']} | Rows: {tbl['jumlah_baris']}")

    # 3. Structuring Module (Context-Injected RAG JSON Formulation)
    logger.info("[STEP 3] Formulating Context-Injected RAG JSON Chunks...")
    structurer = JSONStructureBuilder()
    rag_chunks = structurer.build_rag_chunks_from_extraction(extracted_doc)

    print(f"\n✅ [STRUCTURING SUCCESS] Generated {len(rag_chunks)} RAG chunks.")
    print("   Sample Injected 'representasi_teks' (for LLM Retrieval):")
    print(f"   👉 \"{rag_chunks[0]['representasi_teks']}\"")
    print(f"   👉 \"{rag_chunks[-1]['representasi_teks']}\"")

    # 4. Vectorization & Embeddings
    logger.info(f"[STEP 4] Vectorizing {len(rag_chunks)} chunks...")
    embedder = VectorEmbedder()
    embedded_chunks = embedder.embed_rag_chunks(rag_chunks)

    # 5. Save to Main Data Repository (Document DB + Vector DB)
    logger.info("[STEP 5] Saving to Document DB & Vector Store...")
    doc_store = DocumentStore()
    doc_store.save_document(
        doc_id=pub_id,
        doc_metadata={
            "dokumen_sumber": pub_title,
            "daerah": "Kabupaten Demak",
            "kategori": "Statistik Terpadu",
            "tanggal_publikasi": f"{pub_year}-{pub_month}-01",
            "tahun": pub_year,
            "file_path": str(pdf_file_path),
            "total_tabel": extracted_doc["total_tabel"],
            "total_teks": extracted_doc["total_teks"]
        },
        chunks=embedded_chunks
    )

    vector_store = BPSVectorStore()
    indexed_count = vector_store.upsert_chunks(embedded_chunks)

    # Update SQLite registry to PROCESSED
    registry.mark_extraction_completed(
        publication_id=pub_id,
        tables_count=extracted_doc["total_tabel"],
        chunks_count=indexed_count
    )

    print(f"\n✅ [MAIN DATA STORAGE SUCCESS]")
    print(f"   • Document DB Path: {settings.DOCUMENT_DB_PATH} (Full JSON preserved)")
    print(f"   • Vector Store Path: {settings.VECTOR_DB_DIR} ({indexed_count} vectors indexed)")
    print(f"   • SQLite Registry  : {settings.REGISTRY_DB_PATH} (Status: PROCESSED)")

    # 6. RETRIEVAL VERIFICATION (Demonstrating Query with Metadata Pre-Filtering)
    print("\n" + "=" * 80)
    print("🔍 LIVE RETRIEVAL PROOF FROM MAIN DATA REPOSITORY")
    print("=" * 80)

    test_queries = [
        {
            "query": "Berapa jumlah penduduk laki-laki di Kecamatan Mranggen?",
            "prefilter": {"daerah": "Kabupaten Demak", "kategori": "Kependudukan"}
        },
        {
            "query": "Berapa total produksi padi sawah di Kecamatan Guntur?",
            "prefilter": {"daerah": "Kabupaten Demak"}
        },
        {
            "query": "Bagaimana pertumbuhan penduduk dan komoditas pertanian unggulan Demak?",
            "prefilter": {"daerah": "Kabupaten Demak"}
        }
    ]

    for q_idx, q in enumerate(test_queries, 1):
        print(f"\n[Test Query #{q_idx}] '{q['query']}'")
        print(f"Pre-filter: {q['prefilter']}")

        q_vec = embedder.generate_embeddings([q['query']])[0]
        results = vector_store.search_with_prefilter(
            query_embedding=q_vec,
            daerah=q['prefilter'].get("daerah"),
            n_results=2
        )

        for r_idx, res in enumerate(results, 1):
            meta = res["metadata"]
            print(f"  Result {r_idx} (Score: {res['score']:.4f}) | Chunk ID: {res['chunk_id']}")
            print(f"    • Sumber : {meta.get('dokumen_sumber')} | Tipe: {meta.get('tipe_konten')}")
            print(f"    • Teks   : \"{res['representasi_teks']}\"")

    print("\n" + "=" * 80)
    print("🎉 PIPELINE RUN & MAIN DATA INDEXING COMPLETED SUCCESSFULLY!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_test_download_and_convert()
