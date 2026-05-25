"""Speech-to-Text module with faster-whisper and Uzbek fine-tuned model support.

Supports:
- HuggingFace fine-tuned models (BlueRaccoon/whisper-small-uz, islomov/rubaistt_v2_medium)
- Standard faster-whisper models (small, medium, etc.)
- whisper.cpp subprocess fallback
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import structlog

from alisa.core.config import get_config
from alisa.voice.dialect_normalizer import post_process_stt, get_initial_prompt_for_uzbek

logger = structlog.get_logger()

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logger.info("faster_whisper_not_available", fallback="whisper.cpp")

# Global model instance (stays loaded in memory)
_whisper_model: Optional[object] = None


def _get_whisper_model():
    """Get or initialize the faster-whisper model (singleton).
    
    Supports both standard models ('small', 'medium') and 
    HuggingFace model IDs ('BlueRaccoon/whisper-small-uz').
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    cfg = get_config().get("stt", {})
    model_id = cfg.get("model", "BlueRaccoon/whisper-small-uz")
    device = cfg.get("device", "cpu")
    compute_type = cfg.get("compute_type", "int8")

    logger.info("loading_whisper_model", model=model_id, device=device, compute_type=compute_type)

    _whisper_model = WhisperModel(
        model_id,
        device=device,
        compute_type=compute_type,
        cpu_threads=cfg.get("cpu_threads", 4),
    )

    logger.info("whisper_model_loaded", model=model_id)
    return _whisper_model


def transcribe(wav_bytes: bytes) -> str:
    """Transcribe WAV audio bytes to text."""
    if not wav_bytes:
        return ""

    if FASTER_WHISPER_AVAILABLE:
        return post_process_stt(_transcribe_faster_whisper(wav_bytes))
    else:
        return post_process_stt(_transcribe_whisper_cpp(wav_bytes))


def _transcribe_faster_whisper(wav_bytes: bytes) -> str:
    """Transcribe using faster-whisper with Uzbek fine-tuned model."""
    cfg = get_config().get("stt", {})
    language = cfg.get("language", "uz")

    temp_dir = "/dev/shm" if os.path.exists("/dev/shm") else None
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=temp_dir)
    try:
        tmp.write(wav_bytes)
        tmp.close()

        model = _get_whisper_model()

        segments, info = model.transcribe(
            tmp.name,
            language=language,
            beam_size=cfg.get("beam_size", 3),
            best_of=cfg.get("best_of", 3),
            temperature=cfg.get("temperature", 0.0),
            initial_prompt=cfg.get("initial_prompt", None) or get_initial_prompt_for_uzbek(),
            vad_filter=cfg.get("vad_filter", True),
            vad_parameters=dict(
                min_silence_duration_ms=cfg.get("vad_min_silence_ms", 500),
                speech_pad_ms=cfg.get("vad_speech_pad_ms", 200),
            ),
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info("stt_done", text_len=len(text), language=info.language,
                   probability=f"{info.language_probability:.2f}", method="faster_whisper")
        return text

    except Exception as e:
        logger.error("faster_whisper_error", error=str(e))
        return _transcribe_whisper_cpp(wav_bytes)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _transcribe_whisper_cpp(wav_bytes: bytes) -> str:
    """Transcribe using whisper.cpp subprocess (fallback)."""
    cfg = get_config().get("whisper", {})
    binary = cfg.get("binary", "/usr/local/bin/whisper-cli")
    model = cfg.get("model", "/opt/alisa/models/ggml-base.bin")
    language = cfg.get("language", "uz")

    temp_dir = "/dev/shm" if os.path.exists("/dev/shm") else None
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=temp_dir)
    try:
        tmp.write(wav_bytes)
        tmp.close()

        cmd = [binary, "-m", model, "-l", language, "-f", tmp.name, "--no-timestamps"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error("whisper_cpp_failed", stderr=result.stderr[:200])
            return ""

        text = result.stdout.strip()
        logger.info("stt_done", text_len=len(text), method="whisper_cpp")
        return text

    except subprocess.TimeoutExpired:
        logger.error("whisper_cpp_timeout")
        return ""
    except FileNotFoundError:
        logger.error("whisper_binary_not_found", binary=binary)
        return ""
    except Exception as e:
        logger.error("stt_error", error=str(e))
        return ""
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def unload_model():
    """Unload the whisper model to free memory."""
    global _whisper_model
    if _whisper_model is not None:
        del _whisper_model
        _whisper_model = None
        logger.info("whisper_model_unloaded")
