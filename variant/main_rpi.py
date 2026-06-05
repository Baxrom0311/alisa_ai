import sys
import os
import io
import time
import asyncio
import re
import pyaudio
import pygame
import speech_recognition as sr
from openai import OpenAI
import edge_tts
import json  # JSON import qilinadi
from service.robot_controller import RobotController  # RobotController import qilinadi

if sys.platform.startswith("linux"):
    os.environ.setdefault("SDL_AUDIODRIVER", "alsa")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env_file()

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "",
).strip()
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "google/gemini-2.5-flash")
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "uz-UZ-SardorNeural")
EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+15%")
EDGE_TTS_PITCH = os.getenv("EDGE_TTS_PITCH", "+50Hz")
EDGE_TTS_VOLUME = os.getenv("EDGE_TTS_VOLUME", "+18%")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "uz-UZ")
GREETING_TEXT = os.getenv(
    "GREETING_TEXT",
    "Assalomu alaykum! Tanishsak bo'ladimi? Ismingiz nima?",
)
GEMINI_TEXT_FALLBACK_MODELS = [
    GEMINI_TEXT_MODEL,
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-001",
]

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://amir-temur-ai.uz",
        "X-Title": "Yordamchi AI",
    },
)


# ==========================================
# 3. PERSONA VA TTS YO'RIQNOMASI
# ==========================================
def build_gemini_persona_prompt():
    return (
        "You are a friendly synthetic Uzbek-speaking boy character named Ali. "
        "You are not a real person. You speak only in Uzbek. "
        "You answer in a warm, curious, natural, child-like boy tone. "
        "Your answers must be short, clear, and suitable for being spoken aloud. "
        "Do not use markdown, bullet points, code formatting, emojis, or long formal explanations unless the user explicitly asks for technical details. "
        "If the user asks something complex, explain it simply and step by step in Uzbek. "
        "Always keep the conversation natural and friendly. "
        "Your response must be a JSON object with two keys: `speech` (string) and `movements` (array of objects). "
        "The `speech` key should contain the text you want to speak in Uzbek. "
        "The `movements` key should contain a list of robot movement commands. Each command object must have a `command` key (an array of 7 integers representing angles for [Head, Right Shoulder, Right Elbow, Right Wrist, Left Shoulder, Left Elbow, Left Wrist], each between 0 and 180 degrees) and a `wait` key (a float representing the time in seconds to wait after executing the command). "
        "After all movements, the robot must return to the default position `[90, 90, 90, 90, 90, 90, 90]` with a `wait` of `0.5` seconds. "
        "Always include at least the default position in the `movements` array. "
        "When greeting, make the robot raise its right arm to say hello. For example, a movement like `{\"command\": [90, 152, 90, 90, 90, 90, 90], \"wait\": 0.5}` (raise arm), then `{\"command\": [90, 152, 180, 86, 90, 90, 90], \"wait\": 4.0}` (hold arm), followed by returning to default. "
        "For expressive or descriptive speech, try to include more varied and frequent movements to make the robot appear lively. "
        "Example JSON response for a greeting: `{\"speech\": \"Salom! Men Ali. Sizga qanday yordam bera olaman?\", \"movements\": [{\"command\": [90, 152, 90, 90, 90, 90, 90], \"wait\": 0.5}, {\"command\": [90, 152, 180, 86, 90, 90, 90], \"wait\": 4.0}, {\"command\": [90, 90, 90, 90, 90, 90, 90], \"wait\": 0.5}]}`"
    )


SALOMLASHISH = [
    "salom",
    "assalomu alaykum",
    "salom alaykum",
    "vaalaykum",
    "hayrli kun",
    "hayrli tong",
    "hayrli kech",
    "salom aleykum",
    "assalom",
]

XAYRLASHISH = [
    "xayr",
    "hayr",
    "ko'rishguncha",
    "xayrlashaman",
    "salomat bo'ling",
    "boraman",
    "ketaman",
    "hayrlashish",
]

YORDAM = [
    "yordam",
    "nima qila olasan",
    "nimalarni bilasan",
    "qanday savollar",
    "help",
    "buyruqlar",
]

TAYYOR_JAVOBLAR = {
    "salom": "Salom! Yaxshimisiz? Bugun kayfiyatingiz qanday?",
    "xayr": "Mayli, ko'rishguncha. O'zingizni ehtiyot qiling.",
    "yordam": "Albatta, qanday yordam bera olaman?",
}

FALLBACK_API_ERROR = "Internet yoki API bilan bog'lanishda muammo bo'ldi."
FALLBACK_TTS_ERROR = "Kechirasiz, ovoz chiqarishda muammo bo'ldi."
FALLBACK_TEXT_ONLY = "Mayli, hozircha javobni matn ko'rinishida ko'rsataman."
FALLBACK_STT_ERROR = "Bir oz tushunmadim, qaytadan aytib bera olasizmi?"

conversation_history = []
MAX_HISTORY = 12
_mixer_initialized = False


def add_to_history(role, content):
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > MAX_HISTORY * 2:
        conversation_history[:] = conversation_history[-(MAX_HISTORY * 2):]


def sanitize_text_for_tts(text):
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[*_#>\[\]\(\)]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[{}\[\]<>]", " ", text)
    text = re.sub(r"[^\w\s.,!?;:'\-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_long_speech_into_chunks(text, limit=280):
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks or [text[:limit]]


def prepare_uzbek_spoken_text(text):
    text = (
        text.replace("â€”", "-")
        .replace("â€“", "-")
        .replace("’", "'")
        .replace("`", "'")
    )
    text = sanitize_text_for_tts(text)
    text = re.sub(r"\s*-\s*", ", ", text)
    text = re.sub(r"([!?.,])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_optimal_microphone():
    print("[TIZIM] Mikrofonlar tekshirilmoqda...")
    pa = pyaudio.PyAudio()

    preferred_keywords = [
        "usb",
        "webcam",
        "headset",
        "bluetooth",
        "mic",
        "microphone",
        "audio",
    ]
    ignore_keywords = ["stereo mix", "loopback", "monitor", "virtual", "output"]

    try:
        default_info = pa.get_default_input_device_info()
        default_idx = int(default_info["index"])
    except Exception:
        default_info = None
        default_idx = None

    input_devices = []
    for idx in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(idx)
        if info.get("maxInputChannels", 0) <= 0:
            continue
        input_devices.append(info)

    best_device = None
    best_score = -1

    for info in input_devices:
        name = str(info.get("name", "")).lower()
        if any(word in name for word in ignore_keywords):
            continue

        score = 0
        if any(word in name for word in preferred_keywords):
            score += 3
        if default_idx is not None and int(info["index"]) != default_idx:
            score += 2
        if info.get("maxInputChannels", 0) >= 1:
            score += 1
        if info.get("defaultSampleRate", 0) >= 16000:
            score += 1

        if score > best_score:
            best_score = score
            best_device = info

    if best_device is not None:
        chosen_idx = int(best_device["index"])
        chosen_name = best_device["name"]
        chosen_rate = int(best_device.get("defaultSampleRate", 16000))
        source_type = "Tashqi" if chosen_idx != default_idx else "Standart"
        print(f"[TIZIM] {source_type} mikrofon tanlandi: {chosen_name} (ID:{chosen_idx})")
        pa.terminate()
        return chosen_idx, chosen_rate

    if default_info is not None:
        chosen_idx = int(default_info["index"])
        chosen_rate = int(default_info.get("defaultSampleRate", 16000))
        print(f"[TIZIM] Standart mikrofon tanlandi: {default_info['name']} (ID:{chosen_idx})")
        pa.terminate()
        return chosen_idx, chosen_rate

    pa.terminate()
    print("[TIZIM] Mikrofon topilmadi. Tizim default qurilmasi ishlatiladi.")
    return None, None


def create_microphone(device_index):
    if device_index is None:
        return sr.Microphone()
    return sr.Microphone(device_index=device_index)


def listen(recognizer, mic):
    with mic as source:
        print("\n[INPUT] Gapiring...")
        recognizer.adjust_for_ambient_noise(source, duration=0.8)

        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            print("[STT] Matn aniqlanmoqda...")
            text = recognizer.recognize_google(audio, language=STT_LANGUAGE)
            print(f"[SIZ] {text}")
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            print(f"[AI] {FALLBACK_STT_ERROR}")
            return None
        except Exception as exc:
            print(f"[XATO] Mikrofon xatosi: {exc}")
            return None


async def think(text):  # robot_controller argumentini olib tashladim, chunki u endi harakatlarni bajarmaydi
    print("[AI] Javob tayyorlanmoqda...")
    text_lower = text.lower().strip()

    # Tayyor javoblar uchun ham JSON formatini qaytarish kerak
    if any(soz in text_lower for soz in SALOMLASHISH):
        speech_text = TAYYOR_JAVOBLAR["salom"]
        # Salomlashish harakati: 0.5s qo'l ko'tarish, 4.0s ushlab turish, 0.5s defaultga qaytish
        movements = [
            {"command": [90, 152, 90, 90, 90, 90, 90], "wait": 0.5},
            {"command": [90, 152, 180, 86, 90, 90, 90], "wait": 4.0},
            {"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}
        ]
        response_data = {"speech": speech_text, "movements": movements}
        print(f"[AI] {speech_text}")
        return response_data

    if any(soz in text_lower for soz in XAYRLASHISH):
        speech_text = TAYYOR_JAVOBLAR["xayr"]
        response_data = {"speech": speech_text, "movements": [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]}
        print(f"[AI] {speech_text}")
        return response_data

    if any(soz in text_lower for soz in YORDAM):
        speech_text = TAYYOR_JAVOBLAR["yordam"]
        response_data = {"speech": speech_text, "movements": [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]}
        print(f"[AI] {speech_text}")
        return response_data

    try:
        messages = [{"role": "system", "content": build_gemini_persona_prompt()}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": text})

        last_error = None
        response = None
        for model_name in GEMINI_TEXT_FALLBACK_MODELS:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=220,
                    top_p=0.9,
                    frequency_penalty=0.15,
                    presence_penalty=0.1,
                    response_format={"type": "json_object"}  # JSON formatini so'raymiz
                )
                break
            except Exception as model_error:
                last_error = model_error
                continue

        if response is None:
            raise last_error

        raw_ai_response_content = (response.choices[0].message.content or "").strip()

        # JSON obyektini matndan ajratib olish uchun regexdan foydalanamiz
        json_match = re.search(r"\{.*\}", raw_ai_response_content, re.DOTALL)

        ai_response_data = None
        if json_match:
            json_string = json_match.group(0)
            try:
                ai_response_data = json.loads(json_string)
            except json.JSONDecodeError:
                print(f"[XATO] AI dan noto'g'ri JSON formati (regexdan keyin): {json_string}")

        if ai_response_data is None:
            print(f"[XATO] AI dan JSON javobi topilmadi yoki noto'g'ri: {raw_ai_response_content}")
            speech_text = FALLBACK_API_ERROR
            movements = [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]
        else:
            speech_text = ai_response_data.get("speech", FALLBACK_API_ERROR)
            movements = ai_response_data.get("movements", [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}])

        if not speech_text:
            speech_text = FALLBACK_API_ERROR

        add_to_history("user", text)
        add_to_history("assistant", speech_text)  # Faqat speech qismini historyga qo'shamiz

        print(f"[AI] {speech_text}")

        # think funksiyasi endi harakatlarni bajarmaydi, faqat ma'lumotni qaytaradi
        return {"speech": speech_text, "movements": movements}

    except Exception as exc:
        print(f"[XATO] API xatosi: {exc}")
        return {"speech": FALLBACK_API_ERROR, "movements": [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]}


def _ensure_mixer():
    global _mixer_initialized
    if not _mixer_initialized:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        _mixer_initialized = True


async def _generate_edge_audio_bytes(uzbek_text):
    communicate = edge_tts.Communicate(
        text=uzbek_text,
        voice=EDGE_TTS_VOICE,
        rate=EDGE_TTS_RATE,
        pitch=EDGE_TTS_PITCH,
        volume=EDGE_TTS_VOLUME,
    )
    audio_chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.extend(chunk["data"])
    if audio_chunks:
        return bytes(audio_chunks)
    raise RuntimeError("Edge TTS dan audio olinmadi.")


def _play_mp3_bytes(audio_bytes):
    _ensure_mixer()
    audio_stream = io.BytesIO(audio_bytes)
    pygame.mixer.music.load(audio_stream, "mp3")
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(20)
    pygame.mixer.music.stop()


async def speak(text):
    print("[TTS] Ovoz chiqarilmoqda...")
    clean_text = prepare_uzbek_spoken_text(text)
    if not clean_text:
        return

    chunks = split_long_speech_into_chunks(clean_text)

    try:
        for part in chunks:
            audio_bytes = await _generate_edge_audio_bytes(part)
            if audio_bytes:
                _play_mp3_bytes(audio_bytes)
    except Exception as exc:
        print(f"[XATO] {FALLBACK_TTS_ERROR}: {exc}")
        print(f"[AI] {FALLBACK_TEXT_ONLY}")


async def main():  # main funksiyasini async qildim
    print("\nSUHBAT AI Raspberry Pi versiyasi ishga tushdi.")

    if not OPENROUTER_API_KEY:
        print("[XATO] OPENROUTER_API_KEY topilmadi.")
        print("[INFO] Muhit o'zgaruvchisiga API kalitini kiriting.")
        return

    print("[SYSTEM] API tekshirilmoqda...")
    try:
        ping_ok = False
        for model_name in GEMINI_TEXT_FALLBACK_MODELS:
            try:
                client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "Faqat o'zbekcha: salom de."},
                        {"role": "user", "content": "test"},
                    ],
                    max_tokens=8,
                )
                ping_ok = True
                break
            except Exception:
                continue

        if not ping_ok:
            raise RuntimeError("Gemini chat model topilmadi yoki noto'g'ri model tanlangan.")
        print("[OK] API ulanib turibdi.")
    except Exception as exc:
        print(f"[XATO] API ulanmadi: {exc}")
        print("[INFO] OPENROUTER_API_KEY, internet va GEMINI_TEXT_MODEL ni tekshiring.")
        return

    mic_idx, _mic_rate = get_optimal_microphone()
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.0
    recognizer.non_speaking_duration = 0.5

    try:
        mic = create_microphone(mic_idx)
    except Exception as exc:
        print(f"[XATO] Mikrofon ishga tushmadi: {exc}")
        return

    # RobotController obyektini yaratamiz
    robot_controller = RobotController()
    if not robot_controller.ser or not robot_controller.ser.is_open:
        print("[XATO] Robotga ulanib bo'lmadi. Dastur robot harakatlarisiz ishlaydi.")
        robot_controller = None
    else:
        # Robotga ulanish muvaffaqiyatli bo'lsa, boshlang'ich harakatlarni bajaramiz
        print("[ROBOT] Boshlang'ich harakatlar bajarilmoqda...")
        initial_movements = [
            {"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5},  # Default holat
            {"command": [90, 90, 90, 0, 90, 90, 90], "wait": 0.5},  # O'ng bilakni burish
            {"command": [90, 90, 90, 180, 90, 90, 90], "wait": 0.5},  # O'ng bilakni boshqa tomonga burish
            {"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5},  # Default holatga qaytarish
            {"command": [90, 90, 90, 90, 90, 90, 0], "wait": 0.5},  # Chap bilakni burish
            {"command": [90, 90, 90, 90, 90, 90, 180], "wait": 0.5},  # Chap bilakni boshqa tomonga burish
            {"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5},  # Default holatga qaytarish
        ]
        if robot_controller:  # robot_controller None bo'lmasa
            await robot_controller.execute_movements(initial_movements)  # await qo'shildi
        print("[ROBOT] Boshlang'ich harakatlar yakunlandi.")

    print("[READY] Raspberry Pi suhbatga tayyor. Ctrl+C bilan chiqasiz.\n")
    print(
        f"[TTS] Ovoz: {EDGE_TTS_VOICE} | rate={EDGE_TTS_RATE}, "
        f"pitch={EDGE_TTS_PITCH}, volume={EDGE_TTS_VOLUME}"
    )

    initial_greeting = os.getenv("GREETING_TEXT", "Assalomu alaykum! Tanishsak bo'ladimi? Ismingiz nima?")

    # GREETING_TEXT bilan birga robot harakatlarini parallel bajarish
    greeting_movements = [
        {"command": [90, 152, 90, 90, 90, 90, 90], "wait": 0.5},  # 0.5s qo'lni ko'tarish
        {"command": [90, 152, 180, 86, 90, 90, 90], "wait": 4.0},  # 4.0s qo'lni ushlab turish
        {"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}  # 0.5s default holatga qaytish
    ]

    if robot_controller:
        await asyncio.gather(
            speak(initial_greeting),
            robot_controller.execute_movements(greeting_movements)
        )
    else:
        await speak(initial_greeting)

    while True:
        try:
            user_text = listen(recognizer, mic)
            if not user_text:
                continue

            text_lower = user_text.lower().strip()
            is_goodbye = any(soz in text_lower for soz in XAYRLASHISH)

            # think funksiyasiga robot_controller obyektini uzatmaymiz, chunki u endi harakatlarni bajarmaydi
            ai_response_parsed = await think(user_text)  # await qo'shildi

            # Faqat speech qismini speak funksiyasiga uzatamiz
            # Harakatlar va ovozni parallel bajarish
            speech_task = speak(ai_response_parsed["speech"])
            movement_task = None
            if robot_controller:
                movement_task = robot_controller.execute_movements(ai_response_parsed["movements"])

            if movement_task:
                await asyncio.gather(speech_task, movement_task)
            else:
                await speech_task

            if is_goodbye:
                print("\n[STOP] Dastur to'xtatildi.")
                break

            await asyncio.sleep(0.3)  # time.sleep o'rniga asyncio.sleep dan foydalandim

        except KeyboardInterrupt:
            farewell = "Tanishganimdan xursandman. Suhbat uchun rahmat."
            print(f"[AI] {farewell}")
            await speak(farewell)  # await qo'shildi
            print("[STOP] Dastur to'xtatildi.")
            break
        except Exception as exc:
            print(f"\n[XATO] Kutilmagan xato: {exc}")
            await asyncio.sleep(2)  # await qo'shildi


if __name__ == "__main__":
    asyncio.run(main())  # main funksiyasini asyncio.run bilan ishga tushirdim