"""Alisa Voice Server — WebSocket streaming pipeline: STT → LLM → TTS."""
import asyncio
import json
import re
import subprocess
import tempfile
from pathlib import Path

import websockets

from .llm_manager import generate_sentences
from .tts_manager import synthesize, to_48k_stereo
from .utils import load_config, is_low_effort

RATE = 16000


def clean_response(text: str) -> str:
    """Remove markdown, emojis, and formatting from LLM response."""
    text = re.sub(r"[\*]+", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"<.*?>", "", text)
    text = text.replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]+", "", text)
    return text


async def transcribe_audio(audio_data: bytes, config: dict) -> str:
    """Transcribe audio using whisper.cpp CLI."""
    stt_cfg = config["stt"]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
        # Write WAV header + PCM data
        import struct
        data_size = len(audio_data)
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(audio_data)

    model_path = stt_cfg.get("model_path", "models/ggml-base.bin")
    lang = stt_cfg.get("language", "uz")
    cmd = ["whisper-cli", "-m", model_path, "-l", lang, "-f", tmp, "--no-timestamps", "-t", "4"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = stdout.decode().strip()
        # whisper outputs [BLANK_AUDIO] or similar for silence
        if "[" in text and "]" in text:
            text = re.sub(r"\[.*?\]", "", text).strip()
        return text
    except (asyncio.TimeoutError, Exception):
        return ""
    finally:
        Path(tmp).unlink(missing_ok=True)


async def process_connection(websocket):
    """Handle one client connection."""
    config = load_config()
    audio_buffer = bytearray()
    silence_frames = 0
    speaking = False
    history = [{"role": "system", "content": config["system_prompt"]}]

    print("[Server] Client connected")

    async for message in websocket:
        if isinstance(message, str):
            if message == "__done__":
                continue
            # Config update from client
            try:
                data = json.loads(message)
                if data.get("type") == "config_sync":
                    config.update(data.get("config", {}))
            except (json.JSONDecodeError, Exception):
                pass
            continue

        if not isinstance(message, bytes):
            continue

        # Accumulate audio
        audio_buffer.extend(message)

        # Simple VAD: detect silence (energy-based)
        import numpy as np
        chunk = np.frombuffer(message, dtype=np.int16)
        energy = np.abs(chunk).mean()

        if energy > 300:
            speaking = True
            silence_frames = 0
        elif speaking:
            silence_frames += 1

        # ~1 second of silence after speech = utterance complete
        frames_per_sec = RATE // len(chunk) if len(chunk) > 0 else 16
        if speaking and silence_frames > frames_per_sec:
            speaking = False
            silence_frames = 0

            if len(audio_buffer) < RATE:  # Less than 1 sec = skip
                audio_buffer = bytearray()
                continue

            # Transcribe
            text = await transcribe_audio(bytes(audio_buffer), config)
            audio_buffer = bytearray()

            if not text or is_low_effort(text):
                continue

            print(f"\033[32m[User]: {text}\033[0m")

            # LLM + TTS streaming
            history.append({"role": "user", "content": text})
            context = history[-(config.get("history_length", 6) * 2 + 1):]

            full_response = ""
            async for sentence in generate_sentences(context):
                sentence = clean_response(sentence)
                if not sentence:
                    continue
                print(f"\033[36m[Alisa]: {sentence}\033[0m")
                full_response += sentence + " "

                # TTS → send audio to client
                pcm = await synthesize(sentence)
                audio_48k = await to_48k_stereo(pcm)
                # Send in chunks
                for i in range(0, len(audio_48k), 2048):
                    await websocket.send(audio_48k[i:i + 2048])

            await websocket.send("__END__")
            history.append({"role": "assistant", "content": full_response.strip()})

    print("[Server] Client disconnected")


async def main():
    config = load_config()
    host = config.get("server_host", "0.0.0.0")
    port = config.get("server_port", 8765)
    print(f"[Alisa Server] ws://{host}:{port}")
    async with websockets.serve(process_connection, host, port, ping_timeout=None, ping_interval=None):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
