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
        ▼ (Module 5a: Granular JSON Storage)              ▼ (Module 5b: Vector DB)
[ 1 JSON Per Tabel: database/tables/{doc_id}/ ]     [ ChromaDB / SQLite Vector Store ]
[ 1 JSON Per PDF  : database/documents/{doc_id}.json ] (Vectors point directly to table JSONs)
[ 1 JSON Per Teks : database/narratives/{doc_id}/ ]
```

---

## Granular JSON Storage (Anti-Token Blowout)

To prevent LLM context-window exhaustion and hallucinations, the pipeline does NOT dump entire books into a single monolithic JSON file. Instead, it generates granular, self-contained files:

1. **1 File JSON Per Tabel (`database/tables/{doc_id}/tabel_{tabel_id}.json`)**:
   Contains table headers, cleaned records, row-level natural language representations, units, sources, and chunk IDs (~2-5 KB).
2. **1 File JSON Per PDF (`database/documents/{doc_id}.json`)**:
   Contains document metadata, list of extracted table JSON file paths, list of narrative JSON file paths, and chunk summaries.
3. **1 File JSON Per Narasi (`database/narratives/{doc_id}/naratif_{idx}.json`)**:
   Contains chapter and paragraph-level narrative text blocks.
4. **Direct Vector-to-JSON Linking**:
   When Vector Search retrieves relevant chunks, it returns the direct file path to the corresponding table JSON (`file_json_tabel`), allowing AI agents to read only the target table without loading the whole publication.

---

## 🤖 AI Chatbot (RAG-Fed Assistant)

Sistem ini telah dilengkapi modul AI Chatbot mandiri di dalam folder [`chatbot/`](chatbot/README.md) yang mengonsumsi data dari pipeline RAG secara langsung.

### Menjalankan Chatbot:
```bash
# Jalankan sesi percakapan interaktif di CLI
python -m chatbot.cli
```

### Konfigurasi API LLM:
Salin file `.env.example` menjadi `.env`, lalu masukkan API Key (misal: Google Gemini atau OpenAI):
```bash
copy .env.example .env
```
Untuk dokumentasi arsitektur dan opsi API selengkapnya, lihat [Dokumentasi Chatbot](chatbot/README.md).
