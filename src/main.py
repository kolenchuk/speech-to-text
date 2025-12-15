#!/usr/bin/env python3
"""
Speech-to-Text Application
==========================

Full-featured offline speech-to-text dictation for Ubuntu 24.04.

Usage:
    python -m src.main              # Interactive mode
    python -m src.main --daemon     # Background daemon (hold-to-talk)
    python -m src.main --record 5   # Record 5 seconds and transcribe
    python -m src.main --test       # Run component tests

Features:
    - Hold-to-talk recording (daemon mode)
    - Offline transcription using Whisper
    - Auto-typing into active application
    - Works on both X11 and Wayland
"""

import argparse
import asyncio
import sys
import os
import tempfile
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.utils.logging import setup_logging
from src.core.transcriber import Transcriber
from src.core.recorder import AudioRecorder
from src.core.text_input import TextInput


def run_tests(config: Config) -> bool:
    """Run component tests."""
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
    display = config.display.actual_server
    text_input = TextInput(display)
    print(f"  Display server: {display}")
    print(f"  Text tool: {text_input.tool}")
    print("  Result: PASS")
    tests_passed += 1
    print()

    # Test 2: Audio recording
    tests_total += 1
    print("Test 2: Audio Recording (2 seconds)")
    recorder = AudioRecorder(
        sample_rate=config.audio.sample_rate,
        channels=config.audio.channels,
    )
    audio_file = recorder.record_sync(2)
    if audio_file and os.path.exists(audio_file):
        print("  Result: PASS")
        tests_passed += 1
        AudioRecorder.cleanup(audio_file)
    else:
        print("  Result: FAIL")
    print()

    # Test 3: Whisper model
    tests_total += 1
    print("Test 3: Model Loading")
    try:
        transcriber = Transcriber(
            model=config.whisper.model,
            local_model_path=config.whisper.local_model_path or None,
            download_if_missing=config.whisper.download_if_missing,
            device=config.whisper.device,
            compute_type=config.whisper.compute_type,
        )
        transcriber.load_model()
        print(f"  Model: {config.whisper.model}")
        print(f"  Device: {config.whisper.device}")
        print("  Result: PASS")
        tests_passed += 1
    except Exception as e:
        print(f"  Error: {e}")
        print("  Result: FAIL")
    print()

    # Test 4: Text tool availability
    tests_total += 1
    print(f"Test 4: Text Tool ({text_input.tool})")
    if text_input._check_tool_available():
        print("  Result: PASS")
        tests_passed += 1
    else:
        print(f"  Result: FAIL - {text_input.tool} not found")
    print()

    # Test 5: Keyboard device (for daemon mode)
    tests_total += 1
    print("Test 5: Keyboard Device Detection")
    try:
        from src.utils.device_finder import find_keyboard_device, list_keyboard_devices

        keyboards = list_keyboard_devices()
        if keyboards:
            print(f"  Found {len(keyboards)} keyboard(s):")
            for kbd in keyboards[:3]:
                print(f"    - {kbd['path']}: {kbd['name']}")
            device = find_keyboard_device(config.hotkey.device_path or None)
            if device:
                print(f"  Selected: {device}")
                print("  Result: PASS")
                tests_passed += 1
            else:
                print("  Result: FAIL - Could not select device")
        else:
            print("  Result: FAIL - No keyboards found")
    except Exception as e:
        print(f"  Error: {e}")
        print("  Result: FAIL")
    print()

    # Summary
    print("=" * 60)
    print(f"Tests Passed: {tests_passed}/{tests_total}")
    print("=" * 60)

    return tests_passed == tests_total


def record_and_transcribe(
    config: Config,
    duration: int,
    type_output: bool = False,
) -> str:
    """Record audio, transcribe, and optionally type."""
    print()
    print("=" * 60)
    print("STEP 1: Recording Audio")
    print("=" * 60)
    print(f"Recording for {duration} seconds...")
    print("Speak now!")
    print()

    recorder = AudioRecorder(
        sample_rate=config.audio.sample_rate,
        channels=config.audio.channels,
    )

    audio_file = recorder.record_sync(duration)
    if not audio_file:
        print("Recording failed")
        return ""

    print()
    print("=" * 60)
    print("STEP 2: Transcribing")
    print("=" * 60)

    transcriber = Transcriber(
        model=config.whisper.model,
        local_model_path=config.whisper.local_model_path or None,
        download_if_missing=config.whisper.download_if_missing,
        device=config.whisper.device,
        compute_type=config.whisper.compute_type,
        language=config.whisper.language or None,
    )

    text = transcriber.transcribe(audio_file)
    AudioRecorder.cleanup(audio_file)

    if not text:
        print("No speech detected in audio")
        return ""

    print()
    print("Transcribed text:")
    print("-" * 60)
    print(text)
    print("-" * 60)

    if type_output and text:
        print()
        print("=" * 60)
        print("STEP 3: Typing Text")
        print("=" * 60)
        print()
        print("Focus on the target application window...")
        print("Text will be typed in 3 seconds...")
        time.sleep(3)

        text_input = TextInput(config.display.actual_server)
        text_input.type_text_sync(text)

    return text


def interactive_mode(config: Config):
    """Run in interactive mode with menu."""
    print()
    print("=" * 60)
    print("  Speech-to-Text Application")
    print("=" * 60)
    print()
    print(f"Display Server: {config.display.actual_server}")
    print(f"Model:          {config.whisper.model}")
    print(f"Hotkey:         {config.hotkey.trigger_key}")
    print()

    # Pre-load model
    print("Loading Whisper model...")
    transcriber = Transcriber(
        model=config.whisper.model,
        local_model_path=config.whisper.local_model_path or None,
        download_if_missing=config.whisper.download_if_missing,
        device=config.whisper.device,
        compute_type=config.whisper.compute_type,
    )
    transcriber.load_model()
    print()

    while True:
        print()
        print("Options:")
        print("  [1] Record and transcribe (5 seconds)")
        print("  [2] Record and transcribe (custom duration)")
        print("  [3] Record, transcribe, and TYPE to active window")
        print("  [4] Run component tests")
        print("  [5] Start daemon mode (hold-to-talk)")
        print("  [c] Show configuration")
        print("  [q] Quit")
        print()

        choice = input("Enter choice: ").strip().lower()

        if choice == "1":
            record_and_transcribe(config, 5, type_output=False)

        elif choice == "2":
            try:
                duration = int(input("Enter duration in seconds: "))
                record_and_transcribe(config, duration, type_output=False)
            except ValueError:
                print("Invalid duration")

        elif choice == "3":
            try:
                duration = int(input("Enter duration in seconds [5]: ") or "5")
                record_and_transcribe(config, duration, type_output=True)
            except ValueError:
                print("Invalid duration")

        elif choice == "4":
            run_tests(config)

        elif choice == "5":
            print()
            print("Starting daemon mode...")
            print(f"Hold {config.hotkey.trigger_key} to record, release to transcribe.")
            print("Press Ctrl+C to exit.")
            print()
            run_daemon_mode(config)

        elif choice == "c":
            config.print_config()

        elif choice == "q":
            print("Goodbye!")
            break

        else:
            print("Invalid choice")


def run_daemon_mode(config: Config):
    """Run in daemon mode (hold-to-talk)."""
    from src.daemon.service import run_daemon

    try:
        asyncio.run(run_daemon(config))
    except KeyboardInterrupt:
        print("\nDaemon stopped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Speech-to-Text Application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main              # Interactive mode
  python -m src.main --daemon     # Daemon mode (hold-to-talk)
  python -m src.main --record 5   # Record 5 seconds
  python -m src.main --record 10 --type  # Record and type
  python -m src.main --test       # Run tests
        """,
    )

    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run in daemon mode (hold-to-talk)",
    )

    parser.add_argument(
        "--record", "-r",
        type=int,
        metavar="SECONDS",
        help="Record for specified seconds and transcribe",
    )

    parser.add_argument(
        "--type", "-t",
        action="store_true",
        help="Type the transcribed text (use with --record)",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run component tests",
    )

    parser.add_argument(
        "--model", "-m",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model to use",
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        metavar="PATH",
        help="Path to configuration file",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-essential output",
    )

    args = parser.parse_args()

    # Load configuration
    config_path = args.config if args.config else None
    config = Config.load(config_path)

    # Override from command line
    if args.model:
        config.whisper.model = args.model

    # Set up logging
    log_level = "DEBUG" if args.verbose else ("WARNING" if args.quiet else config.logging.level)
    setup_logging(level=log_level)

    # Run tests
    if args.test:
        success = run_tests(config)
        sys.exit(0 if success else 1)

    # Daemon mode
    if args.daemon:
        run_daemon_mode(config)
        sys.exit(0)

    # Record and transcribe
    if args.record:
        text = record_and_transcribe(config, args.record, type_output=args.type)
        if text:
            print()
            print("Final transcription:")
            print(text)
        sys.exit(0 if text else 1)

    # Default: interactive mode
    interactive_mode(config)


if __name__ == "__main__":
    main()
