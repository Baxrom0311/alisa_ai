#!/bin/bash
# Alisa AI Assistant - Raspberry Pi Installation Script

set -e

# Language configuration (default: uz for Uzbek as per PROJECT_BRIEF)
LANG=${LANG:-uz}

echo "🤖 Installing Alisa AI Assistant on Raspberry Pi..."
echo "🌐 Language: $LANG"

# Check if running on ARM64
if [ "$(uname -m)" != "aarch64" ]; then
    echo "⚠️  Warning: This script is designed for ARM64 (aarch64) architecture"
    echo "Current architecture: $(uname -m)"
fi

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install system dependencies
echo "🔧 Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    build-essential \
    portaudio19-dev \
    alsa-utils \
    ffmpeg

# Create alisa user if not exists
if ! id "alisa" &>/dev/null; then
    echo "👤 Creating alisa user..."
    sudo useradd -m -s /bin/bash alisa
    sudo usermod -a -G audio alisa
fi

# Install directory
INSTALL_DIR="/opt/alisa"
echo "📁 Setting up installation directory: $INSTALL_DIR"

# Copy project files
sudo mkdir -p $INSTALL_DIR
sudo cp -r . $INSTALL_DIR/
sudo chown -R alisa:alisa $INSTALL_DIR

# Create Python virtual environment
echo "🐍 Setting up Python virtual environment..."
sudo -u alisa python3 -m venv $INSTALL_DIR/venv
sudo -u alisa $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt

# Install Ollama
echo "🧠 Installing Ollama..."
curl -fsSL https://ollama.ai/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama

# Wait for Ollama to start
sleep 5

# Pull default model (qwen2.5:3b as specified in PROJECT_BRIEF)
echo "📥 Downloading AI model (this may take a while)..."
sudo -u alisa ollama pull qwen2.5:3b

# Install whisper.cpp
echo "🎤 Installing whisper.cpp..."
cd /tmp
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
make -j$(nproc)
sudo cp main /usr/local/bin/whisper-cli
sudo cp models/download-ggml-model.sh /usr/local/bin/
cd /tmp && rm -rf whisper.cpp

# Download whisper model
echo "📥 Downloading speech recognition model..."
sudo -u alisa mkdir -p $INSTALL_DIR/models
cd $INSTALL_DIR/models
if [ "$LANG" = "uz" ]; then
    # Multilingual model for Uzbek support
    sudo -u alisa /usr/local/bin/download-ggml-model.sh base
else
    # English-only model (default)
    sudo -u alisa /usr/local/bin/download-ggml-model.sh base.en
fi

# Install Piper TTS
echo "🗣️  Installing Piper TTS..."
cd /tmp
wget https://github.com/rhasspy/piper/releases/latest/download/piper_arm64.tar.gz
tar -xzf piper_arm64.tar.gz
sudo cp piper/piper /usr/local/bin/
sudo mkdir -p /usr/local/share/piper
sudo cp -r piper/* /usr/local/share/piper/
rm -rf piper piper_arm64.tar.gz

# Download Piper voice model (matching config default)
echo "📥 Downloading text-to-speech voice..."
cd $INSTALL_DIR/models
if [ "$LANG" = "uz" ]; then
    echo "⚠️  Uzbek Piper voice not available in default repository."
    echo "Installing Russian voice as phonetic fallback..."
    echo ""
    echo "📋 To install a proper Uzbek voice later:"
    echo "1. Download a compatible .onnx + .json voice model to /opt/alisa/models/"
    echo "2. Update config.yaml piper.model path to point to your voice"
    echo "3. Restart Alisa service: sudo systemctl restart alisa"
    echo ""
    
    # Download Russian voice as fallback (phonetically closer to Uzbek)
    sudo -u alisa wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx
    sudo -u alisa wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json
    echo "✅ Russian voice installed as temporary fallback"
else
    # English voice (default)
    sudo -u alisa wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx
    sudo -u alisa wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
fi

# Copy config if it doesn't exist
echo "⚙️  Setting up configuration..."
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    sudo -u alisa cp $INSTALL_DIR/config.yaml.example $INSTALL_DIR/config.yaml
    echo "✅ Created config.yaml from example"
else
    echo "ℹ️  config.yaml already exists, keeping current configuration"
fi

# Create logs directory with tmpfs optimization
sudo -u alisa mkdir -p $INSTALL_DIR/logs

# Optimize for SD card longevity
echo "💾 Optimizing for SD card longevity..."

# Create tmpfs mount for logs to reduce SD card writes
sudo tee -a /etc/fstab > /dev/null << EOF
# Alisa AI Assistant - tmpfs for logs to reduce SD card wear
tmpfs /opt/alisa/logs tmpfs defaults,noatime,nosuid,nodev,noexec,mode=0755,size=100M,uid=alisa,gid=alisa 0 0
EOF

# Mount the tmpfs
sudo mount /opt/alisa/logs

# Configure log rotation for any persistent logs
sudo tee /etc/logrotate.d/alisa > /dev/null << EOF
/opt/alisa/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 alisa alisa
    postrotate
        systemctl reload alisa || true
    endscript
}
EOF

# Create environment file for secrets
echo "🔐 Creating environment file..."
sudo mkdir -p /etc/alisa
sudo chown root:alisa /etc/alisa
sudo chmod 750 /etc/alisa
sudo tee /etc/alisa/environment > /dev/null << EOF
# Alisa AI Assistant Environment Variables
# Uncomment and set these for Telegram bot functionality:
# TELEGRAM_BOT_TOKEN=your_bot_token_here
# TELEGRAM_CHAT_ID=your_chat_id_here
EOF
sudo chmod 640 /etc/alisa/environment

# Install systemd service
echo "🔧 Installing systemd service..."
sudo cp $INSTALL_DIR/setup/systemd/alisa.service /etc/systemd/system/

# Install sudoers file for service restart
echo "🔐 Installing sudoers configuration..."
if sudo visudo -cf $INSTALL_DIR/setup/sudoers.d/alisa; then
    sudo cp $INSTALL_DIR/setup/sudoers.d/alisa /etc/sudoers.d/alisa
    sudo chmod 0440 /etc/sudoers.d/alisa
    echo "✅ Sudoers configuration installed"
else
    echo "❌ Sudoers configuration validation failed"
    exit 1
fi

sudo systemctl daemon-reload
sudo systemctl enable alisa

echo "✅ Installation complete!"
echo ""

# Run deployment verification
echo "🧪 Running deployment verification..."
cd /opt/alisa
if python3 setup/verify_deployment.py; then
    echo "✅ Deployment verification passed!"
else
    echo "⚠️  Deployment verification had warnings - check output above"
fi

echo ""
echo "Next steps:"
echo "1. Configure Telegram bot (optional):"
echo "   sudo nano /etc/alisa/environment"
echo "2. Start Alisa service:"
echo "   sudo systemctl start alisa"
echo "3. Check status:"
echo "   sudo systemctl status alisa"
echo "4. View logs:"
echo "   sudo journalctl -u alisa -f"
echo ""
echo "🎉 Alisa AI Assistant is ready!"
