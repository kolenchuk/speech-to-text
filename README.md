# Speech-to-Text Application

Offline speech-to-text dictation system for Ubuntu 24.04 with hold-to-talk support.

## Features

- **Hold-to-talk recording** - Hold a configurable hotkey (keyboard or mouse button) to record, release to transcribe
- **Multi-device support** - Use both keyboard keys AND mouse buttons simultaneously as triggers
- **Per-key double-tap mode** - Different behavior for each trigger (e.g., double-tap keyboard, single-click mouse)
- **Offline transcription** - Uses Whisper model locally (no internet required)
- **Multi-language support** - Auto-detects language (Ukrainian, English, etc.)
- **Mixed-language dictation** - Handles "Він сказав hello world" perfectly with clipboard mode
- **Cross-display server** - Works on both X11 and Wayland
- **Dual text input modes** - uinput (fast) or clipboard (mixed-script friendly)
- **Auto-typing** - Automatically types transcribed text into active window
- **Background service** - Runs as systemd user service
- **Audio feedback** - Optional sounds for recording start/stop
- **CPU optimized** - Runs on CPU with int8 optimization
- **Privacy-focused** - Clipboard mode uses PRIMARY selection (doesn't pollute clipboard history)

## Quick Start

### Interactive Mode

```bash
./run.sh
```

Shows a menu with options:
1. Record and transcribe (5 seconds)
2. Record and transcribe (custom duration)
3. Record, transcribe, and TYPE to active window
4. Run component tests
5. Start daemon mode (hold-to-talk)

### Daemon Mode (Hold-to-Talk)

```bash
# Run in foreground
./run.sh --daemon

# Or start as background service
systemctl --user start speech-to-text
```

Hold the configured hotkey (default **Right Ctrl**) to record, release to transcribe and type.

**Note:** If you use Ctrl frequently (Ctrl+Insert, Ctrl+C, Ctrl+V), enable **double-tap mode** to avoid conflicts. See [Double-Tap Mode](#double-tap-mode) below.

### Command Line Mode

```bash
# Record for 5 seconds
./run.sh --record 5

# Record for 10 seconds and type result
./run.sh --record 10 --type

# Use a different model
./run.sh --model small --record 5

# Run tests
./run.sh --test
```

## Installation

### Prerequisites

**For both X11 and Wayland:**
```bash
# Install audio utilities and clipboard tools
sudo apt install alsa-utils python3-venv wl-clipboard

# Add user to input group (required for evdev and uinput)
sudo usermod -aG input $USER
# Logout and login for group changes to take effect
```

**Optional:**
- `paplay` (usually pre-installed with PulseAudio) - for audio feedback

### Python Environment

```bash
# Create virtual environment
python3 -m venv ~/speech-env

# Activate and install dependencies
source ~/speech-env/bin/activate
pip install faster-whisper numpy soundfile evdev
```

### Systemd Service (Optional)

```bash
# Copy service file
cp systemd/speech-to-text.service ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Start service
systemctl --user start speech-to-text

# Enable auto-start on login
systemctl --user enable speech-to-text

# View logs
journalctl --user -u speech-to-text -f
```

## Configuration

Copy the example configuration:

```bash
mkdir -p ~/.config/speech-to-text
cp config.example.toml ~/.config/speech-to-text/config.toml
```

Edit `~/.config/speech-to-text/config.toml`:

```toml
[model]
model = "base"              # tiny, base, small, medium, large
local_model_path = ""       # Path to local model dir to skip network (e.g., /home/you/models/asr-base)
download_if_missing = true  # Set to false to stay offline after first download
device = "cpu"              # cpu or cuda
compute_type = "int8"       # int8, float16, float32
language = ""               # Empty for auto-detect, or "en", "uk"

[hotkey]
# Single trigger (keyboard or mouse):
trigger_key = "KEY_RIGHTCTRL"              # Or "BTN_FORWARD", "BTN_BACK", etc.

# Multiple triggers (keyboard + mouse):
# trigger_key = "KEY_RIGHTCTRL, BTN_FORWARD"  # Both keyboard AND mouse

device_path = ""                           # Empty for auto-detect
double_tap_keys = ""                       # Keys requiring double-tap (e.g., "KEY_RIGHTCTRL")
enable_double_tap = false                  # Legacy: applies to all keys if double_tap_keys is empty
double_tap_timeout_ms = 300                # Max time between taps

[feedback]
enabled = true
start_sound = "/usr/share/sounds/freedesktop/stereo/message.oga"
stop_sound = "/usr/share/sounds/freedesktop/stereo/complete.oga"

[text_input]
# Text input mode: "uinput" or "clipboard"
mode = "uinput"                    # Use "clipboard" for mixed Latin/Cyrillic text
paste_key_combination = "shift+insert"  # For clipboard mode
key_delay_ms = 10                  # Delay between key events (uinput mode)
```

**To avoid any network access on startup**, download a model once into a local directory and set `local_model_path` to that folder (set `download_if_missing = false` if you want to keep it strictly offline after the initial download).

### Text Input Modes

**uinput mode (default):**
- Fast, direct keycode injection
- Works great for single-language dictation
- **Limitation:** Mixed Latin/Cyrillic text may be garbled (e.g., "hello" with Ukrainian layout → "ру|ддщ")

**clipboard mode (recommended for mixed languages):**
- Solves mixed-script problem completely
- "Він сказав hello world" types correctly regardless of keyboard layout
- Uses PRIMARY selection (Shift+Insert) - **doesn't pollute clipboard history**
- Your regular clipboard (Ctrl+C/V) remains untouched

**To enable clipboard mode:**
```toml
[text_input]
mode = "clipboard"
```

### Using Mouse Buttons

You can use mouse buttons as triggers, either alone or combined with keyboard keys.

**Common mouse button options:**
- `BTN_FORWARD` - Forward navigation button (side button)
- `BTN_BACK` - Back navigation button (side button)
- `BTN_SIDE` / `BTN_EXTRA` - Additional side buttons
- `BTN_MIDDLE` - Middle mouse button (scroll wheel click)

**Example 1: Mouse button only**
```toml
[hotkey]
trigger_key = "BTN_FORWARD"
```
Simple and convenient - just hold the button and speak!

**Example 2: Keyboard + Mouse (Recommended)**
```toml
[hotkey]
trigger_key = "KEY_RIGHTCTRL, BTN_FORWARD"  # Both keyboard AND mouse
double_tap_keys = "KEY_RIGHTCTRL"           # Only keyboard requires double-tap
```

This gives you the best of both worlds:
- **Mouse button:** Simple hold-to-talk (no double-tap needed)
- **Keyboard:** Double-tap to avoid conflicts with Ctrl shortcuts
- Use whichever is more convenient at the time!

**Finding your mouse button code:**

Run the included script to identify your mouse button:
```bash
source ~/speech-env/bin/activate
python3 find_mouse_button.py
```

Select your mouse, press the button you want to use, and note the code shown (e.g., `BTN_FORWARD`, `BTN_EXTRA`).

### Double-Tap Mode

**Problem:** If you use Ctrl shortcuts frequently (Ctrl+Insert, Ctrl+C, Ctrl+V, Ctrl+Arrow, etc.), a single Right Ctrl press/hold triggers dictation and prevents these shortcuts from working.

**Solution 1: Per-key double-tap (Recommended)**

Use double-tap for keyboard, single-tap for mouse:

```toml
[hotkey]
trigger_key = "KEY_RIGHTCTRL, BTN_FORWARD"
double_tap_keys = "KEY_RIGHTCTRL"    # Only keyboard requires double-tap
double_tap_timeout_ms = 300
```

**Solution 2: Double-tap for all keys**

```toml
[hotkey]
trigger_key = "KEY_RIGHTCTRL"
enable_double_tap = true        # Enable double-tap mode for all keys
double_tap_timeout_ms = 300     # 300ms window between taps
```

**How double-tap works:**
1. **Single tap** → Normal key behavior (Ctrl+Insert, Ctrl+C, etc. work normally)
2. **Double-tap quickly** → Arms the listener
3. **Hold on second tap** → Starts recording
4. **Release** → Transcribes and types

**Benefits:**
- ✅ Use Ctrl+Insert, Ctrl+C, Ctrl+V normally
- ✅ No conflicts with any Ctrl shortcuts
- ✅ Similar UX to macOS dictation (Fn double-tap)
- ✅ Works perfectly with vim Ctrl combinations

**Timing adjustment:**
- **Faster (200ms):** Harder to trigger, fewer accidental activations
- **Balanced (300ms):** Recommended default
- **Slower (400ms):** Easier to trigger, might catch accidental double-presses

## Project Structure

```
speech-to-text/
├── run.sh                      # Runner script
├── README.md                   # This file
├── config.example.toml         # Example configuration
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # Main entry point
│   ├── config.py               # Configuration management
│   │
│   ├── core/
│   │   ├── transcriber.py      # Whisper speech recognition
│   │   ├── recorder.py         # Audio recording
│   │   └── text_input.py       # Text input (python-uinput)
│   │
│   ├── daemon/
│   │   ├── hotkey_listener.py  # Keyboard monitoring (evdev)
│   │   ├── state_machine.py    # Service state management
│   │   └── service.py          # Main daemon loop
│   │
│   └── utils/
│       ├── logging.py          # Logging configuration
│       └── device_finder.py    # Keyboard device discovery
│
├── systemd/
│   └── speech-to-text.service  # Systemd user service
│
└── samples/                    # Test audio samples
```

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--daemon` | `-d` | Run in daemon mode (hold-to-talk) |
| `--record SECONDS` | `-r` | Record for specified seconds |
| `--type` | `-t` | Type transcribed text into active window |
| `--model MODEL` | `-m` | Whisper model: tiny, base, small, medium |
| `--config PATH` | `-c` | Path to configuration file |
| `--verbose` | `-v` | Enable verbose logging |
| `--quiet` | `-q` | Suppress non-essential output |
| `--test` | | Run component tests |
| `--help` | `-h` | Show help message |

## Whisper Models

All models are **multilingual** (99+ languages including Ukrainian and English).

| Model | Size | Speed (CPU) | Accuracy | RAM | Recommended For |
|-------|------|-------------|----------|-----|-----------------|
| tiny | 39 MB | ~500ms | Low | 500 MB | Testing only |
| **base** | 140 MB | **1-2s** | **Good** | **1 GB** | **Default choice** |
| small | 460 MB | 2-3s | Better | 2 GB | Better accuracy needed |
| medium | 1.5 GB | 3-5s | High | 5 GB | High-accuracy needs |
| large | 3+ GB | 5-10s | Highest | 10 GB | Professional use |

**Notes:**
- Times are for short phrases (5-10 seconds) on modern CPU (Intel i5/i7 or AMD Ryzen)
- All sizes handle Ukrainian, English, and 99+ other languages equally well
- `--model` flag or `config.toml` allows runtime selection

## Troubleshooting

### Audio not recording

```bash
# List audio devices
arecord -l

# Test recording
arecord -d 3 -f cd test.wav
aplay test.wav
```

### Text not typing

```bash
# Check uinput access
ls -la /dev/uinput

# Check group membership
groups | grep input

# If not in group:
sudo usermod -aG input $USER
# Then logout and login
```

### Keyboard not detected

```bash
# List input devices
ls -la /dev/input/event*

# Check group membership (should include 'input')
groups | grep input
```

### Service not starting

```bash
# Check service status
systemctl --user status speech-to-text

# View logs
journalctl --user -u speech-to-text -n 50

# Check environment
echo $XDG_SESSION_TYPE
echo $XDG_RUNTIME_DIR
```

### Whisper model error

```bash
# Activate environment
source ~/speech-env/bin/activate

# Reinstall
pip install --upgrade faster-whisper
```

### Ctrl shortcuts not working (Ctrl+Insert, Ctrl+C, etc.)

**Problem:** Single Ctrl press triggers dictation, preventing normal Ctrl shortcuts.

**Solution:** Enable double-tap mode in `~/.config/speech-to-text/config.toml`:

```toml
[hotkey]
enable_double_tap = true
double_tap_timeout_ms = 300
```

Then restart the service:
```bash
systemctl --user restart speech-to-text
```

Now single Ctrl press works normally - only double-tap activates dictation.

## How It Works

### Daemon Mode Workflow

1. **Initialization**
   - Pre-loads Whisper model into memory (first startup ~10 seconds)
   - Detects keyboard device and subscribes to evdev events
   - Detects display server (X11/Wayland) and loads appropriate text tool
   - Detects system language from GNOME keyboard layout

2. **Hold-to-Talk Recording**
   - Hold configured hotkey (default: Right Ctrl)
   - If double-tap mode enabled: Must double-tap within timeout window first
   - Plays start sound (optional)
   - Records audio in real-time to temporary file
   - Display: "RECORDING" state

3. **Transcription (on key release)**
   - Stops recording and audio file
   - Plays stop sound (optional)
   - Runs Whisper transcription (CPU-bound, ~1-3 seconds for typical phrase)
   - Auto-detects language if configured to do so
   - Display: "TRANSCRIBING" state

4. **Text Typing**
   - Strips trailing punctuation to avoid layout-specific issues
   - Types text using python-uinput (kernel-level, works on X11 and Wayland)
   - Display: "TYPING" state

5. **Cleanup**
   - Returns to IDLE state
   - Ready for next recording

### State Machine

```
        IDLE
         ↓ (hotkey press)
      RECORDING
         ↓ (hotkey release)
   TRANSCRIBING
         ↓ (text obtained)
       TYPING
         ↓ (typed)
        IDLE

    ERROR (any step fails)
         ↓ (auto-recover)
        IDLE
```

**Key Features:**
- **Language detection:** Keyboard layout checked at press time, not globally
- **Minimum duration check:** Ignores recordings < 0.5 seconds
- **Punctuation handling:** Strips trailing dots/ellipsis before typing
- **Async I/O:** Non-blocking recording and transcription
- **Error recovery:** Automatic return to IDLE on any error

## Development & Future Enhancements

Planned features and improvements:

1. **Alternative Models** - Support for Parakeet TDT, Distil-Whisper
2. **GNOME Integration** - Visual status indicator in top panel
3. **Text Processing** - Multiline detection, special character recognition
4. **Performance** - GPU support, model quantization options

### Running Tests

```bash
# Test all components
./run.sh --test

# Interactive mode with test option
./run.sh
# Then select option [4] to run tests
```

Tests verify:
- ✓ Display server detection
- ✓ Audio recording capability
- ✓ Whisper model loading
- ✓ Text tool availability
- ✓ Keyboard device detection

