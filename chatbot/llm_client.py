"""
Unified LLM Client using HTTPX.
Zero extra heavy SDK requirements; seamlessly supports Google Gemini, OpenAI,
Groq, Ollama / Local LLM, and Mock/Dry-run modes.
"""
import os
import httpx
from typing import Optional
from loguru import logger
from chatbot.config import bot_config


class LLMClient:
    """Unified client for invoking language models across multiple providers."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or bot_config.LLM_PROVIDER).lower()
        self.client = httpx.Client(timeout=60.0)

    def generate(self, prompt: str, system_prompt: str) -> str:
        """Dispatches generation request to the configured provider."""
        # Check if provider can run or needs fallback to mock
        if self.provider == "gemini":
            api_key = bot_config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.warning("[LLMClient] No GEMINI_API_KEY found in environment. Falling back to Dry-Run/Mock response.")
                return self._generate_mock(prompt, system_prompt, reason="GEMINI_API_KEY is not set in .env")
            return self._call_gemini(prompt, system_prompt, api_key)

        elif self.provider in ("openai", "groq", "ollama"):
            return self._call_openai_compatible(prompt, system_prompt)

        elif self.provider == "mock":
            return self._generate_mock(prompt, system_prompt, reason="Configured in MOCK mode")

        else:
            logger.warning(f"[LLMClient] Unknown provider '{self.provider}'. Falling back to mock.")
            return self._generate_mock(prompt, system_prompt, reason=f"Unsupported provider {self.provider}")

    def _call_gemini(self, prompt: str, system_prompt: str, api_key: str) -> str:
        """Calls Google Gemini REST API with automatic resilient fallback."""
        primary_model = bot_config.GEMINI_MODEL
        candidates_to_try = [primary_model]
        for backup in ["gemini-2.5-flash", "gemini-3.7-flash", "gemini-3-flash-preview"]:
            if backup not in candidates_to_try:
                candidates_to_try.append(backup)

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "temperature": bot_config.TEMPERATURE,
                "maxOutputTokens": bot_config.MAX_TOKENS,
                "thinkingConfig": {
                    "thinkingBudget": 1024
                }
            }
        }

        last_error = None
        for model in candidates_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                resp = self.client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        cand = candidates[0]
                        finish_reason = cand.get("finishReason", "")
                        if finish_reason == "MAX_TOKENS":
                            logger.warning("[LLMClient] Model output reached MAX_TOKENS limit.")
                        text_parts = cand.get("content", {}).get("parts", [])
                        clean_parts = [p.get("text", "") for p in text_parts if not p.get("thought", False)]
                        if not clean_parts:
                            clean_parts = [p.get("text", "") for p in text_parts]
                        return "".join(clean_parts).strip()
                    return "Maaf, tidak ada tanggapan yang dihasilkan oleh model Gemini."
                else:
                    last_error = f"{resp.status_code}: {resp.text[:120]}"
                    logger.warning(f"[LLMClient] Model '{model}' returned status {resp.status_code}. Trying next candidate...")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[LLMClient] Model '{model}' request failed ({e}). Trying next candidate...")

        logger.error(f"[LLMClient] All Gemini model attempts failed. Last error: {last_error}")
        return f"[Error Gemini API]: Semua model gagal merespons ({last_error}). Silakan periksa koneksi internet atau kuota API Key Anda."

    def _call_openai_compatible(self, prompt: str, system_prompt: str) -> str:
        """Calls OpenAI, Groq, Ollama, or custom OpenAI-compatible endpoint."""
        provider = self.provider

        if provider == "groq":
            base_url = "https://api.groq.com/openai/v1/chat/completions"
            api_key = bot_config.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
            model = bot_config.GROQ_MODEL
        elif provider == "ollama":
            base_url = f"{bot_config.OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
            api_key = "ollama"
            model = bot_config.OLLAMA_MODEL
        else:  # openai
            base_url = bot_config.OPENAI_BASE_URL or "https://api.openai.com/v1/chat/completions"
            api_key = bot_config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
            model = bot_config.OPENAI_MODEL

        if provider != "ollama" and not api_key:
            logger.warning(f"[LLMClient] No API key found for {provider}. Falling back to Dry-Run/Mock.")
            return self._generate_mock(prompt, system_prompt, reason=f"{provider.upper()}_API_KEY is not set in .env")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": bot_config.TEMPERATURE,
            "max_tokens": bot_config.MAX_TOKENS
        }

        try:
            resp = self.client.post(base_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return f"Maaf, tidak ada respons yang dihasilkan oleh model {provider}."
        except Exception as e:
            logger.error(f"[LLMClient] {provider} API request failed: {e}")
            return f"[Error {provider.upper()} API]: {e}"

    def _generate_mock(self, prompt: str, system_prompt: str, reason: str = "") -> str:
        """
        Mock / Dry-run generator when no live LLM API key is configured.
        Demonstrates that RAG feeding and prompt assembly were successful.
        """
        return (
            "🤖 [SIMULASI CHATBOT BPS - MODE DRY-RUN / MOCK]\n"
            "----------------------------------------------------------------------\n"
            f"ℹ️  Status: RAG Feeder Berhasil Menyiapkan Konteks ({reason})\n\n"
            "Data statistik dari database BPS telah berhasil diambil melalui RAG pipeline.\n"
            "Untuk mengaktifkan respons generasi langsung via kecerdasan buatan, tambahkan salah satu API Key berikut pada file `.env`:\n"
            "  - GEMINI_API_KEY=your_key_here (Default)\n"
            "  - OPENAI_API_KEY=your_key_here\n"
            "  - GROQ_API_KEY=your_key_here\n"
            "  - Atau jalankan Ollama secara lokal (LLM_PROVIDER=ollama)\n\n"
            "Cuplikan data statistik BPS yang terhubung untuk pertanyaan Anda siap digunakan oleh LLM."
        )
