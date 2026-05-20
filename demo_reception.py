#!/usr/bin/env python3
"""Demo script for Alisa reception mode."""

import asyncio
import logging
from alisa.reception.greeter import ReceptionGreeter
from alisa.reception.knowledge import KnowledgeBase

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demo_reception_mode():
    """Demonstrate reception mode functionality."""
    print("🏢 Alisa Reception Mode Demo")
    print("=" * 40)
    
    # Create knowledge base
    kb = KnowledgeBase()
    
    # Test FAQ system
    print("\n📚 Testing FAQ Knowledge Base:")
    test_questions = [
        "ish vaqti nima?",
        "manzil qayerda?",
        "telefon raqam",
        "nima xizmat qilasiz?",
        "random question"
    ]
    
    for question in test_questions:
        answer = kb.find_answer(question)
        print(f"Q: {question}")
        print(f"A: {answer or kb.get_default_response()}")
        print()
    
    # Test greeter
    print("🤖 Testing Reception Greeter:")
    
    async def mock_notifier(message):
        print(f"📱 Telegram notification: {message}")
    
    greeter = ReceptionGreeter(telegram_notifier=mock_notifier)
    
    # Simulate guest arrival
    print("👤 Simulating guest arrival...")
    await greeter._handle_guest()
    
    # Show guest log
    print("\n📋 Guest Log:")
    for i, guest in enumerate(greeter.get_guest_log(), 1):
        print(f"{i}. {guest['time']} - Greeted: {guest['greeted']}")
    
    print("\n✅ Reception mode demo completed!")

if __name__ == "__main__":
    asyncio.run(demo_reception_mode())
