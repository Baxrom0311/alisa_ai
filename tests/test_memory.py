"""Tests for conversation memory module."""

import pytest
from alisa.brain.memory import ConversationMemory, get_memory, reset_memory


def test_memory_init():
    """Test memory initialization."""
    memory = ConversationMemory(max_messages=5)
    assert memory.max_messages == 5
    assert len(memory.messages) == 0


def test_add_message():
    """Test adding messages."""
    memory = ConversationMemory()
    
    memory.add_message("user", "Hello")
    assert len(memory.messages) == 1
    assert memory.messages[0]["role"] == "user"
    assert memory.messages[0]["content"] == "Hello"
    assert "timestamp" in memory.messages[0]
    
    memory.add_message("assistant", "Hi there!", {"source": "llm"})
    assert len(memory.messages) == 2
    assert memory.messages[1]["metadata"]["source"] == "llm"


def test_max_messages_limit():
    """Test message limit enforcement."""
    memory = ConversationMemory(max_messages=3)
    
    # Add more messages than limit
    for i in range(5):
        memory.add_message("user", f"Message {i}")
    
    # Should keep only last 3
    assert len(memory.messages) == 3
    assert memory.messages[0]["content"] == "Message 2"
    assert memory.messages[-1]["content"] == "Message 4"


def test_get_context():
    """Test context generation."""
    memory = ConversationMemory()
    
    # Empty context
    assert memory.get_context() == ""
    
    # Add some messages
    memory.add_message("user", "What is AI?")
    memory.add_message("assistant", "AI is artificial intelligence")
    memory.add_message("user", "Tell me more")
    
    context = memory.get_context()
    assert "Foydalanuvchi: What is AI?" in context
    assert "Alisa: AI is artificial intelligence" in context
    assert "Foydalanuvchi: Tell me more" in context


def test_get_recent_messages():
    """Test getting recent messages."""
    memory = ConversationMemory()
    
    # Add messages
    for i in range(10):
        memory.add_message("user", f"Message {i}")
    
    recent = memory.get_recent_messages(3)
    assert len(recent) == 3
    assert recent[0]["content"] == "Message 7"
    assert recent[-1]["content"] == "Message 9"
    
    # Request more than available
    all_messages = memory.get_recent_messages(20)
    assert len(all_messages) == 10


def test_clear():
    """Test clearing memory."""
    memory = ConversationMemory()
    
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi")
    assert len(memory.messages) == 2
    
    memory.clear()
    assert len(memory.messages) == 0


def test_get_stats():
    """Test conversation statistics."""
    memory = ConversationMemory()
    
    # Empty stats
    stats = memory.get_stats()
    assert stats["total_messages"] == 0
    assert stats["user_messages"] == 0
    assert stats["assistant_messages"] == 0
    
    # Add messages
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi")
    memory.add_message("user", "How are you?")
    
    stats = memory.get_stats()
    assert stats["total_messages"] == 3
    assert stats["user_messages"] == 2
    assert stats["assistant_messages"] == 1
    assert stats["facts_stored"] >= 0


def test_global_memory():
    """Test global memory functions."""
    reset_memory()
    
    memory1 = get_memory()
    memory2 = get_memory()
    
    # Should be same instance
    assert memory1 is memory2
    
    memory1.add_message("user", "Test")
    assert len(memory2.messages) == 1
    
    reset_memory()
    memory3 = get_memory()
    assert len(memory3.messages) == 0
