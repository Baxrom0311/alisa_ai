#!/usr/bin/env python3
"""
Demo script for WebSocket voice pipeline
Tests voice_server.py and audio_client.py integration
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from alisa.config import Config
from alisa.voice_server import VoiceServer
from alisa.audio_client import AudioClient


async def demo_server():
    """Demo voice server"""
    print("🎤 Starting Alisa Voice Server...")
    
    try:
        config = Config.load()
        server = VoiceServer(config)
        
        print("✅ Voice server initialized")
        print("📡 WebSocket server listening on ws://localhost:8765")
        print("🔊 Ready for audio streaming...")
        print("Press Ctrl+C to stop")
        
        await server.start_server()
        
    except FileNotFoundError:
        print("❌ Config file not found. Please create config.yaml from config.yaml.example")
        return
    except Exception as e:
        print(f"❌ Server error: {e}")
        return


async def demo_client():
    """Demo audio client"""
    print("🎧 Starting Alisa Audio Client...")
    
    try:
        config = Config.load()
        client = AudioClient(config)
        
        print("✅ Audio client initialized")
        print("🔌 Connecting to voice server...")
        
        await client.run()
        
    except FileNotFoundError:
        print("❌ Config file not found. Please create config.yaml from config.yaml.example")
        return
    except Exception as e:
        print(f"❌ Client error: {e}")
        return
    finally:
        client.cleanup()


async def demo_pipeline_test():
    """Test the complete pipeline without real audio"""
    print("🧪 Testing WebSocket Pipeline...")
    
    try:
        config = Config.load()
        
        # Test server initialization
        server = VoiceServer(config)
        print("✅ Voice server initialized")
        
        # Test client initialization  
        client = AudioClient(config)
        print("✅ Audio client initialized")
        
        # Test LLM manager
        providers_status = await server.llm_manager.get_provider_status()
        print(f"📊 LLM Providers: {len(providers_status)} configured")
        
        for provider in providers_status:
            status = "✅ Available" if provider["available"] else "❌ Unavailable"
            print(f"  - {provider['name']}: {status}")
        
        # Test a simple LLM request
        print("\n🤖 Testing LLM generation...")
        messages = [{"role": "user", "content": "Salom! Qanday ahvolingiz?"}]
        
        try:
            response_count = 0
            async for sentence in server.llm_manager.generate_stream(messages):
                response_count += 1
                print(f"📝 Sentence {response_count}: {sentence}")
                if response_count >= 3:  # Limit for demo
                    break
                    
            if response_count > 0:
                print("✅ LLM streaming works!")
            else:
                print("⚠️  No LLM response (check API keys)")
                
        except Exception as e:
            print(f"⚠️  LLM test failed: {e}")
        
        print("\n🎯 Pipeline components ready!")
        print("💡 To run full voice assistant:")
        print("   1. Terminal 1: python demo_voice.py server")
        print("   2. Terminal 2: python demo_voice.py client")
        
        client.cleanup()
        
    except FileNotFoundError:
        print("❌ Config file not found. Please create config.yaml from config.yaml.example")
        return
    except Exception as e:
        print(f"❌ Pipeline test error: {e}")
        return


def main():
    """Main entry point"""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python demo_voice.py server   # Start voice server")
        print("  python demo_voice.py client   # Start audio client") 
        print("  python demo_voice.py test     # Test pipeline components")
        return
    
    mode = sys.argv[1].lower()
    
    try:
        if mode == "server":
            asyncio.run(demo_server())
        elif mode == "client":
            asyncio.run(demo_client())
        elif mode == "test":
            asyncio.run(demo_pipeline_test())
        else:
            print(f"Unknown mode: {mode}")
            print("Use: server, client, or test")
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()
