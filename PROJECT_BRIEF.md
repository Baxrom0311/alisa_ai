# Alisa v2 — Raspberry Pi O'zbek AI Assistant

## Goal

Raspberry Pi 5/4 da ishlaydigan real-time o'zbekcha voice assistant. TrooperAI arxitekturasiga asoslangan — WebSocket streaming, sentence-by-sentence TTS, doimiy eshitish. Gibrid LLM (online + offline).

## Arxitektura (TrooperAI dan olingan, kengaytirilgan)

```
┌─────────────────────────────────────────────────────────┐
│  CLIENT (audio_client.py)                               │
│  - PyAudio mic capture (16kHz mono, callback)           │
│  - WebSocket orqali serverga audio stream               │
│  - Serverdan TTS audio qabul qilish                     │
│  - Speaker playback (48kHz stereo, threading)           │
│  - Mic mute during playback (feedback prevention)       │
│  - Fade in/out for smooth audio                         │
└────────────────────────┬────────────────────────────────┘
                         │ WebSocket (ws://localhost:8765)
                         │ Binary: PCM audio chunks
                         │ Text: "__END__", "__done__", config
┌────────────────────────▼────────────────────────────────┐
│  SERVER (voice_server.py)                               │
│                                                         │
│  1. STT: whisper.cpp (o'zbek fine-tuned model)          │
│     - Real-time, silence detection                      │
│     - islomov/rubaistt_v2 yoki OvozifyLabs/whisper-uz   │
│                                                         │
│  2. LLM: Gibrid fallback chain                          │
│     ├─ Online: GPT-4o-mini → Gemini → DeepSeek         │
│     └─ Offline: llama.cpp (qwen2.5:3b)                  │
│     - Sentence streaming (har gap tayyor — TTS ga)      │
│                                                         │
│  3. TTS: Piper (subprocess, --output_raw)               │
│     - O'zbek: facebook/mms-tts-uzb (offline)            │
│     - Yoki: edge-tts uz-UZ (online, yaxshi sifat)       │
│     - Sentence-by-sentence (kutmaydi)                   │
│     - SoX upsampling 16kHz → 48kHz stereo               │
│                                                         │
│  4. Telegram bot (alohida thread)                       │
│     - /ask, /status, /mode                              │
└─────────────────────────────────────────────────────────┘
```

## Asosiy tamoyillar (TrooperAI dan)

1. **Doimiy eshitish** — mic doim yoniq, audio stream uzluksiz
2. **Silence detection** — odam gapirishni to'xtatganda LLM ga yuboradi
3. **Sentence streaming** — LLM birinchi gapni yozishi bilan TTS boshlaydi
4. **Mic mute during playback** — o'z ovozini eshitmasligi uchun
5. **WebSocket** — client/server alohida, parallel ishlaydi
6. **Low-effort filter** — "hm", "uh" kabi shovqinlarni filtrlash

## Bizning qo'shimchalar (TrooperAI da yo'q)

1. **Wake word** — "Alisa" deyilganda faollashadi (doim eshitmaydi)
2. **Gibrid LLM** — online API lar + offline llama.cpp fallback
3. **O'zbek STT** — whisper.cpp + uz fine-tuned model
4. **O'zbek TTS** — facebook/mms-tts-uzb yoki edge-tts
5. **Telegram bot** — remote boshqaruv
6. **Resepsiya rejimi** — mehmonlarni salomlash
7. **Multi-provider LLM** — qaysi API key bor bo'lsa shu ishlaydi

## Fayllar strukturasi

```
alisa/
  audio_client.py        # Mic capture + speaker playback + WebSocket client
  voice_server.py        # STT + LLM + TTS pipeline (WebSocket server)
  llm_manager.py         # Multi-provider LLM (online/offline fallback)
  tts_manager.py         # Multi-engine TTS (edge-tts, piper, mms, gTTS)
  config.json            # Sozlamalar
  providers/
    openai_provider.py
    gemini_provider.py
    deepseek_provider.py
    ollama_provider.py   # llama.cpp/Ollama local
  tts_engines/
    edge_tts.py          # Microsoft edge-tts (online, natural)
    piper_tts.py         # Piper (offline, en/ru)
    mms_tts.py           # Facebook MMS (offline, uz, robotic)
  telegram_bot.py        # Telegram integration
  wake_word.py           # "Alisa" wake word detection
  reception.py           # Resepsiya rejimi
  web_ui/
    app.py               # FastAPI web config panel
    templates/
      index.html         # Sozlamalar sahifasi
  utils.py               # Yordamchi funksiyalar
  models/                # STT/TTS model fayllari
  voices/                # Piper voice fayllari
```

## STT variantlari (o'zbek)

| Model | Hajm | Sifat | Tezlik Pi da |
|-------|------|-------|--------------|
| whisper.cpp tiny | 75MB | ⚠️ O'rtacha | ✅ 2-3s |
| whisper.cpp base | 142MB | ✅ Yaxshi | ⚠️ 4-6s |
| islomov/rubaistt_v2_medium | 769MB | ✅✅ Zo'r (UZ tuned) | ❌ Sekin |
| OvozifyLabs/whisper-small-uz | 244MB | ✅ Yaxshi (UZ/EN/RU) | ⚠️ 5-8s |
| Vosk (small model) | 50MB | ⚠️ UZ yo'q | ✅ 10ms |

**Tavsiya:** whisper.cpp base + o'zbek fine-tune. Yoki Vosk + custom uz model.

## TTS variantlari (o'zbek)

| Model | Sifat | Offline | Tezlik |
|-------|-------|---------|--------|
| facebook/mms-tts-uzb | ⚠️ Robotic | ✅ | ✅ Tez |
| edge-tts uz-UZ-MadinaNeural | ✅✅ Natural | ❌ Online | ✅ Tez |
| edge-tts uz-UZ-SardorNeural | ✅✅ Natural | ❌ Online | ✅ Tez |
| Piper (custom trained) | ✅ Yaxshi | ✅ | ✅ Tez |

**Tavsiya gibrid:**
- Internet bor → edge-tts (MadinaNeural — ayol, SardorNeural — erkak)
- Internet yo'q → facebook/mms-tts-uzb (offline fallback)

## LLM fallback chain

```python
providers = [
    {"name": "openai", "model": "gpt-4o-mini", "timeout": 5},
    {"name": "gemini", "model": "gemini-2.0-flash", "timeout": 5},
    {"name": "deepseek", "model": "deepseek-chat", "timeout": 5},
    {"name": "grok", "model": "grok-2", "timeout": 5},
    {"name": "claude", "model": "claude-sonnet", "timeout": 5},
    {"name": "ollama", "model": "qwen2.5:3b", "timeout": 10},  # offline
]
# API key yo'q = skip (0s)
# Oxirgi ishlagan provider eslab qolinadi
# Sentence streaming: har gap tayyor bo'lishi bilan TTS ga yuboriladi
```

## config.json

```json
{
  "language": "uz",
  "wake_word": "alisa",
  "mic_name": "USB",
  "audio_output_device": "USB",
  "volume": 80,
  "mute_mic_during_playback": true,
  "fade_duration_ms": 100,
  "history_length": 6,
  "system_prompt": "Sen Alisa — aqlli yordamchi. Faqat o'zbek tilida gaplash. Javoblaring qisqa va foydali bo'lsin.",
  "greeting_message": "Assalomu alaykum! Sizga qanday yordam bera olaman?",
  "session_timeout": 30,
  "stt": {
    "engine": "whisper",
    "model": "base",
    "language": "uz"
  },
  "tts": {
    "online": "edge-tts",
    "online_voice": "uz-UZ-MadinaNeural",
    "offline": "mms-tts-uzb",
    "offline_voice": "facebook/mms-tts-uzb"
  },
  "llm": {
    "timeout_sec": 5,
    "providers": [
      {"name": "openai", "api_key": "", "model": "gpt-4o-mini"},
      {"name": "gemini", "api_key": "", "model": "gemini-2.0-flash"},
      {"name": "deepseek", "api_key": "", "model": "deepseek-chat"},
      {"name": "ollama", "model": "qwen2.5:3b", "url": "http://localhost:11434"}
    ]
  },
  "telegram": {
    "bot_token": "",
    "chat_id": ""
  },
  "reception": {
    "enabled": false,
    "greeting": "Assalomu alaykum! Kimni kutayapsiz?"
  }
}
```

## Ishlash tartibi

1. `voice_server.py` ishga tushadi (WebSocket server :8765)
2. `audio_client.py` ishga tushadi (mic + speaker)
3. Client mic dan audio oladi → serverga yuboradi
4. Server:
   - Wake word "Alisa" ni eshitadi → faollashadi
   - STT: audio → matn (whisper.cpp)
   - LLM: matn → javob (streaming, sentence by sentence)
   - TTS: har bir gap → audio
   - Audio → client ga qaytaradi
5. Client speaker dan o'ynatadi
6. Telegram bot parallel ishlaydi

## Acceptance Criteria

- [ ] "Alisa" deyilganda faollashadi
- [ ] O'zbekcha savol → o'zbekcha javob (< 3s birinchi gap)
- [ ] Sentence streaming ishlaydi (kutmaydi)
- [ ] Internet yo'q — offline LLM + offline TTS ishlaydi
- [ ] Internet bor — online LLM + edge-tts (natural ovoz)
- [ ] Mic mute during playback (echo yo'q)
- [ ] Telegram /ask ishlaydi
- [ ] 24/7 systemd service
- [ ] Pi 4GB RAM da sig'adi

## Development Phases

### Phase 1: WebSocket pipeline (TrooperAI bazasi)
- audio_client.py (mic → ws → speaker)
- voice_server.py (ws → STT → LLM → TTS → ws)
- Avval inglizcha test (whisper base + ollama + piper en)

### Phase 2: Multi-TTS engine
- TTS Manager — bir nechta engine ni boshqaradi:
  - edge-tts (online): uz-UZ-MadinaNeural, uz-UZ-SardorNeural
  - Piper (offline): ru-RU, en-US voices
  - facebook/mms-tts-uzb (offline, o'zbek, robotic)
  - gTTS (online, oddiy)
- Config dan tanlash mumkin
- Internet yo'q → avtomatik offline engine ga o'tadi

### Phase 3: Gibrid LLM + O'zbek STT
- llm_manager.py + providers/
- Fallback chain + sentence streaming
- whisper.cpp uz model (OvozifyLabs/whisper-small-uz-v1)

### Phase 4: Wake word + Telegram
- "Alisa" wake word (openWakeWord)
- Telegram bot integration (/ask, /status, /mode, /voice)

### Phase 5: Web UI Config Panel
- Oddiy web sahifa (localhost:8080)
- Sozlamalar:
  - TTS engine tanlash (MadinaNeural / SardorNeural / Piper ru / Piper en)
  - LLM provider tanlash va API key kiritish
  - Wake word sensitivity
  - Volume, mic device
  - Resepsiya rejimi on/off
  - System prompt o'zgartirish
- FastAPI + HTML (minimal, Pi da ishlaydi)

### Phase 6: Resepsiya + Deploy
- Reception mode
- systemd service
- install.sh

## Reference

- TrooperAI: https://github.com/m15-ai/TrooperAI
- whisper.cpp: https://github.com/ggml-org/whisper.cpp
- Piper TTS: https://github.com/rhasspy/piper
- edge-tts: https://github.com/rany2/edge-tts
- facebook/mms-tts-uzb: https://huggingface.co/facebook/mms-tts-uzb-script_cyrillic
- islomov/rubaistt_v2: https://huggingface.co/islomov/rubaistt_v2_medium
- OvozifyLabs/whisper-uz: https://huggingface.co/OvozifyLabs/whisper-small-uz-v1
- llama.cpp: https://github.com/ggml-org/llama.cpp
