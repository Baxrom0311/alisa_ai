"""Profil boshqaruvi — Vali (erkak) / Zilola (ayol).

Profil tanlanganda:
- Ovoz o'zgaradi (voice, pitch, rate)
- Ism o'zgaradi (system prompt da)
- TTS sozlamalari o'zgaradi
"""

from alisa.core.config import get_config

def get_active_profile() -> dict:
    cfg = get_config()
    profile_name = cfg.get('active_profile', 'erkak')
    profiles = cfg.get('profiles', {})
    return profiles.get(profile_name, profiles.get('erkak', {'name': 'Alisa'}))

def get_assistant_name() -> str:
    return get_active_profile().get('name', 'Alisa')

def get_system_prompt(lang: str = 'uz') -> str:
    name = get_assistant_name()
    prompts = {
        'uz': f'Sen {name} — aqlli yordamchi. Sen faqat o\'zbek tilida gaplashasan. Javoblaring qisqa, aniq va foydali bo\'lsin.',
        'ru': f'Ты {name} — умный помощник. Отвечай на русском. Кратко и полезно.',
        'en': f'You are {name} — a smart assistant. Respond in English. Keep it short and helpful.',
    }
    return prompts.get(lang, prompts['uz'])

def set_active_profile(profile_name: str):
    import yaml
    from pathlib import Path
    config_path = Path('/home/baxrom/alisa_ai/config.yaml')
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg['active_profile'] = profile_name
    # TTS sozlamalarini ham yangilash
    profiles = cfg.get('profiles', {})
    if profile_name in profiles:
        p = profiles[profile_name]
        cfg['tts']['voice'] = p.get('voice', cfg['tts'].get('voice'))
        cfg['tts']['pitch'] = p.get('pitch', cfg['tts'].get('pitch'))
        cfg['tts']['rate'] = p.get('rate', cfg['tts'].get('rate'))
        cfg['tts']['espeak_voice'] = p.get('espeak_voice', cfg['tts'].get('espeak_voice'))
        cfg['tts']['espeak_pitch'] = p.get('espeak_pitch', cfg['tts'].get('espeak_pitch'))
        cfg['tts']['espeak_speed'] = p.get('espeak_speed', cfg['tts'].get('espeak_speed'))
    with open(config_path, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
