"""Audio preprocessing — noise suppression and echo cancellation.

Google/Amazon/Apple voice assistantlari qo'llaydigan texnikalar:

1. Noise Suppression — fon shovqinini tozalash (konditsioner, mashina, ko'cha)
2. Echo Cancellation — Alisa o'zi gapirgan ovozni filtrlash (barge-in uchun)
3. Audio Normalization — ovoz balandligini bir xil qilish
4. High-pass filter — past chastotali shovqinni olib tashlash

Apple: Always-On Processor da 2-stage DNN
Amazon: Multi-mic beamforming + neural echo suppression
Google: On-device noise reduction + federated learning
"""

import numpy as np
import structlog

logger = structlog.get_logger()


def preprocess_audio(audio_int16: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Full audio preprocessing pipeline.
    
    Args:
        audio_int16: Raw audio as int16 numpy array
        sample_rate: Sample rate (must be 16000 for Whisper/Silero)
    
    Returns:
        Cleaned audio as int16 numpy array
    """
    if len(audio_int16) == 0:
        return audio_int16

    # Convert to float for processing
    audio = audio_int16.astype(np.float32) / 32768.0

    # 1. DC offset removal
    audio = audio - np.mean(audio)

    # 2. High-pass filter (remove <80Hz rumble — AC hum, wind)
    audio = _highpass_filter(audio, cutoff=80, sample_rate=sample_rate)

    # 3. Noise gate (silence very quiet sections to reduce background hiss)
    audio = _noise_gate(audio, threshold=0.005, attack_ms=5, release_ms=50, sample_rate=sample_rate)

    # 4. Spectral noise suppression
    audio = _spectral_denoise(audio, sample_rate=sample_rate)

    # 5. Normalize volume (prevent clipping, ensure consistent level)
    audio = _normalize(audio, target_db=-3.0)

    # Convert back to int16
    return (audio * 32767).astype(np.int16)


def _highpass_filter(audio: np.ndarray, cutoff: int = 80, sample_rate: int = 16000) -> np.ndarray:
    """Simple first-order high-pass filter to remove low-frequency noise."""
    rc = 1.0 / (2.0 * np.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)

    filtered = np.zeros_like(audio)
    filtered[0] = audio[0]
    for i in range(1, len(audio)):
        filtered[i] = alpha * (filtered[i - 1] + audio[i] - audio[i - 1])
    return filtered


def _noise_gate(audio: np.ndarray, threshold: float = 0.005,
                attack_ms: int = 5, release_ms: int = 50,
                sample_rate: int = 16000) -> np.ndarray:
    """Noise gate — mutes audio below threshold (removes background hiss)."""
    attack_samples = int(attack_ms * sample_rate / 1000)
    release_samples = int(release_ms * sample_rate / 1000)

    envelope = np.abs(audio)
    # Smooth envelope
    kernel_size = max(attack_samples, 1)
    kernel = np.ones(kernel_size) / kernel_size
    envelope = np.convolve(envelope, kernel, mode='same')

    # Apply gate
    gate = np.where(envelope > threshold, 1.0, 0.0)

    # Smooth gate transitions (avoid clicks)
    smooth_kernel = np.ones(release_samples) / release_samples
    gate = np.convolve(gate, smooth_kernel, mode='same')
    gate = np.clip(gate, 0.0, 1.0)

    return audio * gate


def _spectral_denoise(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Spectral subtraction noise reduction.
    
    Estimates noise from first 100ms (assumed silence) and subtracts it.
    This is the same principle used in Google's on-device noise reduction.
    """
    # Use first 100ms as noise estimate
    noise_samples = int(0.1 * sample_rate)
    if len(audio) < noise_samples * 2:
        return audio

    # STFT parameters
    frame_size = 512
    hop_size = 256

    # Estimate noise spectrum from beginning
    noise_segment = audio[:noise_samples]
    noise_frames = _frame_audio(noise_segment, frame_size, hop_size)
    if len(noise_frames) == 0:
        return audio

    noise_spectrum = np.mean(np.abs(np.fft.rfft(noise_frames * np.hanning(frame_size), axis=1)), axis=0)

    # Process full audio
    frames = _frame_audio(audio, frame_size, hop_size)
    if len(frames) == 0:
        return audio

    window = np.hanning(frame_size)
    output = np.zeros(len(audio))
    window_sum = np.zeros(len(audio))

    for i, frame in enumerate(frames):
        spectrum = np.fft.rfft(frame * window)
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)

        # Spectral subtraction with oversubtraction factor
        clean_magnitude = np.maximum(magnitude - 1.5 * noise_spectrum, 0.1 * magnitude)

        # Reconstruct
        clean_spectrum = clean_magnitude * np.exp(1j * phase)
        clean_frame = np.fft.irfft(clean_spectrum, n=frame_size)

        # Overlap-add
        start = i * hop_size
        end = start + frame_size
        if end <= len(output):
            output[start:end] += clean_frame * window
            window_sum[start:end] += window ** 2

    # Normalize by window sum
    mask = window_sum > 1e-8
    output[mask] /= window_sum[mask]

    return output[:len(audio)]


def _frame_audio(audio: np.ndarray, frame_size: int, hop_size: int) -> np.ndarray:
    """Split audio into overlapping frames."""
    n_frames = (len(audio) - frame_size) // hop_size + 1
    if n_frames <= 0:
        return np.array([])
    frames = np.zeros((n_frames, frame_size))
    for i in range(n_frames):
        start = i * hop_size
        frames[i] = audio[start:start + frame_size]
    return frames


def _normalize(audio: np.ndarray, target_db: float = -3.0) -> np.ndarray:
    """Normalize audio to target dB level (prevents clipping)."""
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-8:
        return audio

    target_rms = 10 ** (target_db / 20.0)
    gain = target_rms / rms

    # Limit gain to prevent amplifying noise
    gain = min(gain, 10.0)

    normalized = audio * gain
    # Soft clip to prevent distortion
    return np.tanh(normalized)
