#!/bin/bash
# Speech-to-Text Interactive Installation Script
# For Ubuntu/Debian systems

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VENV_PATH="$HOME/speech-env"
CONFIG_DIR="$HOME/.config/speech-to-text"
CONFIG_FILE="$CONFIG_DIR/config.toml"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/speech-to-text.service"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper functions
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Do not run this script as root or with sudo."
    print_error "The script will ask for sudo when needed."
    exit 1
fi

# Show help if requested
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Speech-to-Text Interactive Installer"
    echo ""
    echo "This script will:"
    echo "  - Install system dependencies (alsa-utils, wl-clipboard, xclip, python3, etc.)"
    echo "  - Create Python virtual environment at ~/speech-env"
    echo "  - Install Python packages (faster-whisper, evdev, etc.)"
    echo "  - Add user to 'input' group for keyboard/uinput access"
    echo "  - Copy configuration and systemd service files"
    echo "  - Configure clipboard mode for mixed Latin/Cyrillic text support"
    echo ""
    echo "Usage: ./install.sh"
    echo ""
    echo "After installation, you must logout and login for group changes to take effect."
    exit 0
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   Speech-to-Text Installation (Ubuntu/Debian)            ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Check for Ubuntu/Debian
print_step "Checking system compatibility"
if [ ! -f /etc/debian_version ]; then
    print_warning "This script is designed for Ubuntu/Debian systems."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
print_success "System check passed"

# Check for sudo access
print_step "Checking sudo access"
if ! sudo -v; then
    print_error "This script requires sudo access for system dependencies."
    exit 1
fi
print_success "Sudo access confirmed"

# Check minimum requirements
print_step "Checking system requirements"
TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
AVAILABLE_DISK=$(df -BG "$HOME" | awk 'NR==2 {print $4}' | sed 's/G//')

if [ "$TOTAL_MEM" -lt 2 ]; then
    print_warning "System has less than 2GB RAM. Whisper 'small' model may be slow."
fi

if [ "$AVAILABLE_DISK" -lt 2 ]; then
    print_error "Insufficient disk space. Need at least 2GB free."
    exit 1
fi
print_success "Requirements met (RAM: ${TOTAL_MEM}GB, Disk: ${AVAILABLE_DISK}GB available)"

# Install system dependencies
print_step "Installing system dependencies"
PACKAGES="alsa-utils wl-clipboard xclip python3 python3-venv python3-pip"
MISSING_PACKAGES=""

for pkg in $PACKAGES; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
    fi
done

if [ -n "$MISSING_PACKAGES" ]; then
    print_step "Installing:$MISSING_PACKAGES"
    sudo apt update
    sudo apt install -y $MISSING_PACKAGES
    print_success "System packages installed"
else
    print_success "All system packages already installed"
fi

# Add user to input group
print_step "Configuring user permissions"
if groups | grep -q '\binput\b'; then
    print_success "User already in 'input' group"
else
    sudo usermod -aG input "$USER"
    print_success "User added to 'input' group"
fi

# Create Python virtual environment
print_step "Setting up Python environment"
if [ -d "$VENV_PATH" ]; then
    print_success "Virtual environment already exists at $VENV_PATH"
else
    python3 -m venv "$VENV_PATH"
    print_success "Created virtual environment at $VENV_PATH"
fi

# Install Python packages
print_step "Installing Python packages"
source "$VENV_PATH/bin/activate"

# Check if packages are already installed
PIP_PACKAGES="faster-whisper evdev numpy soundfile"
NEEDS_INSTALL=false

for pkg in $PIP_PACKAGES; do
    if ! pip show "$pkg" &>/dev/null; then
        NEEDS_INSTALL=true
        break
    fi
done

if [ "$NEEDS_INSTALL" = true ]; then
    pip install --upgrade pip
    pip install $PIP_PACKAGES
    print_success "Python packages installed"
else
    print_success "Python packages already installed"
fi

# Ask user for model size
echo ""
print_step "Select Whisper model size"
echo ""
echo "  1) tiny   [39 MB,  fastest, lower accuracy]"
echo "  2) base   [140 MB, fast, good accuracy]"
echo "  3) small  [460 MB, recommended for multilingual] (RECOMMENDED)"
echo "  4) medium [1.5 GB, slow, high accuracy]"
echo "  5) large  [3+ GB,  slowest, best accuracy]"
echo ""
read -p "Choice [3]: " MODEL_CHOICE

case "$MODEL_CHOICE" in
    1) MODEL="tiny" ;;
    2) MODEL="base" ;;
    4) MODEL="medium" ;;
    5) MODEL="large" ;;
    *) MODEL="small" ;;  # Default
esac

print_success "Selected model: $MODEL"

# Create configuration
print_step "Setting up configuration"
mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ]; then
    print_warning "Configuration already exists at $CONFIG_FILE"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_success "Keeping existing configuration"
    else
        cp "$PROJECT_DIR/config.example.toml" "$CONFIG_FILE"
        # Update model
        sed -i "s/^model = .*/model = \"$MODEL\"/" "$CONFIG_FILE"
        # Enable clipboard mode
        sed -i "s/^mode = .*/mode = \"clipboard\"/" "$CONFIG_FILE"
        print_success "Configuration updated"
    fi
else
    cp "$PROJECT_DIR/config.example.toml" "$CONFIG_FILE"
    # Update model
    sed -i "s/^model = .*/model = \"$MODEL\"/" "$CONFIG_FILE"
    # Enable clipboard mode
    sed -i "s/^mode = .*/mode = \"clipboard\"/" "$CONFIG_FILE"
    print_success "Configuration created at $CONFIG_FILE"
fi

# Install systemd service
print_step "Installing systemd service"
mkdir -p "$SERVICE_DIR"

if [ -f "$SERVICE_FILE" ]; then
    print_warning "Service file already exists at $SERVICE_FILE"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_success "Keeping existing service file"
    else
        cp "$PROJECT_DIR/systemd/speech-to-text.service" "$SERVICE_FILE"
        # Update paths to use current user and project directory
        sed -i "s|/home/dev|$HOME|g" "$SERVICE_FILE"
        sed -i "s|/home/dev/speech-to-text|$PROJECT_DIR|g" "$SERVICE_FILE"
        systemctl --user daemon-reload
        print_success "Service file updated"
    fi
else
    cp "$PROJECT_DIR/systemd/speech-to-text.service" "$SERVICE_FILE"
    # Update paths to use current user and project directory
    sed -i "s|/home/dev|$HOME|g" "$SERVICE_FILE"
    sed -i "s|/home/dev/speech-to-text|$PROJECT_DIR|g" "$SERVICE_FILE"
    systemctl --user daemon-reload
    print_success "Service file installed"
fi

# Enable service (but don't start - user needs to logout/login)
print_step "Enabling systemd service"
if systemctl --user is-enabled speech-to-text &>/dev/null; then
    print_success "Service already enabled"
else
    systemctl --user enable speech-to-text
    print_success "Service enabled (will start on next login)"
fi

# Final summary
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║               Installation Complete!                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
print_success "Speech-to-Text installed successfully!"
echo ""
print_warning "IMPORTANT: You must logout and login again for the 'input' group membership to take effect."
echo ""
echo "After logout/login:"
echo "  - Service will start automatically"
echo "  - Hold Right Ctrl to record speech"
echo "  - First use will download the Whisper model (~$(
    case "$MODEL" in
        tiny) echo "39MB" ;;
        base) echo "140MB" ;;
        small) echo "460MB" ;;
        medium) echo "1.5GB" ;;
        large) echo "3GB+" ;;
    esac
) for '$MODEL')"
echo ""
echo "Useful commands:"
echo "  Start service:    systemctl --user start speech-to-text"
echo "  Stop service:     systemctl --user stop speech-to-text"
echo "  View logs:        journalctl --user -u speech-to-text -f"
echo "  Run tests:        $PROJECT_DIR/run.sh --test"
echo "  Interactive mode: $PROJECT_DIR/run.sh"
echo ""
echo "Configuration: $CONFIG_FILE"
echo "Service file:  $SERVICE_FILE"
echo ""
print_success "Model: $MODEL (clipboard mode enabled for mixed Latin/Cyrillic text)"
echo ""
