# Changelog

All notable changes to the Speech-to-Text project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-12-15

### Added
- **Hold-to-talk recording**: Hold Right Ctrl (configurable via evdev) to record audio
- **Local offline transcription**: Uses Faster Whisper models running on CPU with int8 optimization
- **Auto-typing**: Automatically types transcribed text into active application
- **Cross-display server support**: Works on both X11 (xdotool) and Wayland (wtype preferred, ydotool fallback)
- **Smart language detection**: Auto-detects keyboard layout (Ukrainian/English/etc.) at recording time
- **Systemd integration**: Runs as user service on login with proper environment variables
- **Audio feedback**: Configurable start/stop sounds via PulseAudio
- **State machine**: Robust state management (IDLE → RECORDING → TRANSCRIBING → TYPING → IDLE)
- **Component testing**: Built-in test suite for display server, audio, model, keyboard, and tools
- **Interactive CLI mode**: Menu-driven interface for manual recording and transcription
- **Command-line mode**: CLI support for scripting (`--record N --type`)
- **TOML configuration**: Settings management with sensible defaults
- **Daemon mode**: Background service with hotkey monitoring

### Technical Details
- **Python 3.10+** with virtual environment
- **Faster Whisper** for speech recognition with configurable models (tiny, base, small, medium, large)
- **ALSA** (arecord) for audio recording
- **python3-evdev** for keyboard monitoring
- **Text automation tools**: xdotool (X11), wtype (Wayland), ydotool (fallback)
- **GNOME integration**: Keyboard layout detection via gsettings

### Documentation
- Comprehensive README with quick start guide
- System check script for environment validation
- Installation guide with platform-specific instructions
- Configuration template with inline documentation

### Known Limitations
- ydotool has poor Unicode/Cyrillic support on Wayland - wtype preferred
- Multiline text detection not yet implemented
- Special character recognition requires post-processing
- Single Whisper model backend (alternative models planned for future release)

## [1.1.0] - 2025-12-19

### Added
- **Clipboard mode**: New text input mode using PRIMARY selection for mixed Latin/Cyrillic text
- **Configurable text input modes**: `[text_input]` config section with mode selection (uinput by default)
- **Language detection in CLI mode**: Fixed keyboard layout detection for `--record --type` command

### Fixed
- Language detection now works correctly in CLI mode (`--record --type`)
- Fixed config reference error in service.py (`config.typing` → `config.text_input`)
- Removed broken auto-layout switching logic

### Changed
- Text input configuration moved to dedicated `[text_input]` section in config.toml
- Removed Ukrainian-only language restrictions (now supports auto-detection)

---

## Planned Releases

### [1.2.0] - Enhanced Text Processing
- Multiline text recognition with paragraph detection
- Special character and file path post-processing
- Advanced clipboard integration options

### [2.0.0] - Alternative Models Support
- Pluggable model backend architecture
- Support for Parakeet TDT (faster inference)
- Support for Distil-Whisper (smaller footprint)
- Custom fine-tuned model support

### [2.1.0] - GNOME Integration
- Visual status indicator in GNOME top panel
- D-Bus notifications for recording state
- System tray integration

---

## Installation

See [README.md](README.md) for installation instructions and quick start guide.

## Contributing

Report issues and feature requests on GitHub.

## License

See LICENSE file for licensing information.
