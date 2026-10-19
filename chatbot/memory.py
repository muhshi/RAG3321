"""
Conversation Memory Module for Multi-Turn Chatbot Interactions.
Maintains session histories, manages context sliding window, and formats dialogue for LLM.
"""
from typing import List, Dict, Optional
from datetime import datetime
from chatbot.config import bot_config


class ChatSession:
    """Represents a single conversational session with message history."""

    def __init__(self, session_id: str, max_turns: int = bot_config.MAX_HISTORY_TURNS):
        self.session_id = session_id
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []

    def add_user_message(self, content: str) -> None:
        self.history.append({
            "role": "user",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self._truncate()

    def add_assistant_message(self, content: str) -> None:
        self.history.append({
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self._truncate()

    def _truncate(self) -> None:
        """Keeps the history within max_turns * 2 messages."""
        max_messages = self.max_turns * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def format_for_prompt(self) -> str:
        """Formats the history as readable text for the LLM prompt."""
        if not self.history:
            return "(Belum ada riwayat percakapan sebelumnya)"

        formatted = []
        for msg in self.history:
            role = "Pengguna" if msg["role"] == "user" else "Asisten BPS"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)

    def clear(self) -> None:
        """Clears all session messages."""
        self.history.clear()


class SessionManager:
    """Manages active chat sessions across multiple users or interaction threads."""

    def __init__(self):
        self._sessions: Dict[str, ChatSession] = {}

    def get_or_create(self, session_id: str = "default") -> ChatSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = ChatSession(session_id=session_id)
        return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].clear()
