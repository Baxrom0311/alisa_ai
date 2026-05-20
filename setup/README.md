# Alisa AI Assistant - Setup Guide

## Installation

Run the installation script on your Raspberry Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/your-repo/alisa/main/setup/install.sh | bash
```

Or clone the repository and run locally:

```bash
git clone https://github.com/your-repo/alisa.git
cd alisa
sudo ./setup/install.sh
```

## Language Configuration

The installer supports multiple languages via the `LANG` environment variable:

### Uzbek (Default)
```bash
sudo ./setup/install.sh
# or explicitly:
LANG=uz sudo ./setup/install.sh
```

This installs:
- Multilingual Whisper model (`ggml-base.bin`) for Uzbek speech recognition
- qwen2.5:3b LLM model (~2.2GB RAM usage on Pi 4 4GB)
- Russian TTS voice (`ru_RU-irina-medium.onnx`) as phonetic fallback

**Uzbek Voice Setup**: The installer uses a Russian voice as a temporary fallback since dedicated Uzbek Piper voices are not yet available. To install a proper Uzbek voice:
1. Download a compatible Piper voice model (.onnx + .json files) to `/opt/alisa/models/`
2. Update `config.yaml` to point `piper.model` to your voice file
3. Restart Alisa service: `sudo systemctl restart alisa`

### English
```bash
LANG=en sudo ./setup/install.sh
```

This installs:
- English-only Whisper model (`ggml-base.en.bin`)
- qwen2.5:3b LLM model (~2.2GB RAM usage on Pi 4 4GB)
- English TTS voice (`en_US-lessac-medium.onnx`)

## Post-Installation

1. **Verify Installation**:
   ```bash
   cd /opt/alisa
   sudo -u alisa ./setup/verify_deployment.py
   ```
   This comprehensive verification script checks:
   - **Brief acceptance tests** (deployment gate - must pass)
   - System requirements (ARM64, memory, disk space)
   - Dependencies (whisper.cpp, piper, ollama)
   - AI models (Whisper, Piper models)
   - Ollama service and model availability
   - Audio devices (microphone, speakers)
   - Voice pipeline (STT → LLM → TTS)
   - Telegram bot connectivity
   - Systemd service configuration

2. **Configure Telegram Bot** (optional):
   ```bash
   sudo nano /etc/alisa/environment
   ```
   Uncomment and set:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

3. **Start the service**:
   ```bash
   sudo systemctl start alisa
   sudo systemctl status alisa
   ```

4. **View logs**:
   ```bash
   sudo journalctl -u alisa -f
   ```

## System Requirements

- Raspberry Pi 4 (4GB RAM recommended) or Pi 5
- ARM64 (aarch64) architecture
- 64GB+ microSD card
- USB microphone
- Speaker (3.5mm jack or USB)

## Troubleshooting

### Check service status
```bash
sudo systemctl status alisa
```

### View detailed logs
```bash
sudo journalctl -u alisa -n 50
```

### Test components individually
```bash
# Test speech recognition
sudo -u alisa /opt/alisa/venv/bin/python -c "from alisa.voice.stt import transcribe; print('STT ready')"

# Test text-to-speech
sudo -u alisa /opt/alisa/venv/bin/python -c "from alisa.voice.tts import synthesize; print('TTS ready')"

# Test LLM
sudo -u alisa /opt/alisa/venv/bin/python -c "from alisa.brain.llm_manager import get_llm_manager; print('LLM ready')"
```

### Restart service
```bash
sudo systemctl restart alisa
```
