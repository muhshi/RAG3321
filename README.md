# BPS Demak Automated ETL & RAG Vectorization Pipeline

A production-grade, automated Data Pipeline (ETL) and Indexing System designed for Retrieval-Augmented Generation (RAG) over Badan Pusat Statistik (BPS) publications (Kabupaten Demak).

---

## Operational Modes

The master orchestrator (`main.py`) supports three distinct operational modes via `--mode`:

### 1. `statis` (Default)
Periodic incremental ingestion. Scrapes the first 2 pages of the BPS catalog, downloads only new publications (verified against SQLite registry), and indexes them into the Document & Vector databases.
```bash
python main.py --mode statis
```

### 2. `all`
Deep historical crawl. Scrapes up to 50 pages of the BPS catalog and downloads/indexes all unindexed publications.
```bash
python main.py --mode all
# Or with custom depth:
python main.py --mode all --max-pages 20
```

### 3. `test`
Single-document verification run. Fetches page 1, acquires the latest document, parses, structures, vectorizes, stores, and executes an automated semantic search retrieval proof.
```bash
python main.py --mode test
```

---

## On-Demand Utilities

### Direct Single PDF Processing
```bash
python main.py --pdf "data_publikasi/demak/2026/01/sample_demak_test.pdf"
```

### On-Demand Semantic Search with Metadata Pre-filtering
```bash
python main.py --query "Berapa jumlah penduduk di Kecamatan Mranggen?" --filter-kategori Kependudukan --filter-tahun 2026
```

---

## System Architecture

```
[ BPS Demak Portal ]
        │
        ▼ (Module 1: Ingestion)
[ SQLite Deduplication Registry ] ──> Downloads only new PDFs to /data_publikasi/demak/YYYY/MM/
        │
        ▼ (Module 2: Extraction)
[ PDF Extractor (pdfplumber) ] ──> Multi-level header flattening + forward-fill (ffill) + BPS numeric sanitization
        │
        ▼ (Module 3: Structuring)
[ JSON Formulation Engine ] ──> Injects context + generates dynamic natural language 'representasi_teks'
        │
        ▼ (Module 4: Vectorization)
[ SentenceTransformers Embedder ] ──> Generates normalized dense vectors (paraphrase-multilingual-MiniLM-L12-v2)
        │
        ├─────────────────────────────────────────────────┐
        ▼ (Module 5a: Document DB)                        ▼ (Module 5b: Vector DB)
[ JSON Document Store (Full Metadata) ]         [ ChromaDB / SQLite Vector Store (Pre-filters) ]
```
