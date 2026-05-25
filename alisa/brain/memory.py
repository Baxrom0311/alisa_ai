"""Conversation memory with Adaptive Focus Memory (AFM).

Yirik kompaniyalar yondashuvi:
- Amazon Alexa: Contextual ASR — oldingi so'rovlar asosida tanishni yaxshilash
- Google: Personalized speech recognition via federated learning
- Apple: On-device context for follow-up questions

Adaptive Focus Memory (arxiv: 2511.12712):
- FULL: Oxirgi 3 xabar — to'liq saqlanadi
- COMPRESSED: 4-10 xabar — qisqartirilgan holda
- PLACEHOLDER: 10+ xabar — faqat mavzu saqlanadi

Bu yondashuv LLM context window ni tejaydi va muhim ma'lumotni yo'qotmaydi.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


class ConversationMemory:
    """Adaptive Focus Memory for multi-turn conversations."""

    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.messages: List[Dict[str, Any]] = []
        # Long-term facts extracted from conversation
        self.facts: List[str] = []
        self.max_facts = 10

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """Add a message to conversation history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self.messages.append(message)

        # Extract facts from user messages for long-term memory
        if role == "user":
            self._extract_facts(content)

        # Trim old messages
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_context(self, include_system: bool = True) -> str:
        """Get conversation context using Adaptive Focus Memory.
        
        - FULL: last 3 messages (complete text)
        - COMPRESSED: messages 4-8 (summarized)
        - FACTS: long-term extracted facts
        """
        if not self.messages:
            return ""

        parts = []

        # Long-term facts (always included if available)
        if self.facts:
            parts.append("Eslab qoling: " + "; ".join(self.facts[-5:]))

        # COMPRESSED: older messages (just role + short summary)
        older = self.messages[:-3] if len(self.messages) > 3 else []
        if older:
            compressed = []
            for msg in older[-5:]:  # Max 5 compressed messages
                role = "F" if msg["role"] == "user" else "A"
                short = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
                compressed.append(f"{role}: {short}")
            parts.append("Oldingi suhbat:\n" + "\n".join(compressed))

        # FULL: last 3 messages (complete)
        recent = self.messages[-3:]
        for msg in recent:
            role = "Foydalanuvchi" if msg["role"] == "user" else "Alisa"
            parts.append(f"{role}: {msg['content']}")

        return "\n".join(parts)

    def _extract_facts(self, text: str):
        """Extract important facts from user messages for long-term memory.
        
        Simple heuristic: statements with "men", "mening", personal info.
        """
        text_lower = text.lower()
        fact_indicators = [
            "mening ismim", "men", "mening", "uyim", "ishim",
            "telefon", "manzil", "tug'ilgan",
        ]

        # Only extract if it looks like a personal statement (not a question)
        if "?" in text:
            return

        for indicator in fact_indicators:
            if indicator in text_lower and len(text) > 10:
                # Avoid duplicates
                if not any(text_lower[:30] in f.lower() for f in self.facts):
                    self.facts.append(text.strip())
                    if len(self.facts) > self.max_facts:
                        self.facts = self.facts[-self.max_facts:]
                    logger.debug("fact_extracted", fact=text[:50])
                break

    def get_recent_messages(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get recent messages."""
        return self.messages[-count:] if self.messages else []

    def clear(self):
        """Clear conversation history (keeps facts)."""
        self.messages.clear()
        logger.info("conversation_cleared")

    def clear_all(self):
        """Clear everything including facts."""
        self.messages.clear()
        self.facts.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get conversation statistics."""
        user_count = sum(1 for m in self.messages if m["role"] == "user")
        return {
            "total_messages": len(self.messages),
            "user_messages": user_count,
            "assistant_messages": len(self.messages) - user_count,
            "facts_stored": len(self.facts),
        }


# Global instance
_memory = ConversationMemory()


def get_memory() -> ConversationMemory:
    return _memory


def reset_memory():
    global _memory
    _memory = ConversationMemory()
