"""Text-to-Speech module using Piper subprocess."""

import subprocess
import tempfile
from pathlib import Path

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()


def synthesize(text: str) -> str | None:
    """Synthesize text to WAV file using Piper TTS. Returns WAV path or None."""
    if not text or not text.strip():
        return None

    cfg = get_config()["piper"]
    binary = cfg["binary"]
    model = cfg["model"]
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create output file
    out_file = tempfile.NamedTemporaryFile(
        suffix=".wav", dir=str(output_dir), delete=False
    )
    out_path = out_file.name
    out_file.close()

    cmd = [
        binary,
        "--model", model,
        "--output_file", out_path,
    ]

    try:
        result = subprocess.run(
            cmd, input=text, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            logger.error("piper_failed", stderr=result.stderr[:200])
            Path(out_path).unlink(missing_ok=True)
            return None

        logger.info("tts_done", path=out_path)
        return out_path

    except subprocess.TimeoutExpired:
        logger.error("piper_timeout")
        Path(out_path).unlink(missing_ok=True)
        return None
    except FileNotFoundError:
        logger.error("piper_binary_not_found", binary=binary)
        Path(out_path).unlink(missing_ok=True)
        return None
    except Exception as e:
        logger.error("tts_error", error=str(e))
        Path(out_path).unlink(missing_ok=True)
        return None
