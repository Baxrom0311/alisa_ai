"""Wake word detection for Alisa AI Assistant.

This module provides wake word detection using either openWakeWord (when available)
or an energy-gated fallback with STT confirmation. 

Note: The current implementation uses the "alexa" openWakeWord model as a phonetic
proxy for "alisa" since no dedicated "alisa" ONNX model is bundled. This is a
known limitation that will be addressed in future versions.
"""

import asyncio
import struct
import time
import wave
from pathlib import Path

import structlog

from alisa.core.config import get_config
from alisa.voice.audio_io import record_audio

logger = structlog.get_logger()

# Try to import openWakeWord for more efficient detection
try:
    import openwakeword
    from openwakeword import Model
    OPENWAKEWORD_AVAILABLE = True
    logger.info("openwakeword_available", status="enabled")
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    logger.info("openwakeword_available", status="disabled", fallback="energy_gated")


class WakeWordDetector:
    """Wake word detector with optional openWakeWord support."""
    
    def __init__(self):
        self.config = get_config()
        
        # Get wake word configuration (handle both string and dict formats)
        wake_word_config = self.config.get("wake_word", {})
        
        # Handle backward compatibility with string format
        if isinstance(wake_word_config, str):
            self.keyword = wake_word_config.lower()
            self.sensitivity = 0.05
            self.confirmation_cooldown = 5.0
            self.method = "auto"
            self.allow_proxy_model = False  # Default to false for backward compatibility
            self.oww_model_name = "alexa"
            self.oww_framework = "onnx"
            self.energy_threshold = 500
            self.min_duration_ms = 100
        else:
            # New explicit nested format
            self.keyword = wake_word_config.get("keyword", "alisa").lower()
            self.sensitivity = wake_word_config.get("sensitivity", 0.05)
            self.confirmation_cooldown = wake_word_config.get("confirmation_cooldown_sec", 5.0)
            self.method = wake_word_config.get("method", "auto").lower()
            self.allow_proxy_model = wake_word_config.get("allow_proxy_model", False)
            
            # OpenWakeWord specific config
            oww_config = wake_word_config.get("openwakeword", {})
            self.oww_model_name = oww_config.get("model", "alexa")
            self.oww_framework = oww_config.get("inference_framework", "onnx")
            
            # Energy-gated specific config
            energy_config = wake_word_config.get("energy_gated", {})
            self.energy_threshold = energy_config.get("threshold", 500)
            self.min_duration_ms = energy_config.get("min_duration_ms", 100)
        
        self.is_listening = False
        self.oww_model = None
        self.last_confirmation_attempt = 0  # Cooldown tracking
        
        # Check for proxy model condition: keyword='alisa' AND model='alexa'
        is_proxy_model = (self.keyword == "alisa" and self.oww_model_name == "alexa")
        
        # Initialize based on method preference and proxy model policy
        if self.method in ["auto", "openwakeword"] and OPENWAKEWORD_AVAILABLE:
            # If using proxy model without explicit permission, prefer energy-gated
            if is_proxy_model and not self.allow_proxy_model:
                logger.info("wake_word_proxy_disabled", 
                           keyword=self.keyword, 
                           oww_model=self.oww_model_name,
                           message="Using energy-gated detection instead of proxy model")
                self.oww_model = None
            else:
                try:
                    self._init_openwakeword()
                except Exception as e:
                    logger.warning("openwakeword_init_failed", error=str(e), fallback="energy_gated")
                    self.oww_model = None
                    if self.method == "openwakeword":
                        # If explicitly requested openwakeword but failed, log error
                        logger.error("openwakeword_required_but_failed", method=self.method)
        elif self.method == "openwakeword" and not OPENWAKEWORD_AVAILABLE:
            logger.error("openwakeword_not_available", method=self.method, fallback="energy_gated")
        
    def _init_openwakeword(self):
        """Initialize openWakeWord model with explicit configuration."""
        # Use configured model and framework
        self.oww_model = Model(
            wakeword_models=[self.oww_model_name], 
            inference_framework=self.oww_framework
        )
        
        # Always warn about model proxy usage for transparency
        if self.oww_model_name != self.keyword:
            logger.warning("wake_word_model_proxy", 
                          configured_keyword=self.keyword,
                          oww_model=self.oww_model_name,
                          framework=self.oww_framework,
                          message=f"Using '{self.oww_model_name}' model as phonetic proxy for '{self.keyword}'")
        
        logger.info("openwakeword_initialized", 
                   model=self.oww_model_name, 
                   framework=self.oww_framework,
                   target_keyword=self.keyword)
        
    async def start_listening(self, callback):
        """Start listening for wake word."""
        self.is_listening = True
        
        # Determine actual method being used
        if self.oww_model:
            actual_method = "openwakeword"
            method_details = f"model={self.oww_model_name}, framework={self.oww_framework}"
        else:
            actual_method = "energy_gated"
            method_details = f"threshold={self.energy_threshold}, min_duration={self.min_duration_ms}ms"
        
        logger.info("wake_word_listening_started", 
                   keyword=self.keyword, 
                   configured_method=self.method,
                   actual_method=actual_method,
                   details=method_details)
        
        while self.is_listening:
            try:
                # Record 2 seconds of audio
                audio_data = await asyncio.to_thread(record_audio, duration_sec=2.0)
                
                # Use openWakeWord if available, otherwise fall back to energy-gated
                if self.oww_model:
                    if await self._detect_with_openwakeword(audio_data):
                        logger.info("wake_word_detected", keyword=self.keyword, method="openwakeword")
                        await callback()
                else:
                    # Original energy-gated method
                    if self._has_sufficient_energy(audio_data):
                        if await self._confirm_keyword(audio_data):
                            logger.info("wake_word_detected", keyword=self.keyword, method="energy_gated")
                            await callback()
                    
                # Small delay to prevent CPU overload
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error("wake_word_detection_error", error=str(e))
                await asyncio.sleep(1.0)
    
    async def _detect_with_openwakeword(self, audio_data: bytes) -> bool:
        """Detect wake word using openWakeWord."""
        try:
            # Convert bytes to numpy array for openWakeWord
            import numpy as np
            
            # Convert 16-bit PCM to float32 array
            samples = struct.unpack(f"<{len(audio_data)//2}h", audio_data)
            audio_array = np.array(samples, dtype=np.float32) / 32768.0
            
            # Run prediction
            prediction = await asyncio.to_thread(self.oww_model.predict, audio_array)
            
            # Check if configured model was detected above threshold
            model_score = prediction.get(self.oww_model_name, 0.0)
            threshold = self.sensitivity  # Reuse sensitivity config
            
            logger.debug("openwakeword_prediction", 
                        model=self.oww_model_name,
                        score=model_score, 
                        threshold=threshold)
            return model_score > threshold
            
        except Exception as e:
            logger.error("openwakeword_detection_error", error=str(e))
            return False
    
    def stop_listening(self):
        """Stop listening for wake word."""
        self.is_listening = False
        logger.info("wake_word_listening_stopped")
    
    def _has_sufficient_energy(self, audio_data: bytes) -> bool:
        """Check if audio has sufficient energy to warrant transcription."""
        # Convert bytes to samples
        samples = struct.unpack(f"<{len(audio_data)//2}h", audio_data)
        
        # Calculate RMS energy
        rms = (sum(s*s for s in samples) / len(samples)) ** 0.5
        
        # Use configured energy threshold
        return rms > self.energy_threshold
    
    async def _confirm_keyword(self, audio_data: bytes) -> bool:
        """Confirm keyword using STT transcription with cooldown."""
        current_time = time.time()
        
        # Check cooldown to prevent continuous whisper invocations
        if current_time - self.last_confirmation_attempt < self.confirmation_cooldown:
            logger.debug("wake_word_confirmation_cooldown", 
                        remaining=self.confirmation_cooldown - (current_time - self.last_confirmation_attempt))
            return False
        
        self.last_confirmation_attempt = current_time
        
        try:
            # Import here to avoid circular imports
            from alisa.voice.stt import transcribe
            
            # Transcribe the audio segment
            transcript = await asyncio.to_thread(transcribe, audio_data)
            
            if not transcript:
                return False
            
            # Normalize transcript for comparison
            transcript_lower = transcript.lower().strip()
            
            # Check for keyword (allow simple variants)
            keyword_variants = [
                self.keyword,
                f"{self.keyword},",
                f"{self.keyword}.",
                f"{self.keyword}!",
                f"{self.keyword}?"
            ]
            
            # Check if any variant is found in the transcript
            for variant in keyword_variants:
                if variant in transcript_lower:
                    logger.debug("wake_word_confirmed", 
                               transcript=transcript, 
                               keyword=self.keyword)
                    return True
            
            logger.debug("wake_word_not_confirmed", 
                        transcript=transcript, 
                        keyword=self.keyword)
            return False
            
        except Exception as e:
            logger.error("wake_word_confirmation_error", error=str(e))
            return False


async def detect_wake_word(callback):
    """Convenience function to start wake word detection."""
    detector = WakeWordDetector()
    await detector.start_listening(callback)
