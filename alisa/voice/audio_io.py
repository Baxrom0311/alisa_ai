"""Audio I/O module for recording and playback."""

import asyncio
import io
import struct
import wave

import sounddevice as sd
import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()


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
            # Convert bytes to int16 array
            samples = struct.unpack(f"<{len(frames)//2}h", frames)

        import numpy as np
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
    """Record audio until silence is detected using energy-based VAD.
    
    Args:
        max_sec: Maximum recording duration (hard cap)
        silence_ms: Milliseconds of silence to stop recording
        start_timeout_sec: Timeout to wait for speech to start
        energy_threshold_rms: RMS energy threshold to detect speech
        
    Returns:
        WAV bytes of recorded audio
    """
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
                import numpy as np
                # Ensure frame is float32 for calculation
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
    import numpy as np
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
