"""
Chatbot Configuration Module.
Loads environment variables and manages LLM provider, retrieval, and prompt configurations.
"""
from pathlib import Path
from typing import Optional, Literal
from pydantic_settings import BaseSettings


class ChatbotConfig(BaseSettings):
    # LLM Provider selection: gemini, openai, groq, ollama, mock
    LLM_PROVIDER: Literal["gemini", "openai", "groq", "ollama", "mock"] = "gemini"
    
    # API Keys
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    # Model Names
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_MODEL: str = "gpt-4o-mini"
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    OLLAMA_MODEL: str = "llama3"
    
    # Custom Endpoints (e.g. for local Ollama, vLLM, or custom proxies)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_BASE_URL: Optional[str] = None
    
    # LLM Hyperparameters
    TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 8192
    
    # RAG Feeding Settings
    TOP_K_CHUNKS: int = 10
    SCORE_THRESHOLD: float = 0.20
    INCLUDE_FULL_TABLE_JSON: bool = True
    MAX_TABLE_ROWS_IN_CONTEXT: int = 35
    DEFAULT_REGION: Optional[str] = None
    
    # Conversation Memory
    MAX_HISTORY_TURNS: int = 6  # Number of past QA pairs to retain

    class Config:
        env_file = ".env"
        extra = "allow"


# Singleton instance
bot_config = ChatbotConfig()
