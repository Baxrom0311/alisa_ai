"""Text-to-Speech module with Facebook MMS-TTS Uzbek (primary) and fallbacks.

Priority:
1. Facebook MMS-TTS-uzb — real Uzbek voice, neural TTS
2. Piper TTS — fast, but no native Uzbek model
3. espeak-ng — always available, supports Uzbek
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()

# Try to import MMS-TTS dependencies
_mms_model = None
_mms_tokenizer = None
_mms_available = False

try:
    from transformers import VitsModel, AutoTokenizer
    import torch
    import numpy as np
    _mms_available = True
except ImportError:
    logger.info("mms_tts_not_available", fallback="piper/espeak")


def _get_mms_model():
    """Load Facebook MMS-TTS Uzbek model (singleton)."""
    global _mms_model, _mms_tokenizer
    if _mms_model is not None:
        return _mms_model, _mms_tokenizer

    cfg = get_config().get("tts", {})
    model_id = cfg.get("mms_model", "facebook/mms-tts-uzb-script_latin")

    logger.info("loading_mms_tts", model=model_id)
    _mms_tokenizer = AutoTokenizer.from_pretrained(model_id)
    _mms_model = VitsModel.from_pretrained(model_id)
    logger.info("mms_tts_loaded", model=model_id)
    return _mms_model, _mms_tokenizer


def synthesize(text: str) -> Optional[str]:
    """Synthesize text to WAV file. Returns WAV path or None."""
    if not text or not text.strip():
        return None

    # Try MMS-TTS first (real Uzbek voice)
    if _mms_available:
        result = _synthesize_mms(text)
        if result:
            return result

    # Piper fallback
    result = _synthesize_piper(text)
    if result:
        return result

    # espeak-ng fallback
    return _synthesize_espeak(text)


def _synthesize_mms(text: str) -> Optional[str]:
    """Synthesize using Facebook MMS-TTS Uzbek."""
    try:
        import torch
        import numpy as np
        import wave

        model, tokenizer = _get_mms_model()

        inputs = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            output = model(**inputs).waveform

        # Convert to WAV
        audio_np = output.squeeze().cpu().numpy()
        audio_int16 = (audio_np * 32767).astype(np.int16)

        output_dir = Path("/tmp/alisa_tts")
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = tempfile.NamedTemporaryFile(suffix=".wav", dir=str(output_dir), delete=False)
        out_path = out_file.name
        out_file.close()

        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(model.config.sampling_rate)
            wf.writeframes(audio_int16.tobytes())

        logger.info("tts_done", path=out_path, engine="mms-tts-uzb")
        return out_path

    except Exception as e:
        logger.error("mms_tts_error", error=str(e))
        return None


def _synthesize_piper(text: str) -> Optional[str]:
    """Synthesize using Piper TTS."""
    cfg = get_config().get("piper", {})
    binary = cfg.get("binary", "/usr/local/bin/piper")
    model = cfg.get("model", "/opt/alisa/models/tr_TR-fahrettin-medium.onnx")

    output_dir = Path(cfg.get("output_dir", "/tmp/alisa_tts"))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = tempfile.NamedTemporaryFile(suffix=".wav", dir=str(output_dir), delete=False)
    out_path = out_file.name
    out_file.close()

    try:
        result = subprocess.run(
            [binary, "--model", model, "--output_file", out_path],
            input=text, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and Path(out_path).stat().st_size > 100:
            logger.info("tts_done", path=out_path, engine="piper")
            return out_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    Path(out_path).unlink(missing_ok=True)
    return None


def _synthesize_espeak(text: str) -> Optional[str]:
    """Synthesize using espeak-ng (supports Uzbek natively)."""
    output_dir = Path("/tmp/alisa_tts")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = tempfile.NamedTemporaryFile(suffix=".wav", dir=str(output_dir), delete=False)
    out_path = out_file.name
    out_file.close()

    cfg = get_config().get("tts", {})
    speed = cfg.get("espeak_speed", 140)

    try:
        result = subprocess.run(
            ["espeak-ng", "-v", "uz", "-s", str(speed), "-w", out_path, text],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and Path(out_path).stat().st_size > 100:
            logger.info("tts_done", path=out_path, engine="espeak-ng")
            return out_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    Path(out_path).unlink(missing_ok=True)
    return None


def unload_model():
    """Unload TTS model to free memory."""
    global _mms_model, _mms_tokenizer
    if _mms_model is not None:
        del _mms_model, _mms_tokenizer
        _mms_model = None
        _mms_tokenizer = None
        logger.info("mms_tts_model_unloaded")
