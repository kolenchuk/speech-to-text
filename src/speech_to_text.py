#!/usr/bin/env python3
"""
Speech-to-Text Prototype Script
===============================

A simple prototype demonstrating offline speech-to-text dictation.

Features:
- Records audio from microphone
- Transcribes using Whisper (offline, CPU)
- Types text using ydotool (Wayland) or xdotool (X11)

Usage:
    python3 speech_to_text.py              # Interactive mode
    python3 speech_to_text.py --record 5   # Record 5 seconds and transcribe
    python3 speech_to_text.py --test       # Run component tests

Requirements:
    - Python 3.10+
    - faster-whisper, numpy, soundfile (pip packages)
    - arecord (alsa-utils)
    - ydotool (Wayland) or xdotool (X11)
"""

import os
import sys
import subprocess
import tempfile
import time
import argparse
from pathlib import Path


# =============================================================================
# Configuration
# =============================================================================

class Config:
    """Configuration settings for speech-to-text."""

    # Whisper model settings
    WHISPER_MODEL = "base"          # Options: tiny, base, small, medium, large
    WHISPER_DEVICE = "cpu"          # Options: cpu, cuda
    WHISPER_COMPUTE_TYPE = "int8"   # Options: int8, float16, float32
    WHISPER_LANGUAGE = None         # None for auto-detect, or "en", "uk", etc.

    # Audio recording settings
    AUDIO_FORMAT = "cd"             # CD quality: 16-bit, 44.1kHz, stereo
    AUDIO_CHANNELS = 1              # Mono for speech
    AUDIO_RATE = 16000              # 16kHz is optimal for Whisper
    DEFAULT_DURATION = 5            # Default recording duration in seconds

    # Display server detection
    DISPLAY_SERVER = os.environ.get('XDG_SESSION_TYPE', 'x11')

    # Text automation tool
    TEXT_TOOL = "ydotool" if DISPLAY_SERVER == "wayland" else "xdotool"


# =============================================================================
# Display Server Detection
# =============================================================================

def detect_display_server() -> str:
    """Detect whether running on X11 or Wayland."""
    session_type = os.environ.get('XDG_SESSION_TYPE', 'x11')
    return session_type


def get_text_tool() -> str:
    """Get the appropriate text automation tool for the display server."""
    display_server = detect_display_server()
    if display_server == "wayland":
        return "ydotool"
    else:
        return "xdotool"


# =============================================================================
# Audio Recording
# =============================================================================

def record_audio(duration: int, output_file: str) -> bool:
    """
    Record audio from the default microphone using arecord.

    Args:
        duration: Recording duration in seconds
        output_file: Path to save the WAV file

    Returns:
        True if recording successful, False otherwise
    """
    print(f"Recording for {duration} seconds...")
    print("Speak now!")
    print()

    try:
        cmd = [
            "arecord",
            "-d", str(duration),
            "-f", "S16_LE",           # 16-bit signed little-endian
            "-r", str(Config.AUDIO_RATE),  # Sample rate
            "-c", str(Config.AUDIO_CHANNELS),  # Channels
            "-t", "wav",              # WAV format
            output_file
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration + 5
        )

        if result.returncode == 0 and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            print(f"Recording complete ({file_size / 1024:.1f} KB)")
            return True
        else:
            print(f"Recording failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("Recording timed out")
        return False
    except FileNotFoundError:
        print("Error: arecord not found. Install with: sudo apt install alsa-utils")
        return False
    except Exception as e:
        print(f"Recording error: {e}")
        return False


# =============================================================================
# Speech Recognition
# =============================================================================

_whisper_model = None

def load_whisper_model():
    """Load Whisper model (cached after first load)."""
    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    print(f"Loading Whisper '{Config.WHISPER_MODEL}' model...")

    try:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            Config.WHISPER_MODEL,
            device=Config.WHISPER_DEVICE,
            compute_type=Config.WHISPER_COMPUTE_TYPE
        )

        print("Model loaded successfully")
        return _whisper_model

    except ImportError:
        print("Error: faster-whisper not installed.")
        print("Install with: pip install faster-whisper")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to load model: {e}")
        sys.exit(1)


def transcribe_audio(audio_file: str) -> str:
    """
    Transcribe audio file using Whisper.

    Args:
        audio_file: Path to the WAV file

    Returns:
        Transcribed text
    """
    model = load_whisper_model()

    print("Transcribing...")

    try:
        segments, info = model.transcribe(
            audio_file,
            language=Config.WHISPER_LANGUAGE,
            beam_size=5,
            vad_filter=True,  # Filter out non-speech
        )

        # Collect all segments into text
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts)

        print(f"Detected language: {info.language} ({info.language_probability:.1%})")

        return full_text

    except Exception as e:
        print(f"Transcription error: {e}")
        return ""


# =============================================================================
# Text Automation
# =============================================================================

def ensure_ydotool_daemon():
    """Ensure ydotool is ready (for Wayland)."""
    if Config.TEXT_TOOL != "ydotool":
        return True

    # Ubuntu 24.04's ydotool (0.1.8) doesn't need a separate daemon
    # Just verify ydotool is installed
    result = subprocess.run(
        ["which", "ydotool"],
        capture_output=True
    )

    if result.returncode == 0:
        return True

    print("Error: ydotool not found. Install with: sudo apt install ydotool")
    return False


def type_text(text: str) -> bool:
    """
    Type text into the active application using ydotool or xdotool.

    Args:
        text: Text to type

    Returns:
        True if successful, False otherwise
    """
    if not text:
        print("No text to type")
        return False

    tool = Config.TEXT_TOOL

    # Ensure ydotoold is running for Wayland
    if tool == "ydotool":
        if not ensure_ydotool_daemon():
            return False

    print(f"Typing text using {tool}...")

    try:
        if tool == "ydotool":
            cmd = ["ydotool", "type", "--", text]
        else:  # xdotool
            cmd = ["xdotool", "type", "--", text]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("Text typed successfully!")
            return True
        else:
            print(f"Typing failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("Typing timed out")
        return False
    except FileNotFoundError:
        print(f"Error: {tool} not found.")
        if tool == "ydotool":
            print("Install with: sudo apt install ydotool")
        else:
            print("Install with: sudo apt install xdotool")
        return False
    except Exception as e:
        print(f"Typing error: {e}")
        return False


# =============================================================================
# Main Functions
# =============================================================================

def record_and_transcribe(duration: int = None, type_output: bool = True) -> str:
    """
    Complete workflow: record audio, transcribe, and optionally type.

    Args:
        duration: Recording duration in seconds
        type_output: Whether to type the transcribed text

    Returns:
        Transcribed text
    """
    if duration is None:
        duration = Config.DEFAULT_DURATION

    # Create temporary file for audio
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio_file = f.name

    try:
        # Step 1: Record audio
        print()
        print("=" * 60)
        print("STEP 1: Recording Audio")
        print("=" * 60)

        if not record_audio(duration, audio_file):
            return ""

        # Step 2: Transcribe
        print()
        print("=" * 60)
        print("STEP 2: Transcribing")
        print("=" * 60)

        text = transcribe_audio(audio_file)

        if not text:
            print("No speech detected in audio")
            return ""

        print()
        print("Transcribed text:")
        print("-" * 60)
        print(text)
        print("-" * 60)

        # Step 3: Type text (optional)
        if type_output and text:
            print()
            print("=" * 60)
            print("STEP 3: Typing Text")
            print("=" * 60)
            print()
            print("Focus on the target application window...")
            print("Text will be typed in 3 seconds...")
            time.sleep(3)

            type_text(text)

        return text

    finally:
        # Clean up temporary file
        if os.path.exists(audio_file):
            os.unlink(audio_file)


def run_tests():
    """Run component tests to verify system setup."""
    print()
    print("=" * 60)
    print("Running Component Tests")
    print("=" * 60)
    print()

    tests_passed = 0
    tests_total = 0

    # Test 1: Display server detection
    tests_total += 1
    print("Test 1: Display Server Detection")
    display = detect_display_server()
    tool = get_text_tool()
    print(f"  Display server: {display}")
    print(f"  Text tool: {tool}")
    print(f"  Result: PASS")
    tests_passed += 1
    print()

    # Test 2: Audio recording
    tests_total += 1
    print("Test 2: Audio Recording (2 seconds)")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        test_audio = f.name

    try:
        if record_audio(2, test_audio):
            print(f"  Result: PASS")
            tests_passed += 1
        else:
            print(f"  Result: FAIL")
    finally:
        if os.path.exists(test_audio):
            os.unlink(test_audio)
    print()

    # Test 3: Whisper model
    tests_total += 1
    print("Test 3: Whisper Model Loading")
    try:
        model = load_whisper_model()
        if model:
            print(f"  Model: {Config.WHISPER_MODEL}")
            print(f"  Device: {Config.WHISPER_DEVICE}")
            print(f"  Result: PASS")
            tests_passed += 1
        else:
            print(f"  Result: FAIL")
    except Exception as e:
        print(f"  Error: {e}")
        print(f"  Result: FAIL")
    print()

    # Test 4: Text tool availability
    tests_total += 1
    print(f"Test 4: Text Tool ({Config.TEXT_TOOL})")
    result = subprocess.run(["which", Config.TEXT_TOOL], capture_output=True)
    if result.returncode == 0:
        print(f"  Path: {result.stdout.decode().strip()}")
        print(f"  Result: PASS")
        tests_passed += 1
    else:
        print(f"  Result: FAIL - {Config.TEXT_TOOL} not found")
    print()

    # Summary
    print("=" * 60)
    print(f"Tests Passed: {tests_passed}/{tests_total}")
    print("=" * 60)

    return tests_passed == tests_total


def interactive_mode():
    """Run in interactive mode with menu."""
    print()
    print("=" * 60)
    print("  Speech-to-Text Prototype")
    print("=" * 60)
    print()
    print(f"Display Server: {Config.DISPLAY_SERVER}")
    print(f"Text Tool: {Config.TEXT_TOOL}")
    print(f"Whisper Model: {Config.WHISPER_MODEL}")
    print()

    # Pre-load model
    load_whisper_model()

    while True:
        print()
        print("Options:")
        print("  [1] Record and transcribe (5 seconds)")
        print("  [2] Record and transcribe (custom duration)")
        print("  [3] Record, transcribe, and TYPE to active window")
        print("  [4] Run component tests")
        print("  [q] Quit")
        print()

        choice = input("Enter choice: ").strip().lower()

        if choice == "1":
            text = record_and_transcribe(5, type_output=False)

        elif choice == "2":
            try:
                duration = int(input("Enter duration in seconds: "))
                text = record_and_transcribe(duration, type_output=False)
            except ValueError:
                print("Invalid duration")

        elif choice == "3":
            try:
                duration = int(input("Enter duration in seconds [5]: ") or "5")
                text = record_and_transcribe(duration, type_output=True)
            except ValueError:
                print("Invalid duration")

        elif choice == "4":
            run_tests()

        elif choice == "q":
            print("Goodbye!")
            break

        else:
            print("Invalid choice")


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Speech-to-Text Prototype",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 speech_to_text.py              # Interactive mode
  python3 speech_to_text.py --record 5   # Record 5 seconds
  python3 speech_to_text.py --record 10 --type  # Record and type
  python3 speech_to_text.py --test       # Run tests
        """
    )

    parser.add_argument(
        "--record", "-r",
        type=int,
        metavar="SECONDS",
        help="Record for specified seconds and transcribe"
    )

    parser.add_argument(
        "--type", "-t",
        action="store_true",
        help="Type the transcribed text (use with --record)"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run component tests"
    )

    parser.add_argument(
        "--model", "-m",
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        help="Whisper model to use (default: base)"
    )

    args = parser.parse_args()

    # Update config from args
    if args.model:
        Config.WHISPER_MODEL = args.model

    # Run tests
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)

    # Record and transcribe
    if args.record:
        text = record_and_transcribe(args.record, type_output=args.type)
        if text:
            print()
            print("Final transcription:")
            print(text)
        sys.exit(0 if text else 1)

    # Default: interactive mode
    interactive_mode()


if __name__ == "__main__":
    main()
