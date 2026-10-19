"""
BPS AI Chatbot Package.
Provides intelligent, RAG-fed conversational AI over BPS statistical publications.
"""
import sys

# Ensure UTF-8 console output on Windows platforms
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from chatbot.config import ChatbotConfig, bot_config
from chatbot.rag_feeder import RAGFeeder
from chatbot.llm_client import LLMClient
from chatbot.memory import ChatSession, SessionManager
from chatbot.bot import BPSChatbot

__all__ = [
    "BPSChatbot",
    "RAGFeeder",
    "LLMClient",
    "ChatSession",
    "SessionManager",
    "ChatbotConfig",
    "bot_config",
]
