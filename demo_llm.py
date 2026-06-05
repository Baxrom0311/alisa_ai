#!/usr/bin/env python3
"""Demo script for LLM Manager."""

import asyncio
import logging
from alisa import LLMManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_llm_manager():
    """Demonstrate LLM manager functionality."""
    print("🤖 Alisa LLM Manager Demo")
    print("=" * 40)
    
    try:
        # Initialize LLM manager
        llm = LLMManager()
        
        # Show provider status
        status = llm.get_provider_status()
        print(f"📊 Providers: {status['total_providers']}")
        for provider in status['providers']:
            key_status = "✅" if provider['has_api_key'] else "❌"
            print(f"  {provider['name']}: {provider['model']} {key_status}")
        
        print("\n" + "=" * 40)
        
        # Test messages
        messages = [
            {"role": "system", "content": "Sen Alisa - aqlli yordamchi. O'zbek tilida javob ber."},
            {"role": "user", "content": "Salom! O'zingni tanit."}
        ]
        
        print("💬 Test message: Salom! O'zingni tanit.")
        print("⏳ Generating response...")
        
        # Try to generate response
        try:
            response = await llm.generate(messages, timeout=10.0)
            print(f"✅ Response: {response}")
            print(f"🎯 Used provider: {llm.last_working_provider}")
            
            print("\n" + "-" * 40)
            print("🌊 Testing streaming...")
            
            # Test streaming
            async for sentence in llm.generate_stream(messages):
                print(f"📝 Sentence: {sentence}")
                
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            print("💡 This is expected if no API keys are configured")
            
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return
    
    print("\n" + "=" * 40)
    print("✅ Demo completed!")


if __name__ == "__main__":
    asyncio.run(demo_llm_manager())
