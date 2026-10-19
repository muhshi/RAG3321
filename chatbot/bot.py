"""
Master AI Chatbot Orchestrator for BPS Data Knowledge.
Coordinates RAG Feeding, Conversational Intelligence, Prompt Composition, LLM Invocation, and Citations.
"""
import re
import threading
from typing import Optional, Dict, Any, List
from loguru import logger

from chatbot.config import bot_config
from chatbot.rag_feeder import RAGFeeder
from chatbot.llm_client import LLMClient
from chatbot.memory import SessionManager
from chatbot.prompt_templates import (
    BPS_SYSTEM_PROMPT,
    DATA_QUERY_PROMPT_TEMPLATE,
    CONVERSATIONAL_PROMPT_TEMPLATE
)


def is_conversational_or_greeting(text: str) -> bool:
    """
    Detects if a user message is a greeting, small talk, identity inquiry,
    or general conversational discussion that should bypass heavy vector database retrieval.
    Uses strict whole-word matching to avoid false substring triggers (e.g. 'siap' inside 'siapa').
    """
    clean = text.lower().strip()
    clean_no_punct = re.sub(r"[^\w\s]", " ", clean)
    words = set(clean_no_punct.split())
    
    if not words:
        return True

    # Bot identity inquiries ('siapa kamu', 'siapa anda', etc.) are conversational
    bot_identity_signals = [
        "siapa kamu", "kamu siapa", "kamu apa", "siapa anda",
        "bisa bantu apa", "bisa apa", "kamu bisa apa", "apa yang bisa kamu lakukan",
        "apa kabar", "gimana kabarnya", "perkenalkan", "kenalan",
        "apa fungsi bps", "apa tugas bps", "apa itu bps", "apa kepanjangan bps"
    ]
    if any(p in clean for p in bot_identity_signals):
        return True

    # Real inquiries about people, leaders, institutions, or data MUST go to RAG
    inquiry_keywords = [
        "siapa", "kepala", "pimpinan", "pejabat", "kantor", "alamat", "berapa", "jumlah",
        "angka", "data statistik", "tabel", "grafik", "penduduk", "kemiskinan", "pdrb",
        "inflasi", "panen", "produksi", "ipm", "pengangguran", "ihk", "ntp", "kecamatan",
        "desa", "luas lahan", "garis kemiskinan", "padi", "sayur", "ikan", "daging", "ternak",
        "pangan", "pertanian"
    ]
    if any(k in clean for k in inquiry_keywords):
        return False

    # Standalone 1-3 word greetings and courtesies
    single_word_signals = {
        "halo", "hai", "hei", "hi", "hello", "pagi", "siang", "sore", "malam",
        "assalamualaikum", "terima kasih", "makasih", "thanks", "ok", "oke", "sip",
        "mantap", "keren", "siap"
    }
    if words.intersection(single_word_signals) and len(words) <= 3:
        return True

    return False


class BPSChatbot:
    """
    Enterprise Chatbot for Badan Pusat Statistik (BPS) publications,
    powered by an automated RAG retrieval and tabular injection pipeline.
    Supports both natural conversational dialogue and strict data grounding.
    """

    def __init__(
        self,
        feeder: Optional[RAGFeeder] = None,
        llm_client: Optional[LLMClient] = None,
        warmup_background: bool = True
    ):
        self.feeder = feeder or RAGFeeder()
        self.llm = llm_client or LLMClient()
        self.session_manager = SessionManager()
        logger.info(f"BPS Chatbot initialized. Provider: '{self.llm.provider}'")

        # Warm up the embedder model in a non-blocking background thread
        if warmup_background:
            threading.Thread(target=self._async_warmup, daemon=True).start()

    def _async_warmup(self) -> None:
        """Pre-loads vector embedder weights asynchronously without blocking startup."""
        logger.debug("[BPSChatbot] Starting background warmup for vector embedder...")
        self.feeder.warm_up()
        logger.debug("[BPSChatbot] Background warmup completed.")

    def _resolve_followup_query(self, question: str, history: List[Dict[str, str]]) -> str:
        """
        Resolves conversational follow-up questions (e.g. 'yang di tahun 2023 ada gak ?')
        into an effective search query using the topic of previous turns.
        """
        if not history:
            return question

        last_user_query = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                last_user_query = msg.get("content", "").strip()
                break

        if not last_user_query:
            return question

        ql = question.lower().strip()
        # Check if the question already has an independent statistical topic
        primary_topics = [
            'daging', 'ternak', 'unggas', 'sapi', 'kambing', 'potong', 'pemotongan', 'rph',
            'ikan', 'perikanan', 'pelelangan', 'tambak', 'nelayan', 'budidaya',
            'padi', 'beras', 'gabah', 'panen', 'pangan', 'panggan', 'pertanian',
            'sayur', 'hortikultura', 'cabai', 'bawang',
            'pendapatan', 'penghasilan', 'income', 'gaji', 'upah',
            'penduduk', 'kependudukan', 'kemiskinan', 'miskin',
            'sekolah', 'pendidikan', 'kesehatan', 'puskesmas',
            'kepala', 'pimpinan', 'pejabat', 'pimpinan bps', 'nama', 'profil', 'struktur', 'kantor', 'alamat'
        ]
        has_independent_topic = any(t in ql for t in primary_topics)
        if has_independent_topic:
            return question

        followup_signals = [
            "yang di", "kalo di", "kalau di", "kalo", "kalau", "bagaimana", "gimana",
            "ada gak", "ada tidak", "ada ga", "berapa", "tahun", "di tahun",
            "kecamatan", "ini", "itu", "tersebut", "nya"
        ]
        is_short = len(ql.split()) <= 7
        is_followup = any(s in ql for s in followup_signals) or is_short

        if not is_followup:
            return question

        year_match = re.search(r"\b(201[0-9]|202[0-9])\b", ql)
        new_year = year_match.group(1) if year_match else None

        kecamatans = [
            'mranggen', 'sayung', 'karangawen', 'guntur', 'bonang', 'wedung',
            'mijen', 'gajah', 'karanganyar', 'karangtengah', 'wonosalam',
            'dempet', 'kebonagung'
        ]
        found_kec = None
        for k in kecamatans:
            if k in ql:
                found_kec = k
                break

        if new_year:
            prev_clean = re.sub(r"\b(201[0-9]|202[0-9])\b", "", last_user_query).strip()
            resolved = f"{prev_clean} tahun {new_year}"
        elif found_kec:
            resolved = f"{last_user_query} kecamatan {found_kec}"
        else:
            resolved = f"{last_user_query} {question}"

        logger.info(f"[BPSChatbot] Contextual follow-up resolved: '{question}' -> '{resolved}'")
        return resolved

    def ask(
        self,
        question: str,
        session_id: str = "default",
        daerah: Optional[str] = None,
        tahun: Optional[str] = None,
        kategori: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Processes a user question with intelligent dual-mode routing:
        - Mode 1: Conversational / Greetings / Smalltalk (Fast, zero vector retrieval overhead)
        - Mode 2: Statistical Data Query (Fed with RAG vector search & granular table JSONs)
        """
        question = question.strip()
        if not question:
            return {
                "answer": "Halo! Ada yang bisa saya bantu terkait informasi dan data statistik Kabupaten Demak?",
                "citations": [],
                "chunks": [],
                "session_id": session_id
            }

        session = self.session_manager.get_or_create(session_id)
        chat_history_str = session.format_for_prompt()

        # Check intent: Is this a greeting/smalltalk or a data query?
        if is_conversational_or_greeting(question):
            logger.info(f"[BPSChatbot] Routing '{question}' to Fast Conversational Mode.")
            prompt = CONVERSATIONAL_PROMPT_TEMPLATE.format(
                chat_history=chat_history_str,
                user_query=question
            )
            answer = self.llm.generate(prompt=prompt, system_prompt=BPS_SYSTEM_PROMPT)

            session.add_user_message(question)
            session.add_assistant_message(answer)

            return {
                "answer": answer,
                "citations": [],
                "chunks": [],
                "context_fed": "",
                "session_id": session_id,
                "mode": "conversational"
            }

        # Mode 2: Statistical Data Inquiry -> Feed data from RAG pipeline
        effective_query = self._resolve_followup_query(question, session.history)
        logger.info(f"[BPSChatbot] Routing '{question}' (Effective Query: '{effective_query}') to Grounded RAG Data Feeding Mode.")
        rag_package = self.feeder.feed_context(
            query=effective_query,
            daerah=daerah,
            tahun=tahun,
            kategori=kategori,
            top_k=top_k
        )

        context_str = rag_package["context_text"]
        citations = rag_package["citations"]
        chunks = rag_package["chunks"]

        # Formulate grounded prompt
        prompt = DATA_QUERY_PROMPT_TEMPLATE.format(
            context=context_str,
            chat_history=chat_history_str,
            user_query=question
        )

        # Call LLM
        answer = self.llm.generate(
            prompt=prompt,
            system_prompt=BPS_SYSTEM_PROMPT
        )

        # Record conversation turn into memory
        session.add_user_message(question)
        session.add_assistant_message(answer)

        return {
            "answer": answer,
            "citations": citations,
            "chunks": chunks,
            "context_fed": context_str,
            "session_id": session_id,
            "mode": "rag_data"
        }

    def clear_memory(self, session_id: str = "default") -> None:
        """Resets the history of a specific session."""
        self.session_manager.clear_session(session_id)
        logger.info(f"Cleared memory for session: '{session_id}'")
