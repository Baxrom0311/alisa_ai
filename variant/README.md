# Humanoid Robot Voice Assistant

Uzbek tilida gaplashuvchi ovozli yordamchi loyiha. Dastur mikrofon orqali gapni eshitadi, OpenRouter orqali modeldan javob oladi va `edge-tts` yordamida ovoz chiqaradi.

## Asosiy fayllar
- `main.py` - Windows uchun asosiy ishga tushirish fayli.
- `main_rpi.py` - Raspberry Pi yoki Linux muhiti uchun variant.

## Qaysi muhitda ishlatilgan
Loyiha lokalda turli muhitlarda sinab ko'rilgan, lekin hozirgi repodagi mavjud virtual environment quyidagiga mos:

- Python `3.12.10`
- Virtual environment nomi: `venv312`
- Windows muhitida ishlatilgan

Repo ichidagi `venv312/pyvenv.cfg` fayliga ko'ra loyiha aynan `Python 3.12` bilan yaratilgan. Shu sababli eng xavfsiz tavsiya:

- Windows uchun: `Python 3.12.x`
- Raspberry Pi / Linux uchun: imkon qadar `Python 3.12.x`

`PyAudio` kabi kutubxonalar sabab `Python 3.12` bu loyiha uchun eng mos variant hisoblanadi.

## Ishlash mantig'i
Loyiha quyidagi paketlarga tayanadi:

- `openai`
- `edge-tts`
- `SpeechRecognition`
- `PyAudio`
- `pygame-ce`

Qo'shimcha ravishda internet ulanishi, mikrofon va audio chiqish qurilmasi kerak bo'ladi.

## Tavsiya etilgan o'rnatish

### 1. Python versiyasini tayyorlash
Kompyuteringizda `Python 3.12.x` o'rnatilgan bo'lsin.

Tekshirish:

```bash
python --version
```

Agar tizimda bir nechta Python versiya bo'lsa, aynan `3.12` bilan virtual environment yaratgan ma'qul.

Windows misol:

```bash
py -3.12 -m venv .venv
```

Linux yoki Raspberry Pi misol:

```bash
python3.12 -m venv .venv
```

### 2. Virtual environment'ni yoqish
Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
.venv\Scripts\activate.bat
```

Linux / Raspberry Pi:

```bash
source .venv/bin/activate
```

### 3. Kutubxonalarni o'rnatish
Avval `pip` ni yangilang:

```bash
python -m pip install --upgrade pip
```

So'ng dependency'larni o'rnating:

```bash
pip install -r requirements.txt
```

## Platformaga qarab muhim eslatmalar

### Windows
`main.py` Windows uchun moslangan. Kodda Windows encoding bilan bog'liq qo'shimcha sozlashlar bor, shuning uchun Windows'da odatda shu faylni ishlatish tavsiya qilinadi.

Ishga tushirish:

```bash
python main.py
```

### Linux / Raspberry Pi
`main_rpi.py` Linux tomonini hisobga olgan. Kod ichida `SDL_AUDIODRIVER=alsa` kabi sozlamalar ishlatiladi.

Ishga tushirish:

```bash
python main_rpi.py
```

Raspberry Pi yoki Debian/Ubuntu asosidagi tizimlarda `PyAudio` va audio kutubxonalari uchun tizim paketlari kerak bo'lishi mumkin:

```bash
sudo apt update
sudo apt install portaudio19-dev python3-dev ffmpeg libsdl2-mixer-2.0-0
```

Agar `PyAudio` o'rnatishda xato chiqsa, odatda muammo Python paketida emas, tizimdagi `portaudio` kutubxonasida bo'ladi.

## .env sozlash
Repo ichida `.env.example` bor. Uni asos qilib `.env` yarating.

Namunaviy qiymatlar:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
GEMINI_TEXT_MODEL=google/gemini-2.5-flash
EDGE_TTS_VOICE=uz-UZ-SardorNeural
EDGE_TTS_RATE=+15%
EDGE_TTS_PITCH=+50Hz
EDGE_TTS_VOLUME=+18%
STT_LANGUAGE=uz-UZ
GREETING_TEXT=Assalomu alaykum! Tanishsak bo'ladimi? Ismingiz nima?
```

## Muhim sozlamalar izohi
- `OPENROUTER_API_KEY` - OpenRouter API kaliti.
- `GEMINI_TEXT_MODEL` - ishlatiladigan model nomi.
- `EDGE_TTS_VOICE` - ovoz modeli.
- `EDGE_TTS_RATE` - gapirish tezligi.
- `EDGE_TTS_PITCH` - ovoz balandligi / tonalligi.
- `EDGE_TTS_VOLUME` - ovoz darajasi.
- `STT_LANGUAGE` - speech-to-text tili.
- `GREETING_TEXT` - dastur ishga tushganda aytiladigan kirish matni.

## Ehtimoliy muammolar

### 1. `OPENROUTER_API_KEY topilmadi`
`.env` fayli yaratilmagan yoki kalit noto'g'ri kiritilgan.

### 2. Mikrofon ishlamayapti
- Operatsion tizimda microphone permission yoqilganini tekshiring.
- To'g'ri input device ulanganini tekshiring.
- Bluetooth yoki USB mikrofon ishlatsa, dastur uni avtomatik tanlashga harakat qiladi.

### 3. `PyAudio` install bo'lmayapti
- Windows'da `Python 3.12` ishlatayotganingizni tekshiring.
- Linux'da `portaudio19-dev` o'rnatilganini tekshiring.

### 4. Ovoz chiqmayapti
- `pygame` audio driver va tizim audio qurilmalarini tekshiring.
- Linux'da ALSA/PulseAudio sozlamalarini tekshiring.

## Xavfsizlik
- Haqiqiy API kalitlarini hech qachon kod ichiga yozmang.
- `.env`, `deepseek`, `venv312`, `__pycache__` fayllari `.gitignore` orqali ignore qilinadi.
- Push qilishdan oldin `git status` bilan qaysi fayllar commit bo'layotganini tekshirib chiqing.
