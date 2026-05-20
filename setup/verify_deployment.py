#!/usr/bin/env python3
"""Deployment verification script for Alisa AI Assistant.

Prints a human-readable PROJECT_BRIEF checklist with status indicators.
Runs brief-acceptance test suite as deployment gate.
"""

import sys
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alisa.core.config import get_config, reset_config
from alisa.brain.llm_manager import LLMManager


def run_brief_acceptance_tests():
    """Run the comprehensive brief-acceptance test suite."""
    try:
        project_root = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_brief_acceptance.py", "-v", "--tb=short"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        checks = []
        
        if result.returncode == 0:
            # Parse test output for count
            lines = result.stdout.split('\n')
            summary_line = [line for line in lines if 'passed' in line and '====' in line]
            if summary_line:
                checks.append(("✅", f"Brief acceptance tests: {summary_line[0].split('=')[-1].strip()}"))
            else:
                checks.append(("✅", "Brief acceptance tests: All passed"))
        else:
            # Show failed test details
            checks.append(("❌", "Brief acceptance tests: FAILED"))
            if result.stdout:
                failed_lines = [line for line in result.stdout.split('\n') if 'FAILED' in line]
                for line in failed_lines[:3]:  # Show first 3 failures
                    checks.append(("❌", f"  {line.strip()}"))
        
        return checks
        
    except subprocess.TimeoutExpired:
        return [("❌", "Brief acceptance tests: Timeout (>60s)")]
    except Exception as e:
        return [("❌", f"Brief acceptance tests: Error - {e}")]


def check_config_completeness():
    """Check if config.yaml has all required keys."""
    try:
        reset_config()
        config = get_config()
        
        checks = []
        
        # Language setting
        if config.get("language") == "uz":
            checks.append(("✅", "Language set to Uzbek (uz)"))
        else:
            checks.append(("❌", f"Language should be 'uz', got: {config.get('language')}"))
        
        # Wake word
        wake_word = config.get("wake_word")
        if isinstance(wake_word, str) and wake_word == "alisa":
            checks.append(("✅", "Wake word configured as 'alisa'"))
        elif isinstance(wake_word, dict) and wake_word.get("keyword") == "alisa":
            checks.append(("✅", "Wake word configured as 'alisa' (nested format)"))
        else:
            checks.append(("❌", f"Wake word should be 'alisa', got: {wake_word}"))
        
        # LLM providers
        llm_config = config.get("llm", {})
        providers = llm_config.get("providers", [])
        if len(providers) >= 6:
            provider_names = [p.get("name") for p in providers]
            required = ["openai", "gemini", "deepseek", "grok", "claude", "ollama"]
            missing = [name for name in required if name not in provider_names]
            if not missing:
                checks.append(("✅", f"All {len(providers)} LLM providers configured"))
            else:
                checks.append(("❌", f"Missing LLM providers: {missing}"))
        else:
            checks.append(("❌", f"Need 6+ LLM providers, got: {len(providers)}"))
        
        # Ollama last
        if providers and providers[-1].get("name") == "ollama":
            checks.append(("✅", "Ollama is last provider (offline fallback)"))
        else:
            checks.append(("❌", "Ollama should be last provider"))
        
        # Whisper multilingual
        whisper_model = config.get("whisper", {}).get("model", "")
        if ".en.bin" not in whisper_model and any(m in whisper_model for m in ["base", "small", "medium"]):
            checks.append(("✅", "Whisper model is multilingual"))
        else:
            checks.append(("⚠️", f"Whisper model may be English-only: {whisper_model}"))
        
        # Piper Uzbek
        piper_model = config.get("piper", {}).get("model", "")
        if "uz_UZ" in piper_model or "uzbek" in piper_model.lower():
            checks.append(("✅", "Piper TTS model is Uzbek"))
        else:
            checks.append(("⚠️", f"Piper model may not be Uzbek: {piper_model}"))
        
        return checks
        
    except Exception as e:
        return [("❌", f"Config check failed: {e}")]


def check_llm_manager():
    """Check LLM manager functionality."""
    try:
        reset_config()
        manager = LLMManager()
        
        checks = []
        
        # Provider loading
        if len(manager.providers) > 0:
            checks.append(("✅", f"LLM Manager loaded {len(manager.providers)} providers"))
        else:
            checks.append(("❌", "LLM Manager loaded no providers"))
        
        # Ollama availability
        ollama_providers = [p for p in manager.providers if p.name == "ollama"]
        if ollama_providers:
            checks.append(("✅", "Ollama provider available (offline fallback)"))
        else:
            checks.append(("⚠️", "Ollama provider not loaded - no offline fallback"))
        
        # API key skipping
        online_providers = [p for p in manager.providers if p.name != "ollama"]
        if len(online_providers) == 0:
            checks.append(("⚠️", "No online providers loaded (all API keys empty)"))
        else:
            checks.append(("✅", f"{len(online_providers)} online providers loaded"))
        
        return checks
        
    except Exception as e:
        return [("❌", f"LLM Manager check failed: {e}")]


def check_system_prompt():
    """Check Uzbek system prompt."""
    try:
        from alisa.core.assistant import ALISA_SYSTEM_PROMPT_UZ
        
        checks = []
        
        if ALISA_SYSTEM_PROMPT_UZ and len(ALISA_SYSTEM_PROMPT_UZ) > 0:
            uzbek_indicators = ["Sen", "Alisa", "o'zbek", "tilida", "gaplashasan"]
            found_uzbek = any(word in ALISA_SYSTEM_PROMPT_UZ for word in uzbek_indicators)
            if found_uzbek:
                checks.append(("✅", "Uzbek system prompt configured"))
            else:
                checks.append(("⚠️", "System prompt may not be in Uzbek"))
        else:
            checks.append(("❌", "System prompt not found or empty"))
        
        return checks
        
    except Exception as e:
        return [("❌", f"System prompt check failed: {e}")]


def check_telegram_handlers():
    """Check Telegram bot handlers."""
    try:
        # Check if telegram bot module can be imported
        from alisa.telegram.bot import AlisaBot
        
        checks = []
        
        # Check if key handler methods exist in AlisaBot class
        if hasattr(AlisaBot, 'status_command'):
            checks.append(("✅", "Telegram /status handler available"))
        else:
            checks.append(("❌", "Telegram /status handler missing"))
            
        if hasattr(AlisaBot, 'providers_command'):
            checks.append(("✅", "Telegram /providers handler available"))
        else:
            checks.append(("❌", "Telegram /providers handler missing"))
            
        if hasattr(AlisaBot, 'ask_command'):
            checks.append(("✅", "Telegram /ask handler available"))
        else:
            checks.append(("⚠️", "Telegram /ask handler not found (may be in message handler)"))
        
        return checks
        
    except ImportError as e:
        return [("❌", f"Telegram module import failed: {e}")]
    except Exception as e:
        return [("❌", f"Telegram check failed: {e}")]


def check_hardware_requirements():
    """Check hardware-specific requirements (Pi-only)."""
    return [
        ("⏭️", "Wake word detection - requires Pi hardware"),
        ("⏭️", "Voice conversation < 5s - requires Pi hardware"),
        ("⏭️", "Microphone/speaker - requires Pi hardware"),
        ("⏭️", "systemd service - requires Pi deployment"),
    ]


def main():
    """Run deployment verification checklist."""
    print("🤖 Alisa AI Assistant - Deployment Verification")
    print("=" * 50)
    print()
    
    all_checks = []
    
    # Run brief-acceptance tests first as deployment gate
    print("🧪 Brief Acceptance Tests (Deployment Gate):")
    brief_checks = run_brief_acceptance_tests()
    for status, message in brief_checks:
        print(f"  {status} {message}")
        all_checks.append((status, message))
    print()
    
    # If brief tests fail, stop here
    brief_failed = any(status == "❌" for status, _ in brief_checks)
    if brief_failed:
        print("❌ DEPLOYMENT GATE FAILED - Brief acceptance tests must pass")
        print("   Fix failing tests before deployment.")
        return 1
    
    print("📋 Configuration Checks:")
    config_checks = check_config_completeness()
    for status, message in config_checks:
        print(f"  {status} {message}")
        all_checks.append((status, message))
    print()
    
    print("🧠 LLM Manager Checks:")
    llm_checks = check_llm_manager()
    for status, message in llm_checks:
        print(f"  {status} {message}")
        all_checks.append((status, message))
    print()
    
    print("💬 System Prompt Checks:")
    prompt_checks = check_system_prompt()
    for status, message in prompt_checks:
        print(f"  {status} {message}")
        all_checks.append((status, message))
    print()
    
    print("📱 Telegram Bot Checks:")
    telegram_checks = check_telegram_handlers()
    for status, message in telegram_checks:
        print(f"  {status} {message}")
        all_checks.append((status, message))
    print()
    
    print("🔧 Hardware-Specific Checks (Pi deployment only):")
    hardware_checks = check_hardware_requirements()
    for status, message in hardware_checks:
        print(f"  {status} {message}")
        all_checks.append((status, message))
    print()
    
    # Summary
    passed = len([c for c in all_checks if c[0] == "✅"])
    warnings = len([c for c in all_checks if c[0] == "⚠️"])
    failed = len([c for c in all_checks if c[0] == "❌"])
    skipped = len([c for c in all_checks if c[0] == "⏭️"])
    
    print("📊 Summary:")
    print(f"  ✅ Passed: {passed}")
    print(f"  ⚠️  Warnings: {warnings}")
    print(f"  ❌ Failed: {failed}")
    print(f"  ⏭️  Skipped (Pi-only): {skipped}")
    print()
    
    if failed > 0:
        print("❌ Deployment verification failed. Fix issues above.")
        return 1
    elif warnings > 0:
        print("⚠️  Deployment verification passed with warnings.")
        print("✅ Brief acceptance tests passed - Core functionality verified")
        return 0
    else:
        print("✅ Deployment verification passed!")
        print("✅ Brief acceptance tests passed - Ready for deployment")
        return 0


if __name__ == "__main__":
    sys.exit(main())
