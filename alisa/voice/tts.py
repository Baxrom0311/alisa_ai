"""Text-to-Speech — config.yaml dan sozlamalar olinadi (panel orqali saqlanadi).

Online: Edge TTS (tabiiy ovoz) — paneldan tanlangan voice/pitch/rate
Offline: espeak-ng — paneldan tanlangan voice/pitch/speed
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import structlog
from alisa.core.config import get_config

logger = structlog.get_logger()


def synthesize(text: str, lang: str = 'uz') -> Optional[str]:
    if not text or not text.strip():
        return None
    result = _synthesize_edge_tts(text, lang)
    if result:
        return result
    return _synthesize_espeak(text, lang)


def _synthesize_edge_tts(text: str, lang: str = 'uz') -> Optional[str]:
    try:
        cfg = get_config().get('tts', {})
        voice = cfg.get('voice', 'uz-UZ-SardorNeural')
        pitch = cfg.get('pitch', '-20Hz')
        rate = cfg.get('rate', '+5%')

        if lang == 'ru':
            voice = cfg.get('voice_ru', 'ru-RU-DmitryNeural')
        elif lang == 'en':
            voice = cfg.get('voice_en', 'en-US-GuyNeural')

        output_dir = Path('/tmp/alisa_tts')
        output_dir.mkdir(parents=True, exist_ok=True)
        mp3_file = tempfile.NamedTemporaryFile(suffix='.mp3', dir=str(output_dir), delete=False)
        wav_file = mp3_file.name.replace('.mp3', '.wav')
        mp3_file.close()

        cmd = ['edge-tts', '--voice', voice, '--pitch=' + pitch, '--rate=' + rate,
               '--text', text, '--write-media', mp3_file.name]
        result = subprocess.run(cmd, capture_output=True, timeout=15)

        if result.returncode != 0:
            Path(mp3_file.name).unlink(missing_ok=True)
            return None

        subprocess.run(['ffmpeg', '-y', '-i', mp3_file.name, '-ar', '16000', '-ac', '1', wav_file],
                      capture_output=True, timeout=10)
        Path(mp3_file.name).unlink(missing_ok=True)

        if Path(wav_file).exists() and Path(wav_file).stat().st_size > 100:
            logger.info('tts_done', engine='edge-tts', voice=voice)
            return wav_file
    except Exception as e:
        logger.warning('edge_tts_failed', error=str(e))
    return None


def _synthesize_espeak(text: str, lang: str = 'uz') -> Optional[str]:
    output_dir = Path('/tmp/alisa_tts')
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = tempfile.NamedTemporaryFile(suffix='.wav', dir=str(output_dir), delete=False)
    out_path = out_file.name
    out_file.close()

    cfg = get_config().get('tts', {})
    voice = cfg.get('espeak_voice', 'uz')
    pitch = str(cfg.get('espeak_pitch', 25))
    speed = str(cfg.get('espeak_speed', 125))

    if lang == 'ru':
        voice = 'ru'
    elif lang == 'en':
        voice = 'en'

    try:
        result = subprocess.run(
            ['espeak-ng', '-v', voice, '-s', speed, '-p', pitch, text, '-w', out_path],
            capture_output=True, timeout=10)
        if result.returncode == 0 and Path(out_path).stat().st_size > 100:
            logger.info('tts_done', engine='espeak-ng')
            return out_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    Path(out_path).unlink(missing_ok=True)
    return None
