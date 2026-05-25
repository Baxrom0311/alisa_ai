"""Emotion detection — ovoz ohangidan kayfiyatni aniqlash.

Ovoz xususiyatlari asosida:
- Pitch (baland/past) → xursandlik/g'amginlik
- Energy (kuchli/kuchsiz) → g'azab/charchoq
- Speech rate (tez/sekin) → hayajon/xotirjamlik
- Pitch variance (o'zgaruvchan/monoton) → hayajon/zerikarlilik

Natija: happy, sad, angry, neutral, tired
Alisa kayfiyatga qarab javob beradi.
"""

import numpy as np
import structlog

logger = structlog.get_logger()

EMOTIONS = {
    "happy": "😊",
    "sad": "😢",
    "angry": "😠",
    "neutral": "😐",
    "tired": "😴",
    "excited": "🤩",
}


class EmotionDetector:
    """Detect emotion from voice audio features."""

    def detect(self, audio_int16: np.ndarray, sample_rate: int = 16000) -> str:
        """Detect emotion from audio. Returns emotion label."""
        if len(audio_int16) < sample_rate * 0.5:  # Min 0.5s
            return "neutral"

        audio = audio_int16.astype(np.float32) / 32768.0

        # Extract features
        energy = self._rms_energy(audio)
        pitch_mean, pitch_var = self._estimate_pitch(audio, sample_rate)
        speech_rate = self._speech_rate(audio, sample_rate)

        # Simple rule-based classification
        if energy > 0.08 and pitch_var > 50:
            return "angry"
        if energy > 0.05 and pitch_mean > 200 and pitch_var > 30:
            return "excited"
        if pitch_mean > 180 and speech_rate > 4:
            return "happy"
        if energy < 0.015 and speech_rate < 2:
            return "tired"
        if pitch_mean < 130 and pitch_var < 20:
            return "sad"

        return "neutral"

    def get_response_modifier(self, emotion: str) -> str:
        """Get a prefix/modifier for LLM based on detected emotion."""
        modifiers = {
            "happy": "Foydalanuvchi xursand ko'rinadi. Ijobiy javob ber.",
            "sad": "Foydalanuvchi g'amgin ko'rinadi. Yumshoq va qo'llab-quvvatlovchi javob ber.",
            "angry": "Foydalanuvchi asabiy ko'rinadi. Tinch va hurmatli javob ber.",
            "tired": "Foydalanuvchi charchagan ko'rinadi. Qisqa va aniq javob ber.",
            "excited": "Foydalanuvchi hayajonlangan. Energetik javob ber.",
        }
        return modifiers.get(emotion, "")

    def _rms_energy(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(audio ** 2)))

    def _estimate_pitch(self, audio: np.ndarray, sr: int) -> tuple:
        """Estimate pitch using autocorrelation."""
        # Simple autocorrelation-based pitch
        frame_size = int(0.03 * sr)  # 30ms frames
        hop = int(0.01 * sr)
        pitches = []

        for i in range(0, len(audio) - frame_size, hop):
            frame = audio[i:i + frame_size]
            # Autocorrelation
            corr = np.correlate(frame, frame, mode='full')
            corr = corr[len(corr) // 2:]

            # Find first peak after minimum
            min_lag = int(sr / 500)  # 500Hz max
            max_lag = int(sr / 75)   # 75Hz min

            if max_lag > len(corr):
                continue

            segment = corr[min_lag:max_lag]
            if len(segment) == 0:
                continue

            peak_idx = np.argmax(segment) + min_lag
            if corr[peak_idx] > 0.3 * corr[0]:
                pitch = sr / peak_idx
                pitches.append(pitch)

        if not pitches:
            return 150.0, 20.0

        return float(np.mean(pitches)), float(np.std(pitches))

    def _speech_rate(self, audio: np.ndarray, sr: int) -> float:
        """Estimate speech rate (syllables per second)."""
        # Count energy peaks as proxy for syllables
        frame_ms = 25
        frame_size = int(sr * frame_ms / 1000)
        energies = []

        for i in range(0, len(audio) - frame_size, frame_size):
            frame = audio[i:i + frame_size]
            energies.append(np.sqrt(np.mean(frame ** 2)))

        if not energies:
            return 3.0

        energies = np.array(energies)
        threshold = np.mean(energies) * 0.5

        # Count transitions above threshold (syllable onsets)
        above = energies > threshold
        onsets = np.sum(np.diff(above.astype(int)) == 1)

        duration_sec = len(audio) / sr
        return onsets / max(duration_sec, 0.1)


_detector: EmotionDetector = None


def get_emotion_detector() -> EmotionDetector:
    global _detector
    if _detector is None:
        _detector = EmotionDetector()
    return _detector
