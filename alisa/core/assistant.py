"""Main Alisa AI Assistant loop."""

import asyncio
from pathlib import Path

import structlog

from alisa.core.config import get_config
from alisa.core.memory_manager import get_memory_manager
from alisa.voice.wake_word import detect_wake_word
from alisa.voice.audio_io import async_record_audio, async_play_audio, record_audio, play_audio, async_record_until_silence
from alisa.voice.stt import transcribe
from alisa.voice.tts import synthesize
from alisa.brain.llm_manager import LLMManager
from alisa.brain.memory import get_memory
from alisa.brain.online import async_handle_special_queries, async_is_online
from alisa.services.profiler import get_profiler, AsyncProfiledOperation
from alisa.services.error_recovery import get_recovery_manager, with_error_recovery, ErrorRecoveryContext, ErrorSeverity
from alisa.services.performance_monitor import get_performance_monitor

logger = structlog.get_logger()


async def async_generate(prompt: str, system_prompt: str = None) -> str:
    """Async LLM generation function for testing compatibility."""
    llm_manager = LLMManager()
    return await llm_manager.generate(prompt, system_prompt or ALISA_SYSTEM_PROMPT_UZ)

# Canonical Uzbek system prompt from PROJECT_BRIEF.md
ALISA_SYSTEM_PROMPT_UZ = (
    "Sen Alisa — aqlli yordamchi. Sen faqat o'zbek tilida gaplashasan. "
    "Javoblaring qisqa, aniq va foydali bo'lsin. "
    "Agar bilmasang, 'Bilmayman, lekin izlab ko'raman' de. "
    "Sen Raspberry Pi da ishlaysan, resepsiyada mehmonlarni kutib olasan."
)


class AlisaAssistant:
    """Main Alisa AI Assistant."""
    
    def __init__(self):
        import time
        start_time = time.time()
        
        self.config = get_config()
        self.is_running = False
        self.memory = get_memory()
        self.memory_manager = get_memory_manager()
        self.interaction_count = 0
        self.profiler = get_profiler()
        self.recovery_manager = get_recovery_manager()
        self.performance_monitor = get_performance_monitor()
        self.llm_manager = LLMManager()
        
        init_time = time.time() - start_time
        logger.info("assistant_initialized", init_time_ms=int(init_time * 1000), 
                   provider_count=len(self.llm_manager.providers))
        
    async def start(self):
        """Start the assistant main loop."""
        self.is_running = True
        logger.info("alisa_assistant_started")
        
        try:
            await detect_wake_word(self._handle_wake_word)
        except Exception as e:
            logger.error("assistant_error", error=str(e))
        finally:
            self.is_running = False
            logger.info("alisa_assistant_stopped")
    
    def stop(self):
        """Stop the assistant."""
        self.is_running = False
        
    async def _think(self, text: str) -> str:
        """Shared thinking logic: memory + LLM generation."""
        # Check for special online queries first (weather, news)
        if await async_is_online():
            special_response = await async_handle_special_queries(text)
            if special_response:
                # Add to memory for context
                self.memory.add_message("user", text)
                self.memory.add_message("assistant", special_response)
                return special_response
        
        # Add user message to memory
        self.memory.add_message("user", text)
        
        # Get context for better responses
        context = self.memory.get_context()
        
        # Generate response with context using fallback chain
        if context:
            prompt = f"{context}\nFoydalanuvchi: {text}"
        else:
            prompt = text
        
        response = await self.llm_manager.generate(prompt, system_prompt=ALISA_SYSTEM_PROMPT_UZ)
        
        # Add assistant response to memory
        self.memory.add_message("assistant", response)
        
        return response

    async def _handle_wake_word(self):
        """Handle wake word detection - listen, think, speak."""
        async with ErrorRecoveryContext("voice_pipeline", ErrorSeverity.HIGH):
            async with self.performance_monitor.measure("voice_interaction", track_memory=True):
                try:
                    logger.info("wake_word_triggered")
                    
                    # Increment interaction counter and check memory
                    self.interaction_count += 1
                    if self.interaction_count % 10 == 0:  # Check every 10 interactions
                        if self.memory_manager.monitor_and_cleanup():
                            logger.info("memory_cleanup_performed", interaction=self.interaction_count)
                    
                    # 1. Listen - record user speech with VAD
                    logger.info("listening_for_speech")
                    async with AsyncProfiledOperation(self.profiler, "audio_recording"):
                        async with self.performance_monitor.measure("audio_recording"):
                            audio_data = await async_record_until_silence(
                                max_sec=8.0,
                                silence_ms=600,
                                start_timeout_sec=1.5,
                                energy_threshold_rms=0.01
                            )
                    
                    # 2. Think - transcribe and generate response
                    logger.info("processing_speech")
                    async with AsyncProfiledOperation(self.profiler, "speech_transcription"):
                        async with self.performance_monitor.measure("speech_transcription"):
                            text = await asyncio.to_thread(transcribe, audio_data)
                    
                    if not text.strip():
                        logger.info("no_speech_detected")
                        return
                        
                    logger.info("speech_transcribed", text=text)
                    
                    # Use shared thinking logic
                    async with AsyncProfiledOperation(self.profiler, "llm_generation"):
                        async with self.performance_monitor.measure("llm_generation"):
                            response = await self._think(text)
                    
                    logger.info("response_generated", response=response)
                    
                    # 3. Speak - synthesize and play response
                    logger.info("speaking_response")
                    async with AsyncProfiledOperation(self.profiler, "speech_synthesis"):
                        async with self.performance_monitor.measure("speech_synthesis"):
                            audio_path = await asyncio.to_thread(synthesize, response)
                    
                    if audio_path and Path(audio_path).exists():
                        async with self.performance_monitor.measure("audio_playback"):
                            await async_play_audio(audio_path)
                        # Clean up temp file
                        Path(audio_path).unlink(missing_ok=True)
                    else:
                        logger.warning("tts_failed", response=response)
                        
                except Exception as e:
                    logger.error("conversation_error", error=str(e))
                    # Error is automatically recorded by ErrorRecoveryContext
    
    async def process_text(self, text: str) -> str:
        """Process text input directly (for Telegram bot)."""
        async with ErrorRecoveryContext("text_processing", ErrorSeverity.MEDIUM):
            async with self.performance_monitor.measure("text_processing"):
                try:
                    # Validate input explicitly
                    if not text or not isinstance(text, str):
                        return "Kechirasiz, javob bera olmadim."
                    
                    # Use shared thinking logic
                    async with self.performance_monitor.measure("text_llm_generation"):
                        response = await self._think(text)
                    
                    logger.info("text_processed", input=text, response=response)
                    return response
                except Exception as e:
                    logger.error("text_processing_error", error=str(e))
                    return "Kechirasiz, javob bera olmadim."


async def main():
    """Main entry point."""
    assistant = AlisaAssistant()
    
    try:
        await assistant.start()
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        assistant.stop()


if __name__ == "__main__":
    asyncio.run(main())
