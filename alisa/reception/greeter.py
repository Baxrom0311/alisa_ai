"""Guest greeting and reception mode logic."""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable

from ..core.config import get_config
from ..voice.stt import transcribe
from ..voice.tts import synthesize
from ..voice.audio_io import async_record_audio, async_play_audio, record_audio, play_audio, async_record_until_silence
from ..brain.llm_manager import get_llm_manager
from .knowledge import KnowledgeBase


logger = logging.getLogger(__name__)


class ReceptionGreeter:
    """Handles guest greeting and reception mode."""
    
    def __init__(self, telegram_notifier: Optional[Callable] = None):
        self.config = get_config()
        self.knowledge = KnowledgeBase()
        self.telegram_notifier = telegram_notifier
        self.is_active = False
        self.guest_log = []
    
    async def start_reception_mode(self):
        """Start reception mode - listen for guests."""
        self.is_active = True
        logger.info("Reception mode started")
        
        try:
            while self.is_active:
                # Use proper VAD to detect voice activity
                audio_data = await async_record_until_silence(
                    max_sec=3.0,
                    silence_ms=800,
                    start_timeout_sec=2.0,
                    energy_threshold_rms=0.02
                )
                
                if audio_data:
                    await self._handle_guest()
                
                # Small delay to prevent CPU overload
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Reception mode error: {e}")
        finally:
            logger.info("Reception mode stopped")
    
    def stop_reception_mode(self):
        """Stop reception mode."""
        self.is_active = False
    
    async def _handle_guest(self):
        """Handle a detected guest."""
        logger.info("Guest detected")
        
        # Greet the guest
        greeting = self.knowledge.get_greeting()
        await self._speak(greeting)
        
        # Log the visit
        visit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.guest_log.append({
            "time": visit_time,
            "greeted": True
        })
        
        # Notify via Telegram if configured
        if self.telegram_notifier:
            try:
                await self.telegram_notifier(f"🔔 Mehmon keldi: {visit_time}")
            except Exception as e:
                logger.error(f"Telegram notification failed: {e}")
        
        # Listen for questions
        await self._handle_conversation()
    
    async def _handle_conversation(self):
        """Handle conversation with guest."""
        max_exchanges = 3  # Limit conversation length
        
        for _ in range(max_exchanges):
            try:
                # Listen for question using VAD
                audio_data = await async_record_until_silence(
                    max_sec=8.0,
                    silence_ms=1000,
                    start_timeout_sec=3.0,
                    energy_threshold_rms=0.015
                )
                
                if not audio_data:
                    break
                
                question = await asyncio.to_thread(transcribe, audio_data)
                
                if not question or len(question.strip()) < 3:
                    break
                
                logger.info(f"Guest question: {question}")
                
                # Try to find FAQ answer first
                answer = self.knowledge.find_answer(question)
                
                if not answer:
                    # Fallback to LLM for more complex questions
                    system_prompt = """Siz reception xodimisiz. Qisqa va foydali javob bering. 
                    Agar javob bilmasangiz, "Kechirasiz, bu haqida aniq ma'lumotim yo'q" deng."""
                    llm_manager = get_llm_manager()
                    answer = await llm_manager.generate(question, system_prompt=system_prompt)
                    
                    if not answer:
                        answer = self.knowledge.get_default_response()
                
                # Speak the answer
                await self._speak(answer)
                
                # Small pause between exchanges
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Conversation error: {e}")
                break
    
    async def _speak(self, text: str):
        """Convert text to speech and play it."""
        try:
            wav_path = synthesize(text)
            if wav_path:
                await async_play_audio(wav_path)
        except Exception as e:
            logger.error(f"Speech synthesis error: {e}")
    
    def get_guest_log(self) -> list:
        """Get list of recent guests."""
        return self.guest_log.copy()
    
    def clear_guest_log(self):
        """Clear guest log."""
        self.guest_log.clear()
        logger.info("Guest log cleared")


async def async_generate(prompt: str, system_prompt: str = None) -> str:
    """Async LLM generation function for testing compatibility."""
    llm_manager = get_llm_manager()
    return await llm_manager.generate(prompt, system_prompt or "Siz reception xodimisiz. Qisqa va foydali javob bering.")
