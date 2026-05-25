#!/usr/bin/env python3
"""Custom 'Alisa' wake word model training script for openWakeWord.

Bu skript openWakeWord uchun custom "Alisa" wake word modelini train qiladi.
Natija: ~200KB ONNX model fayl.

Talablar:
- openwakeword[train] o'rnatilgan bo'lishi kerak
- Piper TTS (sintetik audio generatsiya uchun)
- GPU tavsiya etiladi (lekin CPU da ham ishlaydi)

Ishlatish:
    python setup/train_wake_word.py --keyword alisa --output models/alisa_wake_word.onnx
"""

import argparse
import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Training uchun kerakli parametrlar
TRAINING_CONFIG = {
    "keyword": "alisa",
    # Turli talaffuz variantlari (shevalar uchun)
    "keyword_variants": [
        "alisa",
        "алиса",  # kirill
        "elisa",  # whisper xatosi
        "alissa",
    ],
    # Sintetik audio generatsiya parametrlari
    "n_samples": 3000,  # Nechta sintetik audio yaratish
    "n_negative_samples": 10000,  # Salbiy namunalar
    # Model parametrlari
    "n_epochs": 50,
    "batch_size": 64,
    "target_accuracy": 0.95,
    "target_false_positive_rate": 0.01,  # 1 false alarm per 100 attempts
}


def check_dependencies():
    """Kerakli kutubxonalar borligini tekshirish."""
    missing = []
    try:
        import openwakeword
    except ImportError:
        missing.append("openwakeword")
    
    try:
        import torch
    except ImportError:
        missing.append("torch")
    
    try:
        import torchaudio
    except ImportError:
        missing.append("torchaudio")
    
    if missing:
        print(f"❌ Quyidagi kutubxonalar topilmadi: {', '.join(missing)}")
        print(f"   O'rnatish: pip install {' '.join(missing)}")
        return False
    return True


def generate_synthetic_samples(keyword: str, output_dir: Path, n_samples: int):
    """Piper TTS yordamida sintetik audio namunalar yaratish."""
    print(f"🎤 '{keyword}' uchun {n_samples} ta sintetik audio yaratilmoqda...")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Turli tezlik va ohangda generatsiya
    speeds = [0.8, 0.9, 1.0, 1.1, 1.2]
    
    generated = 0
    for i in range(n_samples):
        speed = speeds[i % len(speeds)]
        output_file = output_dir / f"{keyword}_{i:05d}.wav"
        
        # Piper TTS bilan generatsiya (agar mavjud bo'lsa)
        try:
            cmd = [
                "piper",
                "--model", "/opt/alisa/models/uz_UZ-doniyorbek-medium.onnx",
                "--output_file", str(output_file),
                "--length_scale", str(1.0 / speed),
            ]
            result = subprocess.run(
                cmd, input=keyword, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                generated += 1
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Piper mavjud emas — espeak fallback
            try:
                cmd = [
                    "espeak-ng", "-v", "uz",
                    "-s", str(int(150 * speed)),
                    "-w", str(output_file),
                    keyword,
                ]
                subprocess.run(cmd, capture_output=True, timeout=5)
                generated += 1
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    
    print(f"   ✅ {generated} ta audio yaratildi")
    return generated


def train_model(keyword: str, output_path: Path, config: dict):
    """openWakeWord modelini train qilish."""
    print(f"🧠 '{keyword}' wake word modeli train qilinmoqda...")
    print(f"   Epochs: {config['n_epochs']}, Batch: {config['batch_size']}")
    
    try:
        from openwakeword.train import train_model as oww_train
        
        # Training data papkasi
        data_dir = Path(tempfile.mkdtemp(prefix="alisa_ww_"))
        positive_dir = data_dir / "positive"
        negative_dir = data_dir / "negative"
        
        # Sintetik namunalar yaratish
        generate_synthetic_samples(keyword, positive_dir, config["n_samples"])
        
        # Model train qilish
        model_path = oww_train(
            keyword=keyword,
            positive_audio_dir=str(positive_dir),
            output_dir=str(output_path.parent),
            n_epochs=config["n_epochs"],
            batch_size=config["batch_size"],
        )
        
        print(f"   ✅ Model saqlandi: {model_path}")
        return model_path
        
    except ImportError:
        print("❌ openwakeword training moduli topilmadi")
        print("   O'rnatish: pip install openwakeword[train]")
        return None
    except Exception as e:
        print(f"❌ Training xatosi: {e}")
        print("\n💡 Alternativa: openWakeWord GitHub dan tayyor modellarni yuklab olish")
        print("   yoki https://github.com/dscripka/openWakeWord/blob/main/notebooks/training_models.ipynb")
        return None


def create_fallback_config(output_dir: Path):
    """Agar training ishlamasa, fallback konfiguratsiya yaratish."""
    config_content = """# Alisa Wake Word Configuration
# 
# Agar custom model train qilib bo'lmasa, quyidagi variantlardan foydalaning:
#
# 1. "alexa" modelini proxy sifatida ishlatish (fonetik o'xshashlik):
#    wake_word:
#      method: openwakeword
#      openwakeword:
#        model: alexa
#      allow_proxy_model: true
#
# 2. Energy-gated + STT confirmation (aniqroq, lekin sekinroq):
#    wake_word:
#      method: energy_gated
#      energy_gated:
#        threshold: 500
#
# 3. Custom model (eng yaxshi variant):
#    wake_word:
#      method: openwakeword
#      openwakeword:
#        model: /opt/alisa/models/alisa_wake_word.onnx
#
# Custom model train qilish uchun:
#   python setup/train_wake_word.py --keyword alisa
#
# Yoki Google Colab da:
#   https://github.com/dscripka/openWakeWord/blob/main/notebooks/training_models.ipynb
"""
    config_path = output_dir / "wake_word_config.md"
    config_path.write_text(config_content)
    print(f"📝 Konfiguratsiya yo'riqnomasi: {config_path}")


def main():
    parser = argparse.ArgumentParser(description="Train custom wake word model for Alisa")
    parser.add_argument("--keyword", default="alisa", help="Wake word keyword")
    parser.add_argument("--output", default="models/alisa_wake_word.onnx", help="Output model path")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--samples", type=int, default=3000, help="Number of synthetic samples")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Alisa Wake Word Model Training")
    print(f"  Keyword: '{args.keyword}'")
    print("=" * 60)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not check_dependencies():
        print("\n⚠️  Dependencies yo'q — fallback konfiguratsiya yaratilmoqda...")
        create_fallback_config(output_path.parent)
        sys.exit(1)

    config = TRAINING_CONFIG.copy()
    config["n_epochs"] = args.epochs
    config["n_samples"] = args.samples

    model_path = train_model(args.keyword, output_path, config)

    if model_path:
        print(f"\n✅ Tayyor! Model: {model_path}")
        print(f"   config.yaml ga qo'shing:")
        print(f"   wake_word:")
        print(f"     method: openwakeword")
        print(f"     openwakeword:")
        print(f"       model: {model_path}")
    else:
        create_fallback_config(output_path.parent)
        sys.exit(1)


if __name__ == "__main__":
    main()
