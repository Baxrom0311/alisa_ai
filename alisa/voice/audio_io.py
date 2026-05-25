"""Audio I/O module for recording and playback with Silero VAD support."""

import asyncio
import io
import struct
import wave

import numpy as np
import sounddevice as sd
import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()

# Try to load Silero VAD
_silero_vad_model = None
_silero_available = False

def _get_silero_vad():
    """Load Silero VAD model (singleton)."""
    global _silero_vad_model, _silero_available
    if _silero_vad_model is not None:
        return _silero_vad_model
    try:
        import torch
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            trust_repo=True,
        )
        _silero_vad_model = model
        _silero_available = True
        logger.info("silero_vad_loaded")
        return model
    except Exception as e:
        logger.info("silero_vad_unavailable", error=str(e), fallback="energy_based")
        _silero_available = False
        return None


def record_audio(duration_sec: float = 5.0) -> bytes:
    """Record audio from microphone, return WAV bytes."""
    cfg = get_config()["audio"]
    sample_rate = cfg["sample_rate"]
    channels = cfg["channels"]
    device = cfg["input_device"]

    try:
        audio = sd.rec(
            int(duration_sec * sample_rate),
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            device=device,
        )
        sd.wait()
    except Exception as e:
        logger.error("record_failed", error=str(e))
        return b""

    # Pack into WAV bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def play_audio(wav_path: str) -> None:
    """Play a WAV file through speaker."""
    cfg = get_config()["audio"]
    device = cfg["output_device"]

    try:
        with wave.open(wav_path, "rb") as wf:
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            samples = struct.unpack(f"<{len(frames)//2}h", frames)

        audio_array = np.array(samples, dtype="int16")
        sd.play(audio_array, samplerate=rate, device=device)
        sd.wait()
    except Exception as e:
        logger.error("play_failed", error=str(e), path=wav_path)


async def async_record_audio(duration_sec: float = 5.0) -> bytes:
    """Async wrapper for record_audio to avoid blocking the event loop."""
    return await asyncio.to_thread(record_audio, duration_sec)


async def async_play_audio(wav_path: str) -> None:
    """Async wrapper for play_audio to avoid blocking the event loop."""
    await asyncio.to_thread(play_audio, wav_path)


def record_until_silence(
    max_sec: float = 8.0,
    silence_ms: int = 600,
    start_timeout_sec: float = 1.5,
    energy_threshold_rms: float = 0.01
) -> bytes:
    """Record audio until silence is detected.
    
    Uses Silero VAD (neural network) if available, falls back to energy-based.
    """
    vad_model = _get_silero_vad()
    if vad_model and _silero_available:
        return _record_with_silero_vad(vad_model, max_sec, silence_ms, start_timeout_sec)
    else:
        return _record_with_energy_vad(max_sec, silence_ms, start_timeout_sec, energy_threshold_rms)


def _record_with_silero_vad(
    vad_model,
    max_sec: float = 8.0,
    silence_ms: int = 600,
    start_timeout_sec: float = 1.5,
) -> bytes:
    """Record using Silero VAD for accurate speech detection."""
    import torch
    
    cfg = get_config()["audio"]
    sample_rate = cfg["sample_rate"]  # Must be 16000 for Silero
    channels = cfg["channels"]
    device = cfg["input_device"]
    
    # Silero VAD works with 512 sample chunks at 16kHz (32ms)
    chunk_size = 512
    silence_chunks_needed = int(silence_ms / 32)
    start_timeout_chunks = int(start_timeout_sec * 1000 / 32)
    max_chunks = int(max_sec * 1000 / 32)
    
    recorded_frames = []
    silence_count = 0
    speech_started = False
    chunks_processed = 0
    
    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            device=device,
            blocksize=chunk_size
        ) as stream:
            while chunks_processed < max_chunks:
                frame, overflowed = stream.read(chunk_size)
                chunks_processed += 1
                
                # Convert to float32 tensor for Silero
                audio_float = frame.astype(np.float32).flatten() / 32768.0
                audio_tensor = torch.from_numpy(audio_float)
                
                # Get speech probability
                speech_prob = vad_model(audio_tensor, sample_rate).item()
                
                if not speech_started:
                    if speech_prob > 0.5:
                        speech_started = True
                        recorded_frames.append(frame)
                        silence_count = 0
                        logger.info("speech_detected_silero", prob=f"{speech_prob:.2f}")
                    elif chunks_processed > start_timeout_chunks:
                        logger.warning("speech_start_timeout")
                        break
                else:
                    recorded_frames.append(frame)
                    if speech_prob < 0.3:
                        silence_count += 1
                        if silence_count >= silence_chunks_needed:
                            logger.info("silence_detected_silero", duration_ms=silence_count * 32)
                            break
                    else:
                        silence_count = 0
                        
    except Exception as e:
        logger.error("silero_vad_record_failed", error=str(e))
        return b""
    
    # Reset VAD state for next call
    try:
        vad_model.reset_states()
    except Exception:
        pass
    
    if not recorded_frames:
        return b""
    
    audio_data = np.concatenate(recorded_frames, axis=0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())
    
    duration = len(recorded_frames) * 32 / 1000
    logger.info("vad_recording_complete", duration_sec=f"{duration:.1f}", method="silero")
    return buf.getvalue()


def _record_with_energy_vad(
    max_sec: float = 8.0,
    silence_ms: int = 600,
    start_timeout_sec: float = 1.5,
    energy_threshold_rms: float = 0.01
) -> bytes:
    """Record audio until silence using energy-based VAD (fallback)."""
    cfg = get_config()["audio"]
    sample_rate = cfg["sample_rate"]
    channels = cfg["channels"]
    device = cfg["input_device"]
    
    # Frame size for VAD analysis (100ms chunks)
    frame_duration_ms = 100
    frame_size = int(sample_rate * frame_duration_ms / 1000)
    silence_frames_needed = silence_ms // frame_duration_ms
    start_timeout_frames = int(start_timeout_sec * 1000 / frame_duration_ms)
    
    recorded_frames = []
    silence_frame_count = 0
    speech_started = False
    frames_since_start = 0
    
    try:
        # Start streaming
        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            device=device,
            blocksize=frame_size
        ) as stream:
            
            while frames_since_start < int(max_sec * 1000 / frame_duration_ms):
                # Read one frame
                frame, overflowed = stream.read(frame_size)
                if overflowed:
                    logger.warning("audio_buffer_overflow")
                
                frames_since_start += 1
                
                # Calculate RMS energy
                frame_float = frame.astype(np.float32)
                rms = np.sqrt(np.mean(frame_float ** 2)) / 32768.0  # Normalize to 0-1 range
                
                # Check if speech has started
                if not speech_started:
                    if rms > energy_threshold_rms:
                        speech_started = True
                        logger.info("speech_detected", rms=rms)
                        recorded_frames.append(frame)
                        silence_frame_count = 0
                    elif frames_since_start > start_timeout_frames:
                        logger.warning("speech_start_timeout")
                        break
                else:
                    # Speech has started, record everything
                    recorded_frames.append(frame)
                    
                    # Check for silence
                    if rms <= energy_threshold_rms:
                        silence_frame_count += 1
                        if silence_frame_count >= silence_frames_needed:
                            logger.info("silence_detected", duration_ms=silence_frame_count * frame_duration_ms)
                            break
                    else:
                        silence_frame_count = 0
                        
    except Exception as e:
        logger.error("vad_record_failed", error=str(e))
        return b""
    
    if not recorded_frames:
        logger.warning("no_audio_recorded")
        return b""
    
    # Convert frames to WAV bytes
    audio_data = np.concatenate(recorded_frames, axis=0)
    
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())
    
    duration = len(recorded_frames) * frame_duration_ms / 1000
    logger.info("vad_recording_complete", duration_sec=duration, frames=len(recorded_frames))
    return buf.getvalue()


async def async_record_until_silence(
    max_sec: float = 8.0,
    silence_ms: int = 600,
    start_timeout_sec: float = 1.5,
    energy_threshold_rms: float = 0.01
) -> bytes:
    """Async wrapper for record_until_silence to avoid blocking the event loop."""
    return await asyncio.to_thread(
        record_until_silence, max_sec, silence_ms, start_timeout_sec, energy_threshold_rms
    )


def test_audio_devices() -> dict:
    """Test audio input/output device availability."""
    try:
        import sounddevice as sd
        
        # Get device info
        devices = sd.query_devices()
        
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        output_devices = [d for d in devices if d['max_output_channels'] > 0]
        
        # Test default devices
        try:
            default_input = sd.query_devices(kind='input')
            input_available = True
        except Exception:
            input_available = False
        
        try:
            default_output = sd.query_devices(kind='output')
            output_available = True
        except Exception:
            output_available = False
        
        return {
            "input_available": input_available,
            "output_available": output_available,
            "input_device_count": len(input_devices),
            "output_device_count": len(output_devices),
            "total_devices": len(devices)
        }
    
    except ImportError:
        logger.warning("sounddevice not available for audio testing")
        return {
            "input_available": False,
            "output_available": False,
            "input_device_count": 0,
            "output_device_count": 0,
            "total_devices": 0,
            "error": "sounddevice not installed"
        }
    except Exception as e:
        logger.error("audio_device_test_failed", error=str(e))
        return {
            "input_available": False,
            "output_available": False,
            "input_device_count": 0,
            "output_device_count": 0,
            "total_devices": 0,
            "error": str(e)
        }
