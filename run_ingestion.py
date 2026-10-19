import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger
from main import BPSPipelineOrchestrator

def main():
    print("\n" + "=" * 75)
    print("      🚀 PIPELINE INGESTION & EKSTRAKSI BPS KABUPATEN DEMAK (FULL)")
    print("=" * 75 + "\n")

    orchestrator = BPSPipelineOrchestrator()

    # Step 1: Check pending downloads
    with orchestrator.registry._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM publications WHERE download_status = 'PENDING'")
        pending_downloads = [dict(row) for row in cursor.fetchall()]

    if pending_downloads:
        print(f"📥 Ditemukan {len(pending_downloads)} publikasi yang perlu diunduh dari BPS...")
        for idx, pub in enumerate(pending_downloads, 1):
            title = pub["title"]
            pid = pub["publication_id"]
            print(f"  [{idx}/{len(pending_downloads)}] Mengunduh: {title[:60]}...")
            try:
                pdf_path = orchestrator.scraper.download_pdf(pub)
                if pdf_path and pdf_path.exists():
                    print(f"       ✓ Berhasil: {pdf_path.name} ({pdf_path.stat().st_size:,} bytes)")
                else:
                    print(f"       ✗ Gagal mengunduh berkas dari server BPS.")
            except Exception as e:
                print(f"       ✗ Error: {e}")
    else:
        print("✓ Seluruh berkas PDF publikasi sudah terunduh di lokal.")

    # Step 2: Check pending extractions
    pending_extractions = orchestrator.registry.get_pending_extractions()
    total_pending = len(pending_extractions)

    if not pending_extractions:
        print("\n🎉 SEMUA DATA PUBLIKASI SUDAH 100% SELESAI DIEKSTRAKSI & DIINDEX!")
    else:
        print(f"\n⚙️  Sisa publikasi yang perlu diekstraksi ke JSON tabel & Vektor: {total_pending} dokumen.\n")

        for idx, pub in enumerate(pending_extractions, 1):
            title = pub.get("title", "")
            pid = pub.get("publication_id", "")
            fpath = Path(pub.get("local_file_path", ""))

            if not fpath.exists():
                print(f"  [{idx}/{total_pending}] ⚠️ Berkas tidak ditemukan: {fpath.name}")
                continue

            print(f"  [{idx}/{total_pending}] Mengekstrak: {title[:65]}...")
            print(f"       File PDF : {fpath.name}")

            start_t = time.time()
            try:
                res = orchestrator.process_single_pdf(fpath, metadata=pub)
                elapsed = time.time() - start_t
                chunks = res.get("chunks_count", 0)
                print(f"       ✓ Sukses : {chunks:,} chunks RAG diindeks ke ChromaDB ({elapsed:.1f} detik)\n")
            except Exception as e:
                print(f"       ✗ Error saat ekstraksi: {e}\n")

    # Step 3: Final Audit Summary
    with orchestrator.registry._get_connection() as conn:
        c = conn.cursor()
        total_in_db = c.execute("SELECT count(*) FROM publications").fetchone()[0]
        proc_in_db = c.execute("SELECT count(*) FROM publications WHERE extraction_status = 'PROCESSED'").fetchone()[0]

    tables_dir = Path("database/tables")
    total_tbl_folders = len([d for d in tables_dir.iterdir() if d.is_dir()]) if tables_dir.exists() else 0
    total_tbl_files = sum(len(list(d.glob("*.json"))) for d in tables_dir.iterdir() if d.is_dir()) if tables_dir.exists() else 0
    chroma_count = orchestrator.vector_store.collection.count() if hasattr(orchestrator.vector_store, 'collection') else 0

    print("=" * 75)
    print("                    📊 LAPORAN AKHIR REKAPITULASI DATA")
    print("=" * 75)
    print(f"  • Total Publikasi di Registri   : {total_in_db} publikasi")
    print(f"  • Publikasi Selesai Diproses    : {proc_in_db}/{total_in_db}")
    print(f"  • Total Folder Publikasi Tabel  : {total_tbl_folders} folder")
    print(f"  • Total File JSON Tabel Mandiri : {total_tbl_files:,} file JSON")
    print(f"  • Total Vektor di ChromaDB      : {chroma_count:,} embeddings")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    main()
