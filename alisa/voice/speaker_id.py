"""Speaker verification (Voice ID) — ovoz bo'yicha foydalanuvchini tanish.

Amazon Alexa Voice Profiles / Apple Siri "Hey Siri" personalization kabi:
- Oila a'zolarini ovoz bo'yicha ajratish
- Shaxsiy javoblar berish (ismini aytish)
- Xavfsizlik — faqat ro'yxatdagi odamlar boshqara oladi

Texnologiya: Speaker embedding (d-vector) + cosine similarity
Model: speechbrain/spkrec-ecapa-voxceleb (yoki oddiy MFCC-based)
"""

import json
import struct
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import numpy as np
import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()

SPEAKERS_FILE = Path("/opt/alisa/data/speakers.json")


class SpeakerVerifier:
    """On-device speaker verification using voice embeddings."""

    def __init__(self):
        self.speakers: Dict[str, np.ndarray] = {}
        self._load_speakers()

    def _load_speakers(self):
        """Load registered speaker embeddings from disk."""
        path = SPEAKERS_FILE
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for name, emb_list in data.items():
                self.speakers[name] = np.array(emb_list, dtype=np.float32)
            logger.info("speakers_loaded", count=len(self.speakers))
        except Exception as e:
            logger.error("speakers_load_failed", error=str(e))

    def _save_speakers(self):
        """Save speaker embeddings to disk."""
        SPEAKERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {name: emb.tolist() for name, emb in self.speakers.items()}
        SPEAKERS_FILE.write_text(json.dumps(data))

    def extract_embedding(self, audio_int16: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """Extract speaker embedding from audio using MFCC-based approach.
        
        Lightweight method that works on Pi without heavy dependencies.
        For better accuracy, use speechbrain ECAPA-TDNN.
        """
        audio = audio_int16.astype(np.float32) / 32768.0

        # Extract MFCCs (13 coefficients)
        mfccs = self._compute_mfcc(audio, sample_rate, n_mfcc=13)
        if mfccs is None or len(mfccs) == 0:
            return np.zeros(13)

        # Average across time → fixed-size embedding
        embedding = np.mean(mfccs, axis=0)
        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding

    def register_speaker(self, name: str, audio_int16: np.ndarray, sample_rate: int = 16000):
        """Register a new speaker (enrollment)."""
        embedding = self.extract_embedding(audio_int16, sample_rate)
        self.speakers[name] = embedding
        self._save_speakers()
        logger.info("speaker_registered", name=name)

    def identify(self, audio_int16: np.ndarray, sample_rate: int = 16000, threshold: float = 0.75) -> Optional[str]:
        """Identify who is speaking. Returns speaker name or None."""
        if not self.speakers:
            return None

        embedding = self.extract_embedding(audio_int16, sample_rate)

        best_name = None
        best_score = -1.0

        for name, ref_embedding in self.speakers.items():
            score = float(np.dot(embedding, ref_embedding))
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= threshold:
            logger.info("speaker_identified", name=best_name, score=f"{best_score:.3f}")
            return best_name

        logger.debug("speaker_unknown", best_score=f"{best_score:.3f}", threshold=threshold)
        return None

    def _compute_mfcc(self, audio: np.ndarray, sample_rate: int, n_mfcc: int = 13) -> Optional[np.ndarray]:
        """Compute MFCC features (lightweight, no external deps)."""
        frame_size = int(0.025 * sample_rate)  # 25ms
        hop_size = int(0.010 * sample_rate)    # 10ms
        n_fft = 512
        n_mels = 26

        # Frame the signal
        n_frames = (len(audio) - frame_size) // hop_size + 1
        if n_frames <= 0:
            return None

        frames = np.zeros((n_frames, frame_size))
        for i in range(n_frames):
            frames[i] = audio[i * hop_size:i * hop_size + frame_size]

        # Apply Hamming window
        frames *= np.hamming(frame_size)

        # FFT
        mag_spec = np.abs(np.fft.rfft(frames, n=n_fft))

        # Mel filterbank
        mel_filters = self._mel_filterbank(n_mels, n_fft, sample_rate)
        mel_spec = np.dot(mag_spec, mel_filters.T)
        mel_spec = np.maximum(mel_spec, 1e-10)

        # Log + DCT → MFCC
        log_mel = np.log(mel_spec)
        mfccs = self._dct(log_mel, n_mfcc)

        return mfccs

    def _mel_filterbank(self, n_mels: int, n_fft: int, sample_rate: int) -> np.ndarray:
        """Create mel filterbank matrix."""
        low_freq = 0
        high_freq = sample_rate / 2
        mel_low = 2595 * np.log10(1 + low_freq / 700)
        mel_high = 2595 * np.log10(1 + high_freq / 700)
        mel_points = np.linspace(mel_low, mel_high, n_mels + 2)
        hz_points = 700 * (10 ** (mel_points / 2595) - 1)
        bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

        filters = np.zeros((n_mels, n_fft // 2 + 1))
        for i in range(n_mels):
            for j in range(bins[i], bins[i + 1]):
                filters[i, j] = (j - bins[i]) / max(bins[i + 1] - bins[i], 1)
            for j in range(bins[i + 1], bins[i + 2]):
                filters[i, j] = (bins[i + 2] - j) / max(bins[i + 2] - bins[i + 1], 1)
        return filters

    def _dct(self, x: np.ndarray, n_out: int) -> np.ndarray:
        """Type-II DCT (for MFCC computation)."""
        n_in = x.shape[1]
        basis = np.zeros((n_out, n_in))
        for k in range(n_out):
            for n in range(n_in):
                basis[k, n] = np.cos(np.pi * k * (2 * n + 1) / (2 * n_in))
        return np.dot(x, basis.T)


# Global instance
_verifier: Optional[SpeakerVerifier] = None


def get_speaker_verifier() -> SpeakerVerifier:
    global _verifier
    if _verifier is None:
        _verifier = SpeakerVerifier()
    return _verifier
