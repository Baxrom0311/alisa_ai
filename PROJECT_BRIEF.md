# Alisa — Raspberry Pi Local AI Assistant

## Goal

Raspberry Pi 4/5 da ishlaydigan o'zbekcha AI assistant. Alisa ovoz bilan gaplashadi, savolarga javob beradi, resepsiya sifatida ishlaydi, va Telegram orqali boshqariladi. Gibrid arxitektura: internet bo'lsa online LLM, bo'lmasa local LLM. Hech qachon qotib qolmaydi.

## Til: O'zbekcha

Alisa FAQAT o'zbekcha gaplashadi. System prompt o'zbekcha. Javoblar o'zbekcha. Foydalanuvchi boshqa tilda yozsa ham o'zbekcha javob beradi.

## Core Architecture: Gibrid Multi-LLM

### Fallback Chain (prioritet bo'yicha)

```
Savol keldi → LLM Manager (oxirgi ishlagan providerdan boshlaydi)
    │
    ├─ 1. GPT-4o-mini (OpenAI) ─── API key bor → 2-3s javob
    │
    ├─ 2. Gemini (Google) ─── GPT ishlamasa → 2-3s
    │
    ├─ 3. DeepSeek ─── timeout 5s → keyingisi
    │
    ├─ 4. Grok (xAI) ─── timeout 5s → keyingisi
    │
    ├─ 5. Claude (Anthropic) ─── timeout 5s → keyingisi
    │
    └─ 6. Local LLM (Ollama) ─── OFFLINE, har doim ishlaydi, 3-5s
            qwen2.5:3b

API key yo'q = skip (0s kutmaydi)
Ishlagan provider eslab qolinadi = keyingi safar undan boshlaydi
Real javob vaqti: 2-3 sekund (odatda birinchi providerda ishlaydi)
```

### LLM Manager qoidalari:
- Har bir provider uchun API key config.yaml da saqlanadi
- API key yo'q provider skip qilinadi (0s — umuman chaqirmaydi)
- Timeout: 5s (online), 10s (local)
- Timeout bo'lsa keyingisiga o'tadi (HECH QACHON qotib qolmaydi)
- Oxirgi muvaffaqiyatli provider eslab qolinadi — keyingi safar SHU DAN boshlaydi
- Barcha providerlar bir xil interface: `async def generate(prompt, system) -> str`
- Rate limit/quota tugasa keyingisiga o'tadi
- Local LLM har doim oxirgi fallback (internet kerak emas)
- Real javob vaqti: 2-3s (chunki ishlagan providerdan boshlaydi)

## Core Features

### 1. Ovozli suhbat (Voice Conversation)
- Wake word: "Alisa" (openWakeWord yoki energy-gated)
- STT: whisper.cpp (local, ARM optimized)
- LLM: Gibrid (yuqoridagi fallback chain)
- TTS: Piper TTS (local, o'zbek/rus ovoz)
- Javob vaqti: < 3 sekund (local), < 5 sekund (online)
- Qotib qolmaslik: har bir bosqichda timeout, skip, fallback

### 2. Telegram Bot
- /ask [savol] — savol yuborish, javob olish
- /status — CPU, RAM, harorat, qaysi LLM ishlatilmoqda
- /mode [reception|assistant] — rejim almashtirish
- /providers — qaysi LLM lar faol, qaysilari o'chiq
- /restart — Alisa ni qayta ishga tushirish
- /update — git pull + restart
- Ovozli xabar → STT → LLM → matnli javob

### 3. Resepsiya rejimi
- Mehmonni salomlash (o'zbekcha)
- FAQ javoblar (ish vaqti, manzil, kim bilan uchrashish)
- Telegram ga "Mehmon keldi" xabari
- Oddiy savollar uchun LLM shart emas (knowledge base)

### 4. Online xususiyatlar (internet mavjud bo'lganda)
- Ob-havo (OpenWeatherMap)
- Yangiliklar
- OTA update (git pull)
- Online LLM (fallback chain)

## Tech Stack

### Hardware
- Raspberry Pi 4 (4GB) yoki Pi 5
- USB mikrofon
- Speaker (3.5mm yoki USB)
- MicroSD 64GB+

### Software — AI
- **STT**: whisper.cpp (ARM64 optimized, tiny/base model)
- **LLM Online**: OpenAI, Gemini, DeepSeek, Grok, Claude (fallback chain)
- **LLM Local**: Ollama + qwen2.5:3b (offline fallback)
- **TTS**: Piper TTS (local)
- **Wake word**: openWakeWord (yoki energy-gated fallback)

### Software — Backend
- Python 3.11+
- asyncio + aiohttp
- python-telegram-bot (async)
- PyAudio / sounddevice
- systemd service
- YAML config
- structlog

## Project Structure

```
alisa/
  core/
    assistant.py         # Asosiy loop: listen → think → speak
    config.py            # YAML config loader
  voice/
    stt.py               # whisper.cpp wrapper
    tts.py               # Piper TTS wrapper
    wake_word.py         # Wake word detection
    audio_io.py          # Mikrofon/speaker
  brain/
    llm_manager.py       # Multi-LLM fallback chain (ASOSIY)
    providers/
      base.py            # Abstract LLM provider interface
      openai.py          # GPT-4o-mini
      gemini.py          # Google Gemini
      deepseek.py        # DeepSeek
      grok.py            # xAI Grok
      claude.py          # Anthropic Claude
      ollama.py          # Local Ollama (offline)
    memory.py            # Conversation history
    online.py            # Weather, news
  telegram/
    bot.py               # Telegram bot
    commands.py          # /ask, /status, /providers, /mode
  reception/
    greeter.py           # Mehmon salomlash
    knowledge.py         # FAQ bazasi
  services/
    health.py            # System monitoring
    updater.py           # OTA update
    scheduler.py         # Vaqtli vazifalar
  tests/
    test_llm_manager.py
    test_providers.py
    test_stt.py
    test_tts.py
    test_telegram.py
    test_assistant.py
  config.yaml            # API keys, sozlamalar
  setup/
    install.sh           # Pi ga o'rnatish
    systemd/alisa.service
```

## config.yaml namunasi

```yaml
language: uz
wake_word: "alisa"

llm:
  timeout_sec: 5
  local_timeout_sec: 10
  providers:
    - name: openai
      api_key: ""  # bo'sh = skip
      model: gpt-4o-mini
      base_url: https://api.openai.com/v1
    - name: gemini
      api_key: ""
      model: gemini-2.0-flash
    - name: deepseek
      api_key: ""
      model: deepseek-chat
      base_url: https://api.deepseek.com/v1
    - name: grok
      api_key: ""
      model: grok-2
      base_url: https://api.x.ai/v1
    - name: claude
      api_key: ""
      model: claude-sonnet-4-20250514
    - name: ollama
      model: qwen2.5:3b
      base_url: http://localhost:11434

stt:
  model: tiny
  language: uz

tts:
  model: uz_UZ-doniyorbek-medium
  speed: 1.0

telegram:
  bot_token: ""
  chat_id: ""

reception:
  greeting: "Assalomu alaykum! Sizga qanday yordam bera olaman?"
  work_hours: "9:00 - 18:00"
  address: ""
```

## System Prompt (O'zbekcha)

```
Sen Alisa — aqlli yordamchi. Sen faqat o'zbek tilida gaplashasan.
Javoblaring qisqa, aniq va foydali bo'lsin.
Agar bilmasang, "Bilmayman, lekin izlab ko'raman" de.
Sen Raspberry Pi da ishlaysan, resepsiyada mehmonlarni kutib olasan.
```

## Constraints

- RAM: < 3GB (OS + Alisa + local model)
- Javob vaqti: < 3s (local), < 5s (online)
- HECH QACHON qotib qolmasligi kerak (timeout + fallback)
- API key yo'q provider avtomatik skip
- Barcha xatolar graceful handle qilinadi
- SD card yemirilishini kamaytirish

## Acceptance Criteria

- [ ] Wake word "Alisa" ishlaydi
- [ ] Ovozli savol → o'zbekcha javob < 5 sek
- [ ] Internet yo'q bo'lsa local LLM ishlaydi
- [ ] Internet bor bo'lsa online LLM ishlatadi
- [ ] Bitta provider ishlamasa keyingisiga o'tadi (fallback)
- [ ] Telegram /ask ishlaydi
- [ ] Telegram /status — qaysi provider ishlatilmoqda ko'rsatadi
- [ ] Telegram /providers — barcha providerlar holati
- [ ] Resepsiya rejimi ishlaydi
- [ ] pytest barcha testlar o'tadi
- [ ] systemd service sifatida 24/7 ishlaydi
- [ ] config.yaml dan API keylar o'qiladi

## Development Phases

### Phase 1: LLM Manager + Fallback Chain
- providers/ papkasi — har bir LLM uchun adapter
- llm_manager.py — fallback logic, timeout, retry
- config.yaml dan providerlarni o'qish
- Test: mock providerlar bilan fallback ishlashini tekshirish

### Phase 2: Voice Pipeline
- whisper.cpp STT
- Piper TTS
- Wake word
- assistant.py loop

### Phase 3: Telegram Bot
- /ask, /status, /providers, /mode
- Ovozli xabar qabul qilish

### Phase 4: Reception + Online
- Mehmon salomlash
- FAQ knowledge base
- Ob-havo, yangiliklar

### Phase 5: Deployment
- install.sh
- systemd service
- OTA update

## Non-Goals

- Web UI
- Video/kamera
- Smart home
- Ko'p foydalanuvchi
- O'z modelini train qilish
