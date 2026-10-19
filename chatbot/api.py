"""
API and Web Integration Module for BPS AI Chatbot.
Provides lightweight interface ready for FastAPI, Flask, Streamlit, or webhook bots.
"""
from typing import Dict, Any, Optional
from chatbot.bot import BPSChatbot

# Global singleton chatbot instance for API serving
_global_bot: Optional[BPSChatbot] = None


def get_chatbot() -> BPSChatbot:
    """Returns singleton instance of BPSChatbot."""
    global _global_bot
    if _global_bot is None:
        _global_bot = BPSChatbot()
    return _global_bot


def handle_chat_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standard request handler suitable for any web framework or message webhook.

    Expected payload:
    {
        "message": "Berapa jumlah penduduk di Demak tahun 2024?",
        "session_id": "optional_user_id",
        "daerah": "optional_override",
        "tahun": "optional_year",
        "kategori": "optional_category",
        "top_k": 4
    }
    """
    bot = get_chatbot()
    message = payload.get("message", "")
    session_id = payload.get("session_id", "default")
    daerah = payload.get("daerah")
    tahun = payload.get("tahun")
    kategori = payload.get("kategori")
    top_k = payload.get("top_k")

    result = bot.ask(
        question=message,
        session_id=session_id,
        daerah=daerah,
        tahun=tahun,
        kategori=kategori,
        top_k=top_k
    )

    return {
        "status": "success",
        "data": {
            "answer": result["answer"],
            "citations": result["citations"],
            "session_id": result["session_id"],
            "total_references": len(result["citations"])
        }
    }


# Optional FastAPI application if installed
try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(
        title="BPS Demak AI Chatbot API",
        description="RAG-fed Intelligent Statistical Assistant for Badan Pusat Statistik",
        version="1.0.0"
    )

    class ChatRequest(BaseModel):
        message: str
        session_id: Optional[str] = "default"
        daerah: Optional[str] = None
        tahun: Optional[str] = None
        kategori: Optional[str] = None
        top_k: Optional[int] = 4

    @app.post("/api/chat")
    def api_chat(req: ChatRequest):
        res = handle_chat_request(req.model_dump())
        return res

    @app.delete("/api/session/{session_id}")
    def api_clear_session(session_id: str):
        bot = get_chatbot()
        bot.clear_memory(session_id)
        return {"status": "success", "message": f"Session '{session_id}' cleared"}

    @app.get("/api/health")
    def api_health():
        return {"status": "healthy", "service": "BPS Chatbot RAG Engine"}

except ImportError:
    app = None
