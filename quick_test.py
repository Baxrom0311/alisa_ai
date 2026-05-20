#!/usr/bin/env python3
"""Quick test script to verify Alisa components are working."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from alisa.core.config import get_config
from alisa.brain.llm_manager import LLMManager
from alisa.services.health import get_system_stats
from alisa.core.validator import validate_system


async def test_basic_functionality():
    """Test basic Alisa functionality."""
    print("🔍 Testing Alisa AI Assistant components...")
    
    # Test 1: Config loading
    print("\n1. Testing configuration...")
    try:
        config = get_config()
        print(f"✅ Config loaded successfully")
        print(f"   Language: {config.get('language', 'not set')}")
        print(f"   Wake word: {config.get('wake_word', 'not set')}")
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False
    
    # Test 2: System validation
    print("\n2. Testing system validation...")
    try:
        is_valid, issues = validate_system()
        if is_valid:
            print("✅ System validation passed")
        else:
            print("⚠️  System validation found issues:")
            for issue in issues:
                print(f"   - {issue}")
    except Exception as e:
        print(f"❌ System validation failed: {e}")
    
    # Test 3: Health monitor
    print("\n3. Testing health monitor...")
    try:
        status = get_system_stats()
        print(f"✅ Health monitor working")
        print(f"   CPU: {status.get('cpu_percent', 'unknown')}%")
        print(f"   Memory: {status.get('memory_percent', 'unknown')}%")
    except Exception as e:
        print(f"❌ Health monitor failed: {e}")
    
    # Test 4: LLM Manager
    print("\n4. Testing LLM Manager...")
    try:
        llm_manager = LLMManager()
        status = llm_manager.get_provider_status()
        providers = status.get("providers", {})
        print(f"✅ LLM Manager initialized")
        print(f"   Available providers: {status.get('active_providers', 0)}")
        for name, provider_status in providers.items():
            status_icon = "✅" if provider_status["available"] else "❌"
            print(f"   {status_icon} {name}: {provider_status['success_rate']}")
    except Exception as e:
        print(f"❌ LLM Manager failed: {e}")
    
    # Test 5: Simple LLM query (if any provider available)
    print("\n5. Testing LLM query...")
    try:
        llm_manager = LLMManager()
        response = await llm_manager.generate("Salom! Sen kimsan?", "Sen Alisa AI yordamchisan.")
        if response:
            print(f"✅ LLM query successful")
            print(f"   Response: {response[:100]}...")
        else:
            print("⚠️  LLM query returned empty response")
    except Exception as e:
        print(f"❌ LLM query failed: {e}")
    
    print("\n🎉 Basic functionality test completed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_basic_functionality())
