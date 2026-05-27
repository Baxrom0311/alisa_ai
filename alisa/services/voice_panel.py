"""TTS Voice Settings Web Panel — ovoz sozlash paneli.

Port 8085 da ishlaydi. Brauzerdan ochib:
- Ovoz tanlash (Sardor, Madina, espeak erkak, espeak ayol)
- Pitch, speed sozlash
- Sinab ko'rish (Play tugmasi)
- Saqlash (config.yaml ga yozadi)
"""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from aiohttp import web
import yaml

CONFIG_PATH = Path('/home/baxrom/alisa_ai/config.yaml')
AUDIO_DIR = Path('/tmp/alisa_tts')
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

HTML_PAGE = '''<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alisa - Ovoz Sozlamalari</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; padding: 20px; }
.container { max-width: 700px; margin: 0 auto; }
h1 { text-align: center; margin-bottom: 30px; color: #00d4ff; font-size: 24px; }
h2 { color: #00d4ff; margin: 20px 0 10px; font-size: 18px; }
.card { background: #16213e; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #0f3460; }
label { display: block; margin: 10px 0 5px; color: #aaa; font-size: 14px; }
select, input[type=range], input[type=text] { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #0f3460; background: #0f3460; color: #fff; font-size: 16px; }
input[type=range] { padding: 5px 0; cursor: pointer; }
.range-row { display: flex; align-items: center; gap: 10px; }
.range-row input { flex: 1; }
.range-row span { min-width: 60px; text-align: right; color: #00d4ff; font-weight: bold; }
.btn { padding: 12px 24px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; margin: 5px; }
.btn-play { background: #00d4ff; color: #000; }
.btn-save { background: #00c853; color: #000; }
.btn-play:hover { background: #00b8e6; }
.btn-save:hover { background: #00a844; }
.buttons { text-align: center; margin-top: 20px; }
.status { text-align: center; margin-top: 10px; color: #00c853; font-size: 14px; min-height: 20px; }
.test-text { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #0f3460; background: #0f3460; color: #fff; font-size: 14px; resize: vertical; min-height: 60px; }
.profiles { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; }
.profile-btn { padding: 8px 16px; border-radius: 20px; border: 2px solid #0f3460; background: transparent; color: #aaa; cursor: pointer; font-size: 13px; }
.profile-btn.active { border-color: #00d4ff; color: #00d4ff; }
.profile-btn:hover { border-color: #00d4ff; }
</style>
</head>
<body>
<div class="container">
<h1>🎤 Alisa — Ovoz Sozlamalari</h1>

<div class="card">
<h2>👤 Profil</h2>
<div class="profiles">
<button class="profile-btn active" onclick="loadProfile('erkak')">👦 Vali (Online)</button>
<button class="profile-btn" onclick="loadProfile('ayol')">👧 Zilola (Online)</button>
<button class="profile-btn" onclick="loadProfile('espeak_erkak')">🤖 Vali (Offline)</button>
<button class="profile-btn" onclick="loadProfile('espeak_ayol')">🤖 Zilola (Offline)</button>
</div>
</div>

<div class="card">
<h2>🔊 Online ovoz (Edge TTS)</h2>
<label>Ovoz</label>
<select id="voice">
<option value="uz-UZ-SardorNeural">Sardor (erkak)</option>
<option value="uz-UZ-MadinaNeural">Madina (ayol)</option>
<option value="ru-RU-DmitryNeural">Dmitriy (rus erkak)</option>
<option value="en-US-GuyNeural">Guy (ingliz erkak)</option>
</select>

<label>Pitch (ovoz balandligi)</label>
<div class="range-row">
<input type="range" id="pitch" min="-50" max="50" value="-20">
<span id="pitch_val">-20Hz</span>
</div>

<label>Tezlik</label>
<div class="range-row">
<input type="range" id="rate" min="-50" max="50" value="5">
<span id="rate_val">+5%</span>
</div>
</div>

<div class="card">
<h2>🤖 Offline ovoz (espeak-ng)</h2>
<label>Ovoz</label>
<select id="espeak_voice">
<option value="uz">O\'zbek erkak</option>
<option value="uz+f3">O\'zbek ayol</option>
<option value="tr">Turk erkak</option>
<option value="ru">Rus erkak</option>
</select>

<label>Pitch (0-99)</label>
<div class="range-row">
<input type="range" id="espeak_pitch" min="0" max="99" value="25">
<span id="espeak_pitch_val">25</span>
</div>

<label>Tezlik (80-200)</label>
<div class="range-row">
<input type="range" id="espeak_speed" min="80" max="200" value="125">
<span id="espeak_speed_val">125</span>
</div>
</div>

<div class="card">
<h2>📝 Sinab ko\'rish</h2>
<textarea class="test-text" id="test_text">Assalomu alaykum! Men Alisa, sizning ovozli yordamchingizman.</textarea>
</div>

<div class="buttons">
<button class="btn btn-play" onclick="testOnline()">▶️ Online ovoz</button>
<button class="btn btn-play" onclick="testOffline()">▶️ Offline ovoz</button>
<button class="btn btn-save" onclick="saveConfig()">💾 Saqlash</button>
</div>
<div class="status" id="status"></div>
</div>

<script>
const profiles = {
  erkak: {voice:'uz-UZ-SardorNeural', pitch:-20, rate:5, espeak_voice:'uz', espeak_pitch:25, espeak_speed:125, name:'Vali'},
  ayol: {voice:'uz-UZ-MadinaNeural', pitch:15, rate:-5, espeak_voice:'uz+f3', espeak_pitch:70, espeak_speed:130, name:'Zilola'},
  espeak_erkak: {voice:'uz-UZ-SardorNeural', pitch:-20, rate:5, espeak_voice:'uz', espeak_pitch:20, espeak_speed:120, name:'Vali'},
  espeak_ayol: {voice:'uz-UZ-MadinaNeural', pitch:15, rate:-5, espeak_voice:'uz+f3', espeak_pitch:75, espeak_speed:130, name:'Zilola'},
};

function loadProfile(name) {
  const p = profiles[name];
  document.getElementById('voice').value = p.voice;
  document.getElementById('pitch').value = p.pitch;
  document.getElementById('rate').value = p.rate;
  document.getElementById('espeak_voice').value = p.espeak_voice;
  document.getElementById('espeak_pitch').value = p.espeak_pitch;
  document.getElementById('espeak_speed').value = p.espeak_speed;
  updateLabels();
  document.querySelectorAll('.profile-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
}

function updateLabels() {
  document.getElementById('pitch_val').textContent = (document.getElementById('pitch').value > 0 ? '+' : '') + document.getElementById('pitch').value + 'Hz';
  document.getElementById('rate_val').textContent = (document.getElementById('rate').value > 0 ? '+' : '') + document.getElementById('rate').value + '%';
  document.getElementById('espeak_pitch_val').textContent = document.getElementById('espeak_pitch').value;
  document.getElementById('espeak_speed_val').textContent = document.getElementById('espeak_speed').value;
}

document.querySelectorAll('input[type=range]').forEach(el => el.addEventListener('input', updateLabels));
updateLabels();

async function testOnline() {
  setStatus('⏳ Generatsiya...');
  const res = await fetch('/api/test', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({engine:'edge', text:document.getElementById('test_text').value,
      voice:document.getElementById('voice').value,
      pitch:document.getElementById('pitch').value+'Hz',
      rate:document.getElementById('rate').value+'%'})});
  const data = await res.json();
  setStatus(data.ok ? '✅ Tayyor!' : '❌ ' + data.error);
}

async function testOffline() {
  setStatus('⏳ Generatsiya...');
  const res = await fetch('/api/test', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({engine:'espeak', text:document.getElementById('test_text').value,
      voice:document.getElementById('espeak_voice').value,
      pitch:document.getElementById('espeak_pitch').value,
      speed:document.getElementById('espeak_speed').value})});
  const data = await res.json();
  setStatus(data.ok ? '✅ Tayyor!' : '❌ ' + data.error);
}

async function saveConfig() {
  const cfg = {
    voice: document.getElementById('voice').value,
    pitch: (document.getElementById('pitch').value > 0 ? '+' : '') + document.getElementById('pitch').value + 'Hz',
    rate: (document.getElementById('rate').value > 0 ? '+' : '') + document.getElementById('rate').value + '%',
    espeak_voice: document.getElementById('espeak_voice').value,
    espeak_pitch: parseInt(document.getElementById('espeak_pitch').value),
    espeak_speed: parseInt(document.getElementById('espeak_speed').value),
  };
  const res = await fetch('/api/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cfg)});
  const data = await res.json();
  setStatus(data.ok ? '💾 Saqlandi!' : '❌ ' + data.error);
}

function setStatus(msg) { document.getElementById('status').textContent = msg; }
</script>
</body>
</html>'''


async def index(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')


async def test_voice(request):
    data = await request.json()
    text = data.get('text', 'Test')
    engine = data.get('engine', 'edge')

    try:
        if engine == 'edge':
            voice = data.get('voice', 'uz-UZ-SardorNeural')
            pitch = data.get('pitch', '-20Hz')
            rate = data.get('rate', '+5%')
            if not pitch.startswith(('+', '-')):
                pitch = '+' + pitch if int(pitch.replace('Hz','')) >= 0 else pitch
            if not rate.startswith(('+', '-')):
                rate = '+' + rate if int(rate.replace('%','')) >= 0 else rate

            mp3 = '/tmp/alisa_tts/panel_test.mp3'
            wav = '/tmp/alisa_tts/panel_test.wav'
            subprocess.run(['edge-tts', '--voice', voice, '--pitch=' + pitch, '--rate=' + rate,
                          '--text', text, '--write-media', mp3], capture_output=True, timeout=15)
            subprocess.run(['ffmpeg', '-y', '-i', mp3, '-ar', '16000', '-ac', '1', wav],
                         capture_output=True, timeout=10)
            subprocess.run(['aplay', '-D', 'plughw:2,0', wav], capture_output=True, timeout=30)
        else:
            voice = data.get('voice', 'uz')
            pitch = data.get('pitch', '25')
            speed = data.get('speed', '125')
            wav = '/tmp/alisa_tts/panel_espeak.wav'
            subprocess.run(['espeak-ng', '-v', voice, '-s', speed, '-p', pitch, text, '-w', wav],
                         capture_output=True, timeout=10)
            subprocess.run(['aplay', '-D', 'plughw:2,0', wav], capture_output=True, timeout=30)

        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})


async def save_config(request):
    data = await request.json()
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}

        cfg['tts'] = {
            'voice': data.get('voice', 'uz-UZ-SardorNeural'),
            'pitch': data.get('pitch', '-20Hz'),
            'rate': data.get('rate', '+5%'),
            'espeak_voice': data.get('espeak_voice', 'uz'),
            'espeak_pitch': data.get('espeak_pitch', 25),
            'espeak_speed': data.get('espeak_speed', 125),
        }
        # Profil nomi bo'yicha active_profile yangilash
        if data.get('voice') == 'uz-UZ-MadinaNeural':
            cfg['active_profile'] = 'ayol'
        else:
            cfg['active_profile'] = 'erkak'
        from alisa.core.config import reset_config
        reset_config()

        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})


def create_app():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_post('/api/test', test_voice)
    app.router.add_post('/api/save', save_config)
    return app


if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8085)
