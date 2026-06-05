"""Alisa Audio Client — Mic capture + Speaker playback + WebSocket."""
import asyncio
import threading
import queue
import json
import numpy as np

import pyaudio
import websockets

from .utils import load_config, apply_fade

CHUNK = 1024
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16

audio_q: queue.Queue = queue.Queue()
playback_q: queue.Queue = queue.Queue()


def mic_callback(in_data, frame_count, time_info, status):
    """PyAudio callback — puts mic data into queue."""
    audio_q.put(in_data)
    return (None, pyaudio.paContinue)


async def send_audio(ws):
    """Send mic audio to server via WebSocket."""
    while True:
        data = await asyncio.to_thread(audio_q.get)
        await ws.send(data)


async def receive_audio(ws, config):
    """Receive TTS audio from server and queue for playback."""
    fade_ms = config.get("fade_duration_ms", 100)
    buffer = bytearray()
    is_first = True

    async for message in ws:
        if isinstance(message, bytes):
            buffer.extend(message)
            if len(buffer) >= 48000:
                chunk = bytes(buffer)
                if is_first and fade_ms > 0:
                    chunk = apply_fade(chunk, fade_ms, apply_in=True, apply_out=False)
                    is_first = False
                playback_q.put(chunk)
                buffer = bytearray()
        elif isinstance(message, str) and message == "__END__":
            if buffer:
                chunk = bytes(buffer)
                if fade_ms > 0:
                    chunk = apply_fade(chunk, fade_ms, apply_in=False, apply_out=True)
                playback_q.put(chunk)
                buffer = bytearray()
            playback_q.put("__END__")
            is_first = True
            await ws.send("__done__")


def playback_worker(output_device_index):
    """Background thread: plays audio from queue."""
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=2, rate=48000, output=True,
                     output_device_index=output_device_index, frames_per_buffer=1024)
    stream.start_stream()
    while True:
        data = playback_q.get()
        if data is None:
            break
        if data == "__END__":
            continue
        try:
            stream.write(data)
        except Exception:
            pass
    stream.stop_stream()
    stream.close()
    pa.terminate()


def find_device(name: str, is_input: bool) -> int | None:
    """Find audio device by partial name match."""
    pa = pyaudio.PyAudio()
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if name and name.lower() in info["name"].lower():
            if is_input and info["maxInputChannels"] > 0:
                pa.terminate()
                return i
            if not is_input and info["maxOutputChannels"] > 0:
                pa.terminate()
                return i
    pa.terminate()
    return None


async def main():
    config = load_config()
    host = config.get("server_host", "localhost")
    port = config.get("server_port", 8765)

    # Find devices
    mic_idx = find_device(config.get("mic_name", ""), is_input=True)
    spk_idx = find_device(config.get("audio_output_device", ""), is_input=False)

    # Start mic
    pa = pyaudio.PyAudio()
    mic_stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                         input_device_index=mic_idx, frames_per_buffer=CHUNK,
                         stream_callback=mic_callback)
    mic_stream.start_stream()

    # Start playback thread
    playback_thread = threading.Thread(target=playback_worker, args=(spk_idx,), daemon=True)
    playback_thread.start()

    # Connect to server
    uri = f"ws://{host}:{port}"
    print(f"[Alisa Client] Connecting to {uri}...")
    async with websockets.connect(uri, ping_timeout=120, ping_interval=30) as ws:
        print("[Alisa Client] Connected. Listening...")
        await ws.send(json.dumps({"type": "config_sync", "config": config}))
        await asyncio.gather(send_audio(ws), receive_audio(ws, config))

    mic_stream.stop_stream()
    mic_stream.close()
    pa.terminate()
    playback_q.put(None)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Alisa Client] Stopped.")
