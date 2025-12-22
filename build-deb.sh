#!/bin/bash
# Build Debian package for speech-to-text

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PACKAGE_NAME="speech-to-text"
VERSION="1.0"
ARCH="amd64"
BUILD_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BUILD_DIR="debian/${PACKAGE_NAME}"
DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper functions
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Show help if requested
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Speech-to-Text Debian Package Builder"
    echo ""
    echo "This script builds a .deb package for distribution."
    echo ""
    echo "Usage: ./build-deb.sh"
    echo ""
    echo "Output: ${DEB_FILE}"
    exit 0
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║        Building Speech-to-Text Debian Package           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Clean up previous build
if [ -d "$BUILD_DIR" ]; then
    print_step "Cleaning previous build"
    rm -rf "$BUILD_DIR"
    print_success "Cleanup complete"
fi

# Create directory structure
print_step "Creating package structure"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/opt/speech-to-text"
mkdir -p "${BUILD_DIR}/usr/lib/systemd/user"
mkdir -p "${BUILD_DIR}/etc/speech-to-text"

# Copy application files
print_step "Copying application files"
cp -r "$PROJECT_DIR/src" "${BUILD_DIR}/opt/speech-to-text/"
cp "$PROJECT_DIR/run.sh" "${BUILD_DIR}/opt/speech-to-text/"
cp "$PROJECT_DIR/config.example.toml" "${BUILD_DIR}/opt/speech-to-text/"
cp "$PROJECT_DIR/README.md" "${BUILD_DIR}/opt/speech-to-text/"
cp "$PROJECT_DIR/CHANGELOG.md" "${BUILD_DIR}/opt/speech-to-text/" 2>/dev/null || true

# Create build info file
cat > "${BUILD_DIR}/opt/speech-to-text/BUILD_INFO" << EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Architecture: ${ARCH}
Built: ${BUILD_TIMESTAMP}
Built-By: $(whoami)@$(hostname)
Git-Commit: $(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
EOF

print_success "Application files copied"

# Copy systemd service
print_step "Copying systemd service"
cp "$PROJECT_DIR/systemd/speech-to-text.service" "${BUILD_DIR}/usr/lib/systemd/user/"
print_success "Service file copied"

# Copy default config
print_step "Creating default configuration"
cp "$PROJECT_DIR/config.example.toml" "${BUILD_DIR}/etc/speech-to-text/config.toml.default"
print_success "Default configuration created"

# Create control file
print_step "Creating package metadata"
cat > "${BUILD_DIR}/DEBIAN/control" << EOF
Package: speech-to-text
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: alsa-utils, python3 (>= 3.10)
Suggests: python3-venv, python3-pip, wl-clipboard, xclip
Maintainer: Speech-to-Text Project <noreply@example.com>
Description: Offline speech-to-text dictation for Ubuntu
 Hold-to-talk offline speech recognition using Faster Whisper.
 Works on both X11 and Wayland with support for multilingual dictation.
 .
 Build: ${BUILD_TIMESTAMP}
 Git: $(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
 .
 Features:
  - Offline transcription using Whisper models
  - Multi-language support (Ukrainian, English, 99+ languages)
  - Mixed-script text support (clipboard mode)
  - Works on X11 and Wayland (requires wl-clipboard for Wayland, xclip for X11)
  - Systemd user service integration
  - Configurable hotkeys and audio feedback
 .
 Recommended packages:
  - wl-clipboard: Required for clipboard mode on Wayland
  - xclip: Required for clipboard mode on X11
EOF
print_success "Control file created"

# Copy postinst script
print_step "Copying post-installation script"
if [ ! -f "$PROJECT_DIR/debian/postinst" ]; then
    print_error "debian/postinst not found. Please create it first."
    exit 1
fi
cp "$PROJECT_DIR/debian/postinst" "${BUILD_DIR}/DEBIAN/"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"
print_success "Post-installation script copied"

# Copy prerm script
print_step "Copying pre-removal script"
if [ ! -f "$PROJECT_DIR/debian/prerm" ]; then
    print_error "debian/prerm not found. Please create it first."
    exit 1
fi
cp "$PROJECT_DIR/debian/prerm" "${BUILD_DIR}/DEBIAN/"
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"
print_success "Pre-removal script copied"

# Set permissions
print_step "Setting file permissions"
chmod 755 "${BUILD_DIR}/opt/speech-to-text/run.sh"
chmod 644 "${BUILD_DIR}/usr/lib/systemd/user/speech-to-text.service"
chmod 644 "${BUILD_DIR}/etc/speech-to-text/config.toml.default"
find "${BUILD_DIR}/opt/speech-to-text/src" -type f -name "*.py" -exec chmod 644 {} \;
print_success "Permissions set"

# Build the package
print_step "Building .deb package"
dpkg-deb --build "$BUILD_DIR" "$DEB_FILE"
print_success "Package built successfully"

# Show package info
print_step "Package information"
dpkg-deb --info "$DEB_FILE"

# Cleanup
print_step "Cleaning up build directory"
rm -rf "$BUILD_DIR"
print_success "Cleanup complete"

# Final summary
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              Package Build Complete!                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
print_success "Debian package created: $DEB_FILE"
echo ""
echo "Build Information:"
echo "  Version: $VERSION"
echo "  Built: $BUILD_TIMESTAMP"
echo "  Git Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "  Package size: $(du -h "$DEB_FILE" | cut -f1)"
echo ""
echo "To install:"
echo "  sudo apt install ./$DEB_FILE"
echo ""
echo "To verify before copying:"
echo "  dpkg-deb --info $DEB_FILE | grep Build"
echo ""
echo "To inspect:"
echo "  dpkg-deb --contents $DEB_FILE"
echo "  dpkg-deb --info $DEB_FILE"
echo ""
