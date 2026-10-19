# 🏛️ BPS AI Chatbot (RAG-Fed Statistical Assistant)

Modul kecerdasan buatan (AI Chatbot) berbasis **Retrieval-Augmented Generation (RAG)** yang terintegrasi langsung dengan basis data publikasi resmi **Badan Pusat Statistik (BPS)** Kabupaten Demak.

Chatbot ini bertindak sebagai **"Sahabat Data BPS"** yang menyajikan jawaban berbasis data faktual, dilengkapi dengan sitasi publikasi resmi, nomor halaman, dan judul tabel, serta menerapkan aturan ketat **anti-halusinasi**.

---

## 📐 Arsitektur Integrasi RAG Feeding

```
┌─────────────────────────────────────────────────────────────┐
│                    PERTANYAAN PENGGUNA                      │
│            "Berapa jumlah penduduk Kecamatan Sayung?"       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
 ┌───────────────────────────────────────────────────────────┐
 │               CHATBOT RAG FEEDER (rag_feeder.py)           │
 │ 1. Embed query (paraphrase-multilingual-MiniLM-L12-v2)    │
 │ 2. Semantic Search di Vector Store (ChromaDB / SQLite)    │
 └─────────────────────────────┬─────────────────────────────┘
                               │
          ┌────────────────────┴────────────────────┐
          ▼                                         ▼
┌───────────────────────────┐         ┌───────────────────────────┐
│       VECTOR CHUNKS       │         │   GRANULAR TABLE JSONs    │
│ Teks Naratif & Metadata   │         │ database/tables/{doc_id}/ │
│ Dokumen BPS               │         │ (Membaca baris & satuan)  │
└─────────┬─────────────────┘         └─────────────┬─────────────┘
          └────────────────────┬────────────────────┘
                               │
                               ▼
 ┌───────────────────────────────────────────────────────────┐
 │             PROMPT & CONTEXT INJECTION ENGINE             │
 │ - Menyusun Konteks Data BPS Terverifikasi                 │
 │ - Menerapkan Persona Resmi BPS & Anti-Hallucination Policy │
 │ - Menyuntikkan Riwayat Percakapan (Memory)                │
 └─────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
 ┌───────────────────────────────────────────────────────────┐
 │                  MULTI-PROVIDER LLM CLIENT                │
 │    Google Gemini  |  OpenAI  |  Groq  |  Ollama (Lokal)   │
 └─────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       JAWABAN AKHIR                         │
│ - Jawaban statistik akurat dengan satuan (jiwa, persen, dll)│
│ - 📚 Sumber Sitasi: Publikasi BPS, Halaman, Judul Tabel     │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Struktur Direktori `chatbot/`

```
chatbot/
├── __init__.py           # Package exports (BPSChatbot, RAGFeeder, LLMClient, dll)
├── config.py             # Konfigurasi chatbot & pemetaan environment variable
├── rag_feeder.py         # Jembatan RAG: Pencarian vektor + pembacaan tabel granular
├── prompt_templates.py   # System prompt resmi BPS, aturan anti-halusinasi & formatter konteks
├── llm_client.py         # Client HTTP multi-provider (Gemini, OpenAI, Groq, Ollama, Mock)
├── memory.py             # Pengelolaan riwayat percakapan multi-turn (sliding window)
├── bot.py                # Master Orchestrator (BPSChatbot)
├── cli.py                # Antarmuka CLI interaktif untuk uji coba via terminal
├── api.py                # Handler REST API (FastAPI / webhook ready)
└── README.md             # Dokumentasi lengkap modul chatbot
```

---

## ⚙️ Konfigurasi Environment (`.env`)

Chatbot dapat dikonfigurasi melalui file `.env` di direktori utama:

```bash
# Pilihan Provider LLM: gemini (default), openai, groq, ollama, mock
LLM_PROVIDER=gemini

# Jika menggunakan Google Gemini (Rekomendasi)
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-1.5-flash

# Jika menggunakan OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Jika menggunakan Groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant

# Jika menggunakan Local LLM (Ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Parameter Pengambilan RAG
TOP_K_CHUNKS=4
SCORE_THRESHOLD=0.30
MAX_TABLE_ROWS_IN_CONTEXT=20
```

> **Mode Dry-Run (Mock):** Jika belum memiliki API Key, Anda tetap dapat menjalankan chatbot. Chatbot akan otomatis mendeteksi ketiadaan API key dan menampilkan status konteks data yang berhasil di-feed tanpa terjadi crash.

---

## 🚀 Cara Menjalankan

### 1. Menjalankan Chatbot Interaktif di Terminal (CLI)

```bash
# Menggunakan konfigurasi default (.env)
python -m chatbot.cli

# Memaksa menggunakan provider tertentu
python -m chatbot.cli --provider gemini
python -m chatbot.cli --provider openai
python -m chatbot.cli --provider ollama

# Menampilkan data RAG yang di-feed ke AI secara langsung untuk debugging
python -m chatbot.cli --show-context
```

**Perintah Khusus dalam Sesi CLI:**
- `/exit` atau `/quit`: Keluar dari sesi.
- `/clear`: Menghapus riwayat percakapan.
- `/context`: Menampilkan teks data RAG terakhir yang diinjeksikan ke LLM.
- `/citations`: Menampilkan daftar dokumen dan tabel rujukan BPS.

---

### 2. Menggunakan Chatbot di Kode Python

```python
from chatbot import BPSChatbot

# Inisialisasi chatbot
bot = BPSChatbot()

# Ajukan pertanyaan
result = bot.ask(
    question="Berapa jumlah penduduk di Kabupaten Demak pada tahun 2024?",
    session_id="user_123"  # Opsional untuk multi-user
)

# Output jawaban
print("Jawaban:")
print(result["answer"])

# Output sitasi sumber
print("\nSumber Publikasi BPS:")
for cit in result["citations"]:
    print(f"- {cit['dokumen']} (Tahun {cit['tahun']}, Hal. {cit['halaman']})")
```

---

### 3. Integrasi ke Web API (FastAPI)

Jika Anda memiliki `fastapi` dan `uvicorn`, jalankan server API:

```bash
uvicorn chatbot.api:app --host 0.0.0.0 --port 8000 --reload
```

Kirimkan HTTP POST ke `http://localhost:8000/api/chat`:
```json
{
  "message": "Data kemiskinan di Demak",
  "session_id": "session_abc"
}
```

---

## 🛡️ Kebijakan Anti-Halusinasi & Integritas Data

1. **Strict Context Adherence**: Chatbot hanya memproses data dari `[KONTEKS DATA BPS TERVERIFIKASI]` yang di-retrieval dari Vector DB dan JSON tabel granular.
2. **Explicit Uncertainty**: Jika data kecamatan, tahun, atau kategori tidak ditemukan, AI diinstruksikan untuk menyatakan ketiadaan data secara jujur dan tidak mengarang angka.
3. **Unit Enforcement**: Mengharuskan penyebutan satuan (jiwa, persen, ton, kkal, dll) agar interpretasi data statistik tidak rancu.
4. **Mandatory Citations**: Menyertakan judul buku publikasi resmi BPS dan halaman/tabel asalnya di setiap jawaban.
