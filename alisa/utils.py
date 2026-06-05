"""Alisa utilities."""
import json
import numpy as np
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def apply_fade(audio_bytes: bytes, duration_ms: int, sample_rate=48000, channels=2, apply_in=True, apply_out=True) -> bytes:
    """Apply fade-in/out to raw PCM audio."""
    samples = np.frombuffer(audio_bytes, dtype=np.int16).copy()
    fade_samples = int(sample_rate * channels * duration_ms / 1000)
    fade_samples = min(fade_samples, len(samples) // 2)
    if apply_in and fade_samples > 0:
        fade_in = np.linspace(0, 1, fade_samples)
        samples[:fade_samples] = (samples[:fade_samples] * fade_in).astype(np.int16)
    if apply_out and fade_samples > 0:
        fade_out = np.linspace(1, 0, fade_samples)
        samples[-fade_samples:] = (samples[-fade_samples:] * fade_out).astype(np.int16)
    return samples.tobytes()


def is_low_effort(text: str) -> bool:
    """Filter out noise/low-effort utterances."""
    noise = {"huh", "uh", "um", "erm", "hmm", "ah", "oh", "eh", "ha", ""}
    return text.lower().strip(".,!? ") in noise
