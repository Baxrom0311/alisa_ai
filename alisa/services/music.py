"""Musiqa ijro etish moduli.

"Musiqa qo'y" → random playlist
"Musiqani to'xtat" → pause
"Keyingisi" → next track
Supports: MP3 files from local directory + Bluetooth speaker
"""

import asyncio
import os
import random
import subprocess
from pathlib import Path
from typing import Optional, List

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()

MUSIC_DIR = Path("/opt/alisa/music")


class MusicPlayer:
    """Simple music player using aplay/mpv subprocess."""

    def __init__(self):
        self.playlist: List[Path] = []
        self.current_index: int = 0
        self.is_playing: bool = False
        self._process: Optional[subprocess.Popen] = None
        self._load_playlist()

    def _load_playlist(self):
        """Load MP3/WAV files from music directory."""
        if MUSIC_DIR.exists():
            self.playlist = sorted(
                MUSIC_DIR.glob("**/*.[mM][pP]3")) + sorted(
                MUSIC_DIR.glob("**/*.[wW][aA][vV]"))
        logger.info("music_loaded", tracks=len(self.playlist))

    def parse_command(self, text: str) -> Optional[str]:
        """Parse music command. Returns response or None."""
        text_lower = text.lower()

        if any(w in text_lower for w in ["musiqa qo'y", "muzika", "play music", "включи музыку"]):
            return self.play()
        if any(w in text_lower for w in ["to'xtat", "pauza", "stop music", "останови"]):
            return self.stop()
        if any(w in text_lower for w in ["keyingisi", "next", "следующ"]):
            return self.next_track()
        if any(w in text_lower for w in ["oldingisi", "previous", "предыдущ"]):
            return self.prev_track()
        return None

    def play(self, index: int = None) -> str:
        """Start playing music."""
        if not self.playlist:
            return "Musiqa fayllari topilmadi. /opt/alisa/music papkasiga MP3 qo'ying."

        if index is not None:
            self.current_index = index
        elif not self.is_playing:
            self.current_index = random.randint(0, len(self.playlist) - 1)

        self.stop()
        track = self.playlist[self.current_index]

        try:
            # Try mpv first (better), fallback to aplay
            player = "mpv" if self._has_command("mpv") else "aplay"
            cmd = [player, "--no-video", str(track)] if player == "mpv" else [player, str(track)]
            self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.is_playing = True
            logger.info("music_playing", track=track.name)
            return f"🎵 {track.stem} ijro etilmoqda"
        except Exception as e:
            logger.error("music_play_error", error=str(e))
            return "Musiqa ijro etishda xatolik."

    def stop(self) -> str:
        """Stop playing."""
        if self._process:
            self._process.terminate()
            self._process = None
        self.is_playing = False
        return "Musiqa to'xtatildi."

    def next_track(self) -> str:
        """Play next track."""
        if self.playlist:
            self.current_index = (self.current_index + 1) % len(self.playlist)
            return self.play(self.current_index)
        return "Playlist bo'sh."

    def prev_track(self) -> str:
        """Play previous track."""
        if self.playlist:
            self.current_index = (self.current_index - 1) % len(self.playlist)
            return self.play(self.current_index)
        return "Playlist bo'sh."

    def _has_command(self, cmd: str) -> bool:
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


_player: Optional[MusicPlayer] = None


def get_music_player() -> MusicPlayer:
    global _player
    if _player is None:
        _player = MusicPlayer()
    return _player
