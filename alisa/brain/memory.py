"""Conversation memory for Alisa AI Assistant."""

from typing import List, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger()

class ConversationMemory:
    """Simple conversation memory with context window."""
    
    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self.messages: List[Dict[str, Any]] = []
    
    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """Add a message to conversation history."""
        message = {
            "role": role,  # "user" or "assistant"
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.messages.append(message)
        
        # Keep only recent messages
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        
        logger.debug("message_added", role=role, content_length=len(content))
    
    def get_context(self, include_system: bool = True) -> str:
        """Get conversation context as formatted string."""
        if not self.messages:
            return ""
        
        context_parts = []
        
        if include_system:
            context_parts.append("Siz Alisa AI assistantsiz. Qisqa va foydali javoblar bering.")
        
        for msg in self.messages[-5:]:  # Last 5 messages for context
            role = "Foydalanuvchi" if msg["role"] == "user" else "Alisa"
            context_parts.append(f"{role}: {msg['content']}")
        
        return "\n".join(context_parts)
    
    def get_recent_messages(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get recent messages."""
        return self.messages[-count:] if self.messages else []
    
    def clear(self):
        """Clear conversation history."""
        self.messages.clear()
        logger.info("conversation_cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get conversation statistics."""
        if not self.messages:
            return {"total_messages": 0, "user_messages": 0, "assistant_messages": 0}
        
        user_count = sum(1 for msg in self.messages if msg["role"] == "user")
        assistant_count = sum(1 for msg in self.messages if msg["role"] == "assistant")
        
        return {
            "total_messages": len(self.messages),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "oldest_message": self.messages[0]["timestamp"] if self.messages else None,
            "newest_message": self.messages[-1]["timestamp"] if self.messages else None
        }

# Global memory instance
_memory = ConversationMemory()

def get_memory() -> ConversationMemory:
    """Get global conversation memory instance."""
    return _memory

def reset_memory():
    """Reset global memory (for testing)."""
    global _memory
    _memory = ConversationMemory()
