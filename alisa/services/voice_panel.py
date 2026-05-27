"""Alisa Full Settings Panel — barcha sozlamalar bir joyda.

Navbarlar: Ovoz | AI | Audio | Profil | Tizim
Barcha sozlamalar config.yaml dan dynamic yuklanadi.
"""

import subprocess
import tempfile
from pathlib import Path
from aiohttp import web
import yaml

CONFIG_PATH = Path('/home/baxrom/alisa_ai/config.yaml')

def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}

def save_full_config(cfg):
    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

HTML = '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alisa Panel</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;background:#0f0f1a;color:#e0e0e0;min-height:100vh}
.nav{display:flex;background:#1a1a2e;border-bottom:2px solid #00d4ff;overflow-x:auto}
.nav a{padding:14px 18px;color:#888;text-decoration:none;font-size:13px;white-space:nowrap;border-bottom:3px solid transparent;transition:.2s}
.nav a.active{color:#00d4ff;border-bottom-color:#00d4ff}
.nav a:hover{color:#fff}
.page{display:none;padding:20px;max-width:750px;margin:0 auto}
.page.active{display:block}
.card{background:#1a1a2e;border-radius:12px;padding:18px;margin-bottom:14px;border:1px solid #2a2a4e}
h2{color:#00d4ff;margin-bottom:12px;font-size:17px}
label{display:block;margin:8px 0 4px;color:#888;font-size:12px}
select,input[type=text],input[type=number]{width:100%;padding:9px;border-radius:8px;border:1px solid #2a2a4e;background:#0f0f1a;color:#fff;font-size:14px}
.rr{display:flex;align-items:center;gap:8px}
.rr input{flex:1}
.rr span{min-width:50px;text-align:right;color:#00d4ff;font-weight:bold;font-size:13px}
input[type=range]{width:100%;cursor:pointer;accent-color:#00d4ff}
.btn{padding:10px 18px;border:none;border-radius:8px;font-size:13px;cursor:pointer;margin:4px;transition:.2s}
.btn-play{background:#00d4ff;color:#000}
.btn-save{background:#00c853;color:#000}
.btn:hover{opacity:.8}
.buttons{text-align:center;margin-top:12px}
.status{text-align:center;margin:8px 0;color:#00c853;font-size:12px;min-height:16px}
textarea{width:100%;padding:9px;border-radius:8px;border:1px solid #2a2a4e;background:#0f0f1a;color:#fff;font-size:13px;resize:vertical;min-height:45px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.tag{display:inline-block;padding:6px 14px;border-radius:16px;border:2px solid #2a2a4e;color:#888;cursor:pointer;font-size:12px;margin:3px;transition:.2s}
.tag.active{border-color:#00d4ff;color:#00d4ff}
.tag:hover{border-color:#00d4ff}
.st{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a4e}
.st-v{color:#00d4ff;font-weight:bold}
</style></head><body>
<nav class="nav" id="nav"></nav>
<div id="pages"></div>
<script>
const PAGES=[
{id:'voice',icon:'🔊',title:'Ovoz',html:`
<div class="card"><h2>🎤 Online ovoz (Edge TTS)</h2>
<label>Ovoz</label>
<select id="v_voice"><option value="uz-UZ-SardorNeural">Sardor (erkak)</option><option value="uz-UZ-MadinaNeural">Madina (ayol)</option><option value="ru-RU-DmitryNeural">Dmitriy (rus)</option><option value="en-US-GuyNeural">Guy (ingliz)</option></select>
<label>Pitch (balandlik)</label><div class="rr"><input type="range" id="v_pitch" min="-50" max="50" value="-20" oninput="U('v_pitch')"><span id="v_pitch_v">-20Hz</span></div>
<label>Tezlik</label><div class="rr"><input type="range" id="v_rate" min="-50" max="50" value="5" oninput="U('v_rate')"><span id="v_rate_v">+5%</span></div>
<label>Volume (balandlik)</label><div class="rr"><input type="range" id="v_vol" min="0" max="100" value="100" oninput="U('v_vol')"><span id="v_vol_v">100%</span></div>
</div>
<div class="card"><h2>🤖 Offline ovoz (espeak-ng)</h2>
<label>Ovoz</label>
<select id="v_espeak"><option value="uz">O'zbek erkak</option><option value="uz+f3">O'zbek ayol</option><option value="tr">Turk</option><option value="ru">Rus</option></select>
<label>Pitch (0-99)</label><div class="rr"><input type="range" id="v_ep" min="0" max="99" value="25" oninput="U('v_ep')"><span id="v_ep_v">25</span></div>
<label>Tezlik (80-200)</label><div class="rr"><input type="range" id="v_es" min="80" max="200" value="125" oninput="U('v_es')"><span id="v_es_v">125</span></div>
</div>
<div class="card"><h2>📝 Sinab ko'rish</h2>
<textarea id="v_text">Assalomu alaykum! Men sizning yordamchingizman.</textarea>
<div class="buttons"><button class="btn btn-play" onclick="testVoice('edge')">▶️ Online</button><button class="btn btn-play" onclick="testVoice('espeak')">▶️ Offline</button><button class="btn btn-save" onclick="saveSection('voice')">💾 Saqlash</button></div>
<div class="status" id="v_status"></div></div>`},

{id:'ai',icon:'🧠',title:'AI',html:`
<div class="card"><h2>🧠 LLM sozlamalari</h2>
<label>Model</label>
<select id="a_model"><option value="qwen2.5:0.5b">Qwen 2.5 0.5B (tez)</option><option value="qwen2.5:3b">Qwen 2.5 3B (aqlli)</option><option value="llama3.2:3b">Llama 3.2 3B</option><option value="gemma2:2b">Gemma 2 2B</option></select>
<label>Timeout (sekund)</label><div class="rr"><input type="range" id="a_timeout" min="5" max="60" value="15" oninput="U('a_timeout')"><span id="a_timeout_v">15s</span></div>
<label>System prompt</label>
<textarea id="a_prompt">Sen yordamchi. Qisqa va foydali javob ber o'zbek tilida.</textarea>
</div>
<div class="card"><h2>🌐 Til</h2>
<label>Asosiy til</label>
<select id="a_lang"><option value="uz">O'zbek</option><option value="ru">Русский</option><option value="en">English</option><option value="auto">Avtomatik</option></select>
</div>
<div class="buttons"><button class="btn btn-save" onclick="saveSection('ai')">💾 Saqlash</button></div>
<div class="status" id="a_status"></div>`},

{id:'audio',icon:'🎤',title:'Audio',html:`
<div class="card"><h2>🔊 Speaker balandligi</h2>
<label>Headphone</label><div class="rr"><input type="range" id="au_hp" min="0" max="100" value="100" oninput="U('au_hp')"><span id="au_hp_v">100%</span></div>
<label>Speaker</label><div class="rr"><input type="range" id="au_sp" min="0" max="100" value="100" oninput="U('au_sp')"><span id="au_sp_v">100%</span></div>
<div class="buttons"><button class="btn btn-play" onclick="setVolume()">🔊 Qo'llash</button></div>
</div>
<div class="card"><h2>🎤 Mikrofon</h2>
<label>Sample rate</label>
<select id="au_sr"><option value="16000">16000 Hz</option><option value="44100">44100 Hz</option></select>
<label>Energy threshold (wake word)</label><div class="rr"><input type="range" id="au_th" min="100" max="2000" value="500" oninput="U('au_th')"><span id="au_th_v">500</span></div>
</div>
<div class="card"><h2>🧪 Test</h2>
<div class="buttons"><button class="btn btn-play" onclick="testMic()">🎤 Mikrofon test</button><button class="btn btn-play" onclick="testSpk()">🔊 Speaker test</button></div>
<div class="status" id="au_status"></div></div>
<div class="buttons"><button class="btn btn-save" onclick="saveSection('audio')">💾 Saqlash</button></div>`},

{id:'profile',icon:'👤',title:'Profil',html:`
<div class="card"><h2>👤 Ovoz profili</h2>
<div id="prof_tags"></div></div>
<div class="card"><h2>✏️ Profil nomi</h2>
<div class="g2"><div><label>Erkak nomi</label><input type="text" id="p_name_m" value="Vali"></div>
<div><label>Ayol nomi</label><input type="text" id="p_name_f" value="Zilola"></div></div>
</div>
<div class="card"><h2>🔔 Wake word</h2>
<label>Chaqirish so'zi</label><input type="text" id="p_wake" value="alisa">
<label>Sensitivity</label><div class="rr"><input type="range" id="p_sens" min="1" max="99" value="50" oninput="U('p_sens')"><span id="p_sens_v">50</span></div>
</div>
<div class="buttons"><button class="btn btn-save" onclick="saveSection('profile')">💾 Saqlash</button></div>
<div class="status" id="p_status"></div>`},

{id:'system',icon:'⚙️',title:'Tizim',html:`
<div class="card"><h2>📊 Tizim holati</h2><div id="sys_stats">Yuklanmoqda...</div></div>
<div class="card"><h2>🔄 Boshqaruv</h2>
<div class="buttons">
<button class="btn btn-play" onclick="sysAction('restart_tts')">🔄 TTS restart</button>
<button class="btn btn-play" onclick="sysAction('restart_ollama')">🔄 Ollama restart</button>
<button class="btn btn-play" onclick="sysAction('update')">⬆️ Yangilash</button>
</div><div class="status" id="sys_status"></div></div>`}
];

// Render
let nav=document.getElementById('nav'),pages=document.getElementById('pages');
PAGES.forEach((p,i)=>{
nav.innerHTML+=`<a href="#" ${i==0?'class="active"':''} onclick="showPage('${p.id}')">${p.icon} ${p.title}</a>`;
pages.innerHTML+=`<div class="page ${i==0?'active':''}" id="pg_${p.id}">${p.html}</div>`;
});

function showPage(id){
document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('active'));
document.getElementById('pg_'+id).classList.add('active');
event.target.classList.add('active');
if(id=='system')loadStats();
}

function U(id){
let el=document.getElementById(id),v=el.value;
let sp=document.getElementById(id+'_v');
if(id=='v_pitch')sp.textContent=(v>0?'+':'')+v+'Hz';
else if(id=='v_rate')sp.textContent=(v>0?'+':'')+v+'%';
else if(id=='v_vol'||id=='au_hp'||id=='au_sp')sp.textContent=v+'%';
else if(id=='a_timeout')sp.textContent=v+'s';
else sp.textContent=v;
}

async function testVoice(engine){
let s=document.getElementById('v_status');s.textContent='⏳...';
let body={engine,text:document.getElementById('v_text').value};
if(engine=='edge'){body.voice=document.getElementById('v_voice').value;body.pitch=document.getElementById('v_pitch').value+'Hz';body.rate=document.getElementById('v_rate').value+'%';body.volume=document.getElementById('v_vol').value;}
else{body.voice=document.getElementById('v_espeak').value;body.pitch=document.getElementById('v_ep').value;body.speed=document.getElementById('v_es').value;}
let r=await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
let d=await r.json();s.textContent=d.ok?'✅ Tayyor!':'❌ '+d.error;
}

async function saveSection(section){
let body={section};
if(section=='voice'){body.voice=document.getElementById('v_voice').value;body.pitch=(document.getElementById('v_pitch').value>0?'+':'')+document.getElementById('v_pitch').value+'Hz';body.rate=(document.getElementById('v_rate').value>0?'+':'')+document.getElementById('v_rate').value+'%';body.espeak_voice=document.getElementById('v_espeak').value;body.espeak_pitch=+document.getElementById('v_ep').value;body.espeak_speed=+document.getElementById('v_es').value;body.volume=+document.getElementById('v_vol').value;}
else if(section=='ai'){body.model=document.getElementById('a_model').value;body.timeout=+document.getElementById('a_timeout').value;body.prompt=document.getElementById('a_prompt').value;body.lang=document.getElementById('a_lang').value;}
else if(section=='audio'){body.sample_rate=+document.getElementById('au_sr').value;body.threshold=+document.getElementById('au_th').value;body.headphone=+document.getElementById('au_hp').value;body.speaker=+document.getElementById('au_sp').value;}
else if(section=='profile'){body.name_m=document.getElementById('p_name_m').value;body.name_f=document.getElementById('p_name_f').value;body.wake=document.getElementById('p_wake').value;body.sensitivity=+document.getElementById('p_sens').value/100;}
let r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
let d=await r.json();
let st=document.getElementById(section[0]+'_status');if(st)st.textContent=d.ok?'💾 Saqlandi!':'❌ '+d.error;
}

async function setVolume(){
let hp=document.getElementById('au_hp').value,sp=document.getElementById('au_sp').value;
let r=await fetch('/api/volume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({headphone:hp,speaker:sp})});
let d=await r.json();document.getElementById('au_status').textContent=d.ok?'✅':'❌';
}
async function testMic(){document.getElementById('au_status').textContent='🎤 Yozilmoqda...';let r=await fetch('/api/test_mic');let d=await r.json();document.getElementById('au_status').textContent=d.ok?'✅ Mikrofon ishlaydi':'❌ '+d.error;}
async function testSpk(){document.getElementById('au_status').textContent='🔊...';let r=await fetch('/api/test_spk');let d=await r.json();document.getElementById('au_status').textContent=d.ok?'✅':'❌';}
async function loadStats(){let r=await fetch('/api/stats');let d=await r.json();let h='';for(let[k,v]of Object.entries(d)){h+=`<div class="st"><span>${k}</span><span class="st-v">${v}</span></div>`;}document.getElementById('sys_stats').innerHTML=h;}
async function sysAction(a){document.getElementById('sys_status').textContent='⏳...';let r=await fetch('/api/system',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})});let d=await r.json();document.getElementById('sys_status').textContent=d.ok?'✅ '+d.msg:'❌';}

// Load config on start
fetch('/api/config').then(r=>r.json()).then(d=>{
if(d.tts){
document.getElementById('v_voice').value=d.tts.voice||'uz-UZ-SardorNeural';
document.getElementById('v_pitch').value=parseInt(d.tts.pitch)||0;
document.getElementById('v_rate').value=parseInt(d.tts.rate)||0;
document.getElementById('v_espeak').value=d.tts.espeak_voice||'uz';
document.getElementById('v_ep').value=d.tts.espeak_pitch||25;
document.getElementById('v_es').value=d.tts.espeak_speed||125;
}
if(d.profiles){
let tags='';for(let[k,v]of Object.entries(d.profiles)){tags+=`<span class="tag ${k==d.active_profile?'active':''}" onclick="setProfile('${k}')">${v.name} (${k})</span>`;}
document.getElementById('prof_tags').innerHTML=tags;
if(d.profiles.erkak)document.getElementById('p_name_m').value=d.profiles.erkak.name;
if(d.profiles.ayol)document.getElementById('p_name_f').value=d.profiles.ayol.name;
}
if(d.wake_word)document.getElementById('p_wake').value=d.wake_word.keyword||'alisa';
document.querySelectorAll('input[type=range]').forEach(el=>U(el.id));
});

async function setProfile(name){
let r=await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile:name})});
location.reload();
}
</script></body></html>'''


async def index(request):
    return web.Response(text=HTML, content_type='text/html')

async def get_config_api(request):
    return web.json_response(load_config())

async def test_voice(request):
    data = await request.json()
    try:
        if data.get('engine') == 'edge':
            voice = data.get('voice', 'uz-UZ-SardorNeural')
            pitch = data.get('pitch', '-20Hz')
            rate = data.get('rate', '+5%')
            if not pitch.startswith(('+', '-')): pitch = ('+' if int(pitch.replace('Hz',''))>=0 else '') + pitch
            if not rate.startswith(('+', '-')): rate = ('+' if int(rate.replace('%',''))>=0 else '') + rate
            mp3, wav = '/tmp/alisa_tts/test.mp3', '/tmp/alisa_tts/test.wav'
            subprocess.run(['edge-tts', '--voice', voice, '--pitch='+pitch, '--rate='+rate, '--text', data['text'], '--write-media', mp3], capture_output=True, timeout=15)
            subprocess.run(['ffmpeg', '-y', '-i', mp3, '-ar', '16000', '-ac', '1', wav], capture_output=True, timeout=10)
            subprocess.run(['aplay', '-D', 'plughw:2,0', wav], capture_output=True, timeout=30)
        else:
            wav = '/tmp/alisa_tts/test_e.wav'
            subprocess.run(['espeak-ng', '-v', data.get('voice','uz'), '-s', str(data.get('speed','125')), '-p', str(data.get('pitch','25')), data['text'], '-w', wav], capture_output=True, timeout=10)
            subprocess.run(['aplay', '-D', 'plughw:2,0', wav], capture_output=True, timeout=30)
        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def save_settings(request):
    data = await request.json()
    cfg = load_config()
    section = data.get('section')
    try:
        if section == 'voice':
            cfg['tts'] = {'voice': data['voice'], 'pitch': data['pitch'], 'rate': data['rate'], 'espeak_voice': data['espeak_voice'], 'espeak_pitch': data['espeak_pitch'], 'espeak_speed': data['espeak_speed'], 'volume': data.get('volume', 100)}
        elif section == 'ai':
            cfg.setdefault('llm', {})['local_timeout_sec'] = data['timeout']
            if 'providers' in cfg.get('llm', {}):
                for p in cfg['llm']['providers']:
                    if p.get('name') == 'ollama': p['model'] = data['model']
            cfg['language'] = data.get('lang', 'uz')
        elif section == 'audio':
            cfg.setdefault('audio', {})['sample_rate'] = data['sample_rate']
            cfg.setdefault('wake_word', {}).setdefault('energy_gated', {})['threshold'] = data['threshold']
        elif section == 'profile':
            cfg.setdefault('profiles', {}).setdefault('erkak', {})['name'] = data['name_m']
            cfg.setdefault('profiles', {}).setdefault('ayol', {})['name'] = data['name_f']
            cfg.setdefault('wake_word', {})['keyword'] = data['wake']
            cfg.setdefault('wake_word', {})['sensitivity'] = data['sensitivity']
        save_full_config(cfg)
        from alisa.core.config import reset_config
        reset_config()
        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def set_volume(request):
    data = await request.json()
    try:
        hp = int(int(data.get('headphone', 100)) * 127 / 100)
        sp = int(int(data.get('speaker', 100)) * 127 / 100)
        subprocess.run(['amixer', '-c', '2', 'set', 'Headphone', f'{hp}'], capture_output=True)
        subprocess.run(['amixer', '-c', '2', 'set', 'Speaker', f'{sp}'], capture_output=True)
        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def test_mic(request):
    try:
        subprocess.run(['arecord', '-D', 'plughw:2,0', '-f', 'S16_LE', '-r', '16000', '-d', '2', '/tmp/mic_t.wav'], capture_output=True, timeout=5)
        subprocess.run(['aplay', '-D', 'plughw:2,0', '/tmp/mic_t.wav'], capture_output=True, timeout=5)
        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def test_spk(request):
    try:
        subprocess.run(['espeak-ng', '-v', 'uz', 'Test ovoz'], capture_output=True, timeout=5)
        return web.json_response({'ok': True})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def get_stats(request):
    import psutil
    temp = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True).stdout.strip()
    return web.json_response({
        'CPU': f"{psutil.cpu_percent()}%",
        'RAM': f"{psutil.virtual_memory().percent}% ({psutil.virtual_memory().used//1024//1024}MB)",
        'Harorat': temp.replace('temp=',''),
        'Disk': f"{psutil.disk_usage('/').percent}%",
        'Uptime': f"{(psutil.boot_time())}",
    })

async def system_action(request):
    data = await request.json()
    action = data.get('action')
    try:
        if action == 'restart_tts':
            return web.json_response({'ok': True, 'msg': 'TTS restart qilindi'})
        elif action == 'restart_ollama':
            subprocess.run(['pkill', 'ollama'], capture_output=True)
            subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return web.json_response({'ok': True, 'msg': 'Ollama restart'})
        elif action == 'update':
            subprocess.run(['git', '-C', '/home/baxrom/alisa_ai', 'pull'], capture_output=True)
            return web.json_response({'ok': True, 'msg': 'Yangilandi'})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def set_profile(request):
    data = await request.json()
    cfg = load_config()
    cfg['active_profile'] = data.get('profile', 'erkak')
    p = cfg.get('profiles', {}).get(cfg['active_profile'], {})
    if p:
        cfg.setdefault('tts', {}).update({k: p[k] for k in ['voice','pitch','rate','espeak_voice','espeak_pitch','espeak_speed'] if k in p})
    save_full_config(cfg)
    from alisa.core.config import reset_config
    reset_config()
    return web.json_response({'ok': True})

def create_app():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/api/config', get_config_api)
    app.router.add_post('/api/test', test_voice)
    app.router.add_post('/api/save', save_settings)
    app.router.add_post('/api/volume', set_volume)
    app.router.add_get('/api/test_mic', test_mic)
    app.router.add_get('/api/test_spk', test_spk)
    app.router.add_get('/api/stats', get_stats)
    app.router.add_post('/api/system', system_action)
    app.router.add_post('/api/profile', set_profile)
    return app

if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8085)
