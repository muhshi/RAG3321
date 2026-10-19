"""
Interactive CLI Interface for BPS AI Chatbot.
Enables real-time command-line conversations fed directly by BPS RAG knowledge.
"""
import sys
import argparse
from typing import Optional

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from loguru import logger

# Keep terminal console completely clean for interactive chat
logger.remove()
try:
    logger.add("logs/chatbot.log", rotation="10 MB", level="DEBUG")
except Exception:
    pass

from chatbot.config import bot_config
from chatbot.llm_client import LLMClient
from chatbot.rag_feeder import RAGFeeder
from chatbot.bot import BPSChatbot


def print_banner():
    banner = """
================================================================================
🏛️  SAHABAT DATA BPS — ASISTEN KECERDASAN BUATAN BPS KABUPATEN DEMAK
================================================================================
Perintah Khusus:
  /exit atau /quit : Keluar dari sesi chat
  /clear           : Menghapus riwayat percakapan
  /context         : Melihat data RAG terakhir yang di-feed ke AI
  /citations       : Melihat daftar dokumen & tabel referensi resmi
================================================================================
"""
    print(banner)


def print_welcome_introduction(provider_name: str, daerah: str):
    intro = f"""
🤖 Sahabat Data BPS:
Halo! Selamat datang di layanan cerdas Sahabat Data BPS. 👋

Saya adalah asisten kecerdasan buatan resmi untuk layanan informasi statistik,
khususnya untuk wilayah {daerah}. 

Anda dapat mengobrol santai dengan saya atau bertanya mengenai berbagai hal:
  📊 Data Statistik Faktual : "Berapa jumlah penduduk di Demak tahun 2023?"
  📈 Indikator Pembangunan  : "Bagaimana tingkat kemiskinan dan IPM di Demak?"
  🌾 Sektor Pertanian       : "Berapa luas panen dan produksi padi di Demak?"
  📖 Konsep & Metodologi    : "Apa itu garis kemiskinan dan bagaimana cara BPS mengukurnya?"

Ada yang bisa saya bantu untuk Anda hari ini? Silakan ketik pertanyaan Anda di bawah!
--------------------------------------------------------------------------------
"""
    print(intro)


def run_cli():
    parser = argparse.ArgumentParser(description="CLI Interaktif Chatbot BPS (RAG-Fed)")
    parser.add_argument("--provider", type=str, default=None, help="LLM Provider (gemini, openai, groq, ollama, mock)")
    parser.add_argument("--daerah", type=str, default=None, help="Filter daerah default (misal: 'Kabupaten Demak')")
    parser.add_argument("--show-context", action="store_true", help="Tampilkan detail RAG feeding setiap ada pertanyaan")
    args = parser.parse_args()

    llm = LLMClient(provider=args.provider)
    feeder = RAGFeeder()
    bot = BPSChatbot(feeder=feeder, llm_client=llm, warmup_background=True)

    target_daerah = args.daerah or bot_config.DEFAULT_REGION

    print_banner()
    print_welcome_introduction(llm.provider.upper(), target_daerah)

    last_response = None
    session_id = "cli_session"

    while True:
        try:
            user_input = input("\n👤 Pengguna > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSampai jumpa! Terima kasih telah menggunakan Sahabat Data BPS.")
            break

        if not user_input:
            continue

        # Handle Slash Commands
        cmd = user_input.lower()
        if cmd in ("/exit", "/quit", "exit", "quit"):
            print("Sampai jumpa! Layanan Sahabat Data BPS ditutup.")
            break
        elif cmd == "/clear":
            bot.clear_memory(session_id)
            print("🧹 Riwayat percakapan berhasil dibersihkan.")
            continue
        elif cmd == "/context":
            if last_response and last_response.get("context_fed"):
                print("\n" + "=" * 60)
                print("📄 [DATA RAG YANG DI-FEED KE AI]")
                print("=" * 60)
                print(last_response["context_fed"])
                print("=" * 60)
            else:
                print("Belum ada query data RAG yang dijalankan pada sesi ini.")
            continue
        elif cmd == "/citations":
            if last_response and last_response.get("citations"):
                print("\n" + "=" * 60)
                print("📚 [DAFTAR SITASI / RUJUKAN PUBLIKASI BPS]")
                print("=" * 60)
                for idx, cit in enumerate(last_response["citations"], 1):
                    print(f"{idx}. {cit['dokumen']} (Tahun {cit['tahun']}, Hal. {cit['halaman']})")
                    if cit.get("judul_tabel"):
                        print(f"   Tabel: {cit['judul_tabel']}")
                print("=" * 60)
            else:
                print("Belum ada sitasi statistik pada pertanyaan terakhir.")
            continue

        # Process question
        print("⏳ Sedang memproses jawaban...")
        response = bot.ask(
            question=user_input,
            session_id=session_id,
            daerah=args.daerah
        )
        last_response = response

        # Print debug context if flag is active
        if args.show_context and response.get("context_fed"):
            print("\n[DEBUG] RAG Context Injected:")
            print(response["context_fed"])

        # Print AI Response
        print(f"\n🤖 Sahabat Data BPS:\n{response['answer']}")

        # Print citation badges only if there are actual document citations
        if response.get("citations"):
            print("\n📌 Rujukan Resmi:")
            for cit in response["citations"][:3]:
                doc_title = cit.get("dokumen") or cit.get("dokumen_sumber") or "Publikasi Resmi BPS"
                hal = cit.get("halaman", "-")
                print(f"  • {doc_title} (Hal. {hal})")


if __name__ == "__main__":
    run_cli()
