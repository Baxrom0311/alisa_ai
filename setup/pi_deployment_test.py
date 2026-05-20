#!/usr/bin/env python3
"""Comprehensive Raspberry Pi deployment test for Alisa AI Assistant."""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

import structlog

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alisa.core.config import get_config
from alisa.core.validator import validate_system, get_system_info
from alisa.brain.llm_manager import get_llm_manager
from alisa.services.health import get_system_stats, check_memory_pressure
from alisa.voice.audio_io import test_audio_devices
from alisa.telegram.bot import AlisaBot
from alisa.core.assistant import AlisaAssistant

logger = structlog.get_logger()


class PiDeploymentTester:
    """Comprehensive deployment tester for Raspberry Pi."""
    
    def __init__(self):
        self.results = {}
        self.errors = []
        self.warnings = []
        
    async def run_all_tests(self) -> Dict:
        """Run all deployment tests."""
        logger.info("Starting Raspberry Pi deployment tests...")
        
        tests = [
            ("system_validation", self.test_system_validation),
            ("config_validation", self.test_config_validation),
            ("llm_providers", self.test_llm_providers),
            ("audio_system", self.test_audio_system),
            ("voice_pipeline", self.test_voice_pipeline),
            ("telegram_bot", self.test_telegram_bot),
            ("memory_management", self.test_memory_management),
            ("performance_benchmarks", self.test_performance_benchmarks),
            ("integration_test", self.test_integration),
        ]
        
        for test_name, test_func in tests:
            try:
                logger.info(f"Running test: {test_name}")
                result = await test_func()
                self.results[test_name] = result
                if result.get("status") == "failed":
                    self.errors.append(f"{test_name}: {result.get('error', 'Unknown error')}")
                elif result.get("warnings"):
                    self.warnings.extend([f"{test_name}: {w}" for w in result["warnings"]])
            except Exception as e:
                error_msg = f"{test_name}: {str(e)}"
                self.errors.append(error_msg)
                self.results[test_name] = {"status": "failed", "error": str(e)}
                logger.error(f"Test {test_name} failed", error=str(e))
        
        return self.generate_report()
    
    async def test_system_validation(self) -> Dict:
        """Test system validation and requirements."""
        try:
            is_valid, issues = validate_system()
            system_info = get_system_info()
            
            warnings = []
            if not is_valid:
                warnings.extend(issues)
            
            # Check Pi-specific requirements
            if system_info.get("memory_gb", 0) < 3:
                warnings.append("Low memory detected - may affect performance")
            
            if system_info.get("architecture") != "aarch64":
                warnings.append("Not running on ARM64 - may not be a Raspberry Pi")
            
            return {
                "status": "passed" if is_valid else "warning",
                "system_info": system_info,
                "warnings": warnings
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_config_validation(self) -> Dict:
        """Test configuration loading and validation."""
        try:
            config = get_config()
            
            # Check critical config sections
            required_sections = ["llm", "whisper", "piper", "telegram"]
            missing_sections = [s for s in required_sections if s not in config]
            
            if missing_sections:
                return {
                    "status": "failed",
                    "error": f"Missing config sections: {missing_sections}"
                }
            
            # Check API keys (without exposing them)
            api_keys_configured = 0
            for provider in config["llm"]["providers"]:
                if provider.get("api_key"):
                    api_keys_configured += 1
            
            return {
                "status": "passed",
                "api_keys_configured": api_keys_configured,
                "total_providers": len(config["llm"]["providers"])
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_llm_providers(self) -> Dict:
        """Test LLM provider availability and fallback chain."""
        try:
            llm_manager = get_llm_manager()
            
            # Test each provider
            provider_results = {}
            working_providers = 0
            
            for provider_name in ["openai", "gemini", "deepseek", "grok", "claude", "ollama"]:
                try:
                    # Quick test with minimal prompt
                    start_time = time.time()
                    response = await llm_manager.generate(
                        "Test", 
                        system="Reply with 'OK'",
                        preferred_provider=provider_name,
                        timeout=10
                    )
                    response_time = time.time() - start_time
                    
                    if response and "OK" in response.upper():
                        provider_results[provider_name] = {
                            "status": "working",
                            "response_time": round(response_time, 2)
                        }
                        working_providers += 1
                    else:
                        provider_results[provider_name] = {
                            "status": "failed",
                            "error": "Invalid response"
                        }
                except Exception as e:
                    provider_results[provider_name] = {
                        "status": "failed",
                        "error": str(e)[:100]
                    }
            
            # Test fallback chain
            fallback_response = await llm_manager.generate("Hello", system="Reply briefly")
            fallback_working = bool(fallback_response)
            
            return {
                "status": "passed" if working_providers > 0 else "failed",
                "working_providers": working_providers,
                "provider_results": provider_results,
                "fallback_working": fallback_working
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_audio_system(self) -> Dict:
        """Test audio input/output devices."""
        try:
            # Test audio devices
            audio_test = test_audio_devices()
            
            return {
                "status": "passed" if audio_test["input_available"] and audio_test["output_available"] else "warning",
                "audio_devices": audio_test,
                "warnings": [] if audio_test["input_available"] and audio_test["output_available"] 
                          else ["Audio devices not properly configured"]
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_voice_pipeline(self) -> Dict:
        """Test the complete voice pipeline (STT + TTS)."""
        try:
            from alisa.voice.stt import transcribe
            from alisa.voice.tts import synthesize
            
            # Create a simple test audio (silence)
            test_audio = b'\x00' * 16000  # 1 second of silence at 16kHz
            
            # Test STT
            stt_result = await asyncio.to_thread(transcribe, test_audio)
            stt_working = isinstance(stt_result, str)  # Should return empty string for silence
            
            # Test TTS
            tts_result = await asyncio.to_thread(synthesize, "Test")
            tts_working = tts_result is not None
            
            # Clean up TTS file
            if tts_result and Path(tts_result).exists():
                Path(tts_result).unlink(missing_ok=True)
            
            return {
                "status": "passed" if stt_working and tts_working else "failed",
                "stt_working": stt_working,
                "tts_working": tts_working
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_telegram_bot(self) -> Dict:
        """Test Telegram bot initialization."""
        try:
            # Only test if token is configured
            if not os.environ.get('TELEGRAM_BOT_TOKEN'):
                return {
                    "status": "skipped",
                    "reason": "TELEGRAM_BOT_TOKEN not configured"
                }
            
            # Create assistant for bot
            assistant = AlisaAssistant()
            
            # Test bot initialization (don't start it)
            bot = AlisaBot(assistant=assistant)
            
            return {
                "status": "passed",
                "bot_initialized": True
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_memory_management(self) -> Dict:
        """Test memory management and monitoring."""
        try:
            # Get initial memory stats
            initial_stats = get_system_stats()
            
            # Simulate some memory usage
            test_data = [b'x' * 1024 for _ in range(1000)]  # 1MB
            
            # Get stats after allocation
            after_stats = get_system_stats()
            
            # Clean up
            del test_data
            
            # Check if memory monitoring is working
            memory_increase = after_stats.get("memory_used_mb", 0) - initial_stats.get("memory_used_mb", 0)
            monitoring_working = memory_increase >= 0  # Should at least not decrease
            
            # Check memory pressure
            pressure_info = check_memory_pressure()
            
            return {
                "status": "passed",
                "monitoring_working": monitoring_working,
                "initial_memory_mb": initial_stats.get("memory_used_mb", 0),
                "memory_pressure": pressure_info["pressure_level"]
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_performance_benchmarks(self) -> Dict:
        """Run performance benchmarks for Pi optimization."""
        try:
            benchmarks = {}
            
            # LLM response time benchmark
            llm_manager = get_llm_manager()
            start_time = time.time()
            response = await llm_manager.generate("Hello", system="Reply with 'Hi'")
            llm_time = time.time() - start_time
            benchmarks["llm_response_time"] = round(llm_time, 2)
            
            # Memory allocation benchmark
            start_time = time.time()
            test_data = [i for i in range(10000)]
            del test_data
            memory_time = time.time() - start_time
            benchmarks["memory_allocation_time"] = round(memory_time, 4)
            
            # File I/O benchmark
            start_time = time.time()
            with tempfile.NamedTemporaryFile() as f:
                f.write(b'x' * 1024 * 100)  # 100KB
                f.flush()
            io_time = time.time() - start_time
            benchmarks["file_io_time"] = round(io_time, 4)
            
            # Evaluate performance
            warnings = []
            if llm_time > 10:
                warnings.append("LLM response time is slow (>10s)")
            if memory_time > 0.1:
                warnings.append("Memory allocation is slow")
            if io_time > 1.0:
                warnings.append("File I/O is slow")
            
            return {
                "status": "passed" if not warnings else "warning",
                "benchmarks": benchmarks,
                "warnings": warnings
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def test_integration(self) -> Dict:
        """Test end-to-end integration."""
        try:
            # Create assistant
            assistant = AlisaAssistant()
            
            # Test text processing (simulates Telegram input)
            response = await assistant.process_text("Salom")
            text_processing_working = bool(response)
            
            # Test memory integration
            memory_working = len(assistant.memory.get_recent_messages()) > 0
            
            return {
                "status": "passed" if text_processing_working else "failed",
                "text_processing_working": text_processing_working,
                "memory_working": memory_working,
                "response_length": len(response) if response else 0
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    def generate_report(self) -> Dict:
        """Generate comprehensive deployment report."""
        passed_tests = sum(1 for r in self.results.values() if r.get("status") == "passed")
        total_tests = len(self.results)
        
        # Determine overall status
        if self.errors:
            overall_status = "failed"
        elif self.warnings:
            overall_status = "warning"
        else:
            overall_status = "passed"
        
        return {
            "overall_status": overall_status,
            "tests_passed": passed_tests,
            "total_tests": total_tests,
            "success_rate": round((passed_tests / total_tests) * 100, 1) if total_tests > 0 else 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "detailed_results": self.results,
            "deployment_ready": overall_status in ["passed", "warning"] and passed_tests >= total_tests * 0.8
        }


async def main():
    """Run deployment tests."""
    # Set up logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    tester = PiDeploymentTester()
    report = await tester.run_all_tests()
    
    # Print summary
    print("\n" + "="*60)
    print("RASPBERRY PI DEPLOYMENT TEST REPORT")
    print("="*60)
    print(f"Overall Status: {report['overall_status'].upper()}")
    print(f"Tests Passed: {report['tests_passed']}/{report['total_tests']} ({report['success_rate']}%)")
    print(f"Deployment Ready: {'YES' if report['deployment_ready'] else 'NO'}")
    
    if report['errors']:
        print(f"\nERRORS ({len(report['errors'])}):")
        for error in report['errors']:
            print(f"  ❌ {error}")
    
    if report['warnings']:
        print(f"\nWARNINGS ({len(report['warnings'])}):")
        for warning in report['warnings']:
            print(f"  ⚠️  {warning}")
    
    print(f"\nDetailed results available in: {report}")
    
    # Exit with appropriate code
    sys.exit(0 if report['deployment_ready'] else 1)


if __name__ == "__main__":
    asyncio.run(main())
