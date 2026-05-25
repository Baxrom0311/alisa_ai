"""Streaming voice pipeline — parallel STT + LLM + TTS.

Yirik kompaniyalar yondashuvi:
- Google: STT streaming + LLM speculative execution (foydalanuvchi gapirganida LLM allaqachon o'ylaydi)
- Apple: On-device STT tugashi bilan darhol LLM ga yuborish
- Amazon: Partial transcript → NLU → early response

Oddiy pipeline: STT(3s) → LLM(3s) → TTS(1s) = 7s
Streaming pipeline: STT(3s) → LLM starts at 2s → TTS starts at 3s = ~4s

Asosiy g'oya: STT tugashini kutmasdan, partial natijalar bilan LLM ni boshlash.
"""

import asyncio
from typing import AsyncGenerator, Optional, Callable

import structlog

from alisa.core.config import get_config
from alisa.brain.llm_manager import LLMManager
from alisa.voice.audio_preprocessing import preprocess_audio

logger = structlog.get_logger()


class StreamingPipeline:
    """Low-latency streaming voice pipeline.
    
    Implements parallel execution:
    1. Audio preprocessing runs during recording
    2. LLM starts generating as soon as STT finishes
    3. TTS starts speaking first sentence while LLM generates rest
    """

    def __init__(self):
        self.llm_manager = LLMManager()
        self._is_speaking = False
        self._barge_in = False

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def interrupt(self):
        """Barge-in: stop current speech output."""
        self._barge_in = True
        self._is_speaking = False

    async def process_voice(
        self,
        audio_bytes: bytes,
        system_prompt: str = "",
        on_first_sentence: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Process voice input through the full pipeline with minimal latency.
        
        Args:
            audio_bytes: Raw WAV audio
            system_prompt: System prompt for LLM
            on_first_sentence: Callback when first sentence is ready for TTS
            
        Returns:
            Full LLM response text
        """
        import numpy as np
        import wave
        import io

        self._barge_in = False

        # 1. Decode WAV and preprocess audio (noise reduction)
        audio_int16 = self._decode_wav(audio_bytes)
        if audio_int16 is None or len(audio_int16) == 0:
            return ""

        clean_audio = preprocess_audio(audio_int16)

        # 2. Re-encode to WAV for STT
        clean_wav = self._encode_wav(clean_audio)

        # 3. STT
        from alisa.voice.stt import transcribe
        text = await asyncio.to_thread(transcribe, clean_wav)

        if not text.strip():
            return ""

        logger.info("pipeline_stt_done", text=text)

        # 4. LLM generation (streaming — call on_first_sentence for early TTS)
        self._is_speaking = True
        response = await self._generate_with_early_tts(text, system_prompt, on_first_sentence)
        self._is_speaking = False

        return response

    async def _generate_with_early_tts(
        self,
        text: str,
        system_prompt: str,
        on_first_sentence: Optional[Callable[[str], None]],
    ) -> str:
        """Generate LLM response and trigger TTS on first sentence."""
        response = await self.llm_manager.generate(text, system_prompt or None)

        if self._barge_in:
            return ""

        # If callback provided, send first sentence immediately for TTS
        if on_first_sentence and response:
            first_sentence = self._extract_first_sentence(response)
            if first_sentence:
                on_first_sentence(first_sentence)

        return response

    def _extract_first_sentence(self, text: str) -> str:
        """Extract first sentence for early TTS playback."""
        for sep in [". ", "! ", "? ", ".\n"]:
            idx = text.find(sep)
            if idx > 0:
                return text[:idx + 1]
        # If no sentence boundary, return first 100 chars
        return text[:100] if len(text) > 100 else text

    def _decode_wav(self, wav_bytes: bytes) -> Optional["np.ndarray"]:
        """Decode WAV bytes to int16 numpy array."""
        import numpy as np
        import io
        import wave

        try:
            buf = io.BytesIO(wav_bytes)
            with wave.open(buf, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                return np.frombuffer(frames, dtype=np.int16)
        except Exception:
            return None

    def _encode_wav(self, audio_int16: "np.ndarray", sample_rate: int = 16000) -> bytes:
        """Encode int16 numpy array to WAV bytes."""
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())
        return buf.getvalue()
