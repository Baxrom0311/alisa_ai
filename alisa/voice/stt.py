"""Speech-to-Text module using whisper.cpp subprocess."""

import os
import subprocess
import tempfile
from pathlib import Path

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()


def transcribe(wav_bytes: bytes) -> str:
    """Transcribe WAV audio bytes to text using whisper.cpp CLI."""
    if not wav_bytes:
        return ""

    cfg = get_config()["whisper"]
    binary = cfg["binary"]
    model = cfg["model"]
    language = cfg["language"]

    # Prefer /dev/shm for temp files to reduce SD card wear
    temp_dir = None
    if os.path.exists("/dev/shm") and os.access("/dev/shm", os.W_OK):
        temp_dir = "/dev/shm"

    # Write WAV to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=temp_dir)
    try:
        tmp.write(wav_bytes)
        tmp.close()

        cmd = [
            binary,
            "-m", model,
            "-l", language,
            "-f", tmp.name,
            "--no-timestamps",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            logger.error("whisper_failed", stderr=result.stderr[:200])
            return ""

        text = result.stdout.strip()
        logger.info("stt_done", text_len=len(text), temp_dir=temp_dir or "system")
        return text

    except subprocess.TimeoutExpired:
        logger.error("whisper_timeout")
        return ""
    except FileNotFoundError:
        logger.error("whisper_binary_not_found", binary=binary)
        return ""
    except Exception as e:
        logger.error("stt_error", error=str(e))
        return ""
    finally:
        Path(tmp.name).unlink(missing_ok=True)
