"""Multi-engine TTS manager. Online (edge-tts) + Offline (piper) fallback."""
import asyncio
import tempfile
import subprocess
from pathlib import Path
from .utils import load_config


async def synthesize(text: str) -> bytes:
    """Synthesize text to raw PCM audio (16kHz mono int16). Falls back automatically."""
    config = load_config()
    tts_cfg = config["tts"]
    engine = tts_cfg.get("engine", "edge-tts")

    try:
        if engine == "edge-tts":
            return await _edge_tts(text, tts_cfg.get("edge_voice", "uz-UZ-MadinaNeural"))
    except Exception:
        pass

    # Fallback to piper
    try:
        return await _piper_tts(text, tts_cfg.get("piper_binary", "piper"), tts_cfg.get("piper_voice", ""))
    except Exception:
        pass

    # Last resort: silence
    return b"\x00" * 32000


async def _edge_tts(text: str, voice: str) -> bytes:
    """Microsoft Edge TTS (online, natural voice)."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = f.name
    proc = await asyncio.create_subprocess_exec(
        "edge-tts", "--voice", voice, "--text", text, "--write-media", tmp,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await asyncio.wait_for(proc.wait(), timeout=10)
    if proc.returncode != 0:
        raise RuntimeError("edge-tts failed")
    # Convert mp3 to raw PCM 16kHz mono
    pcm = await _to_pcm(tmp)
    Path(tmp).unlink(missing_ok=True)
    return pcm


async def _piper_tts(text: str, binary: str, voice_model: str) -> bytes:
    """Piper TTS (offline, fast)."""
    cmd = [binary, "--model", voice_model, "--output_raw"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(input=text.encode()), timeout=10)
    return stdout


async def _to_pcm(audio_file: str) -> bytes:
    """Convert any audio file to raw PCM 16kHz mono int16 using ffmpeg."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", audio_file, "-f", "s16le", "-ar", "16000", "-ac", "1", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await proc.communicate()
    return stdout


async def to_48k_stereo(pcm_16k_mono: bytes) -> bytes:
    """Upsample 16kHz mono to 48kHz stereo for speaker output."""
    proc = await asyncio.create_subprocess_exec(
        "sox", "-t", "raw", "-r", "16000", "-c", "1", "-b", "16", "-e", "signed-integer", "-",
        "-r", "48000", "-c", "2", "-t", "raw", "-",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await proc.communicate(input=pcm_16k_mono)
    return stdout
