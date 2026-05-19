import io
import wave


DEFAULT_AUDIO_DURATION_SECONDS = 120.0
DEFAULT_SAMPLE_RATE = 8_000
DEFAULT_SAMPLE_WIDTH = 2
DEFAULT_CHANNELS = 1


def make_wav_audio(
    duration_seconds: float = DEFAULT_AUDIO_DURATION_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> bytes:
    frame_count = max(1, int(duration_seconds * sample_rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(DEFAULT_CHANNELS)
        audio.setsampwidth(DEFAULT_SAMPLE_WIDTH)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00" * frame_count * DEFAULT_SAMPLE_WIDTH * DEFAULT_CHANNELS)
    return buffer.getvalue()


def expected_wav_bitrate(sample_rate: int = DEFAULT_SAMPLE_RATE) -> int:
    return round(sample_rate * DEFAULT_CHANNELS * DEFAULT_SAMPLE_WIDTH * 8 / 1000)


def wav_upload_data(
    duration_seconds: float = DEFAULT_AUDIO_DURATION_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> dict[str, str]:
    return {
        "format": "wav",
        "duration_seconds": str(duration_seconds),
        "bitrate": str(expected_wav_bitrate(sample_rate)),
    }
