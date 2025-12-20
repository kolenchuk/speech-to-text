"""Main speech-to-text daemon service."""

import asyncio
import logging
import signal
import os
from typing import Optional

from .hotkey_listener import HotkeyListener
from .multi_hotkey_listener import MultiHotkeyListener
from .state_machine import StateMachine, State
from ..core.transcriber import Transcriber
from ..core.recorder import AudioRecorder
from ..core.text_input import TextInput
from ..config import Config
from ..utils.keyboard_layout import KeyboardLayoutMapper

logger = logging.getLogger(__name__)


class AudioFeedback:
    """Simple audio feedback using paplay."""

    def __init__(self, enabled: bool = True, start_sound: str = "", stop_sound: str = ""):
        self.enabled = enabled
        self.start_sound = start_sound
        self.stop_sound = stop_sound

    async def play_start(self):
        """Play start recording sound."""
        if self.enabled and self.start_sound and os.path.exists(self.start_sound):
            await self._play(self.start_sound)

    async def play_stop(self):
        """Play stop recording sound."""
        if self.enabled and self.stop_sound and os.path.exists(self.stop_sound):
            await self._play(self.stop_sound)

    async def _play(self, sound_file: str):
        """Play sound file using paplay."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "paplay", sound_file,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Fire and forget
            asyncio.create_task(proc.wait())
        except Exception as e:
            logger.debug(f"Could not play sound: {e}")


class SpeechToTextService:
    """
    Main speech-to-text service.

    Orchestrates hotkey listening, audio recording, transcription, and text input.
    """

    def __init__(self, config: Config):
        """
        Initialize service.

        Args:
            config: Configuration object
        """
        self.config = config
        self.state = StateMachine(on_state_change=self._on_state_change)

        # Initialize components
        self.transcriber = Transcriber(
            model=config.whisper.model,
            local_model_path=config.whisper.local_model_path or None,
            download_if_missing=config.whisper.download_if_missing,
            device=config.whisper.device,
            compute_type=config.whisper.compute_type,
            language=config.whisper.language or None,
            beam_size=config.whisper.beam_size,
            vad_filter=config.whisper.vad_filter,
            initial_prompt=config.whisper.initial_prompt or "",
        )

        self.recorder = AudioRecorder(
            sample_rate=config.audio.sample_rate,
            channels=config.audio.channels,
            audio_format=config.audio.format,
        )

        self.text_input = TextInput(
            display_server=config.display.actual_server,
            key_delay_ms=config.text_input.key_delay_ms,
            mode=config.text_input.mode,
            paste_key_combination=config.text_input.paste_key_combination,
        )

        self.feedback = AudioFeedback(
            enabled=config.feedback.enabled,
            start_sound=config.feedback.start_sound,
            stop_sound=config.feedback.stop_sound,
        )

        self.listener: Optional[HotkeyListener] = None
        self._shutdown_event = asyncio.Event()
        self._current_audio_file: Optional[str] = None
        self._detected_language: Optional[str] = None  # Store language detected at key press

    def _on_state_change(self, old_state: State, new_state: State):
        """Handle state changes (for logging/debugging)."""
        pass

    async def _on_key_press(self):
        """Handle hotkey press - start recording."""
        if not self.state.is_idle:
            logger.debug("Ignoring key press - not in IDLE state")
            return

        logger.info("Hotkey pressed - starting recording")

        # Detect keyboard layout NOW (at key press time)
        if self.config.whisper.language == "":
            mapper = KeyboardLayoutMapper()
            detected_layout = mapper.detect_current_layout()
            if detected_layout:
                # Map GNOME layout codes to Whisper language codes
                layout_to_language = {
                    'us': 'en',
                    'uk': 'uk',
                    'ua': 'uk',  # GNOME uses 'ua' for Ukrainian, Whisper uses 'uk'
                }
                self._detected_language = layout_to_language.get(detected_layout, detected_layout)
                logger.info(f"Detected keyboard layout '{detected_layout}' -> language: {self._detected_language}")
            else:
                logger.info("Could not detect keyboard layout")
                self._detected_language = None

        if not self.state.start_recording():
            return

        # Play start sound
        await self.feedback.play_start()

        # Start recording
        try:
            self._current_audio_file = await self.recorder.start_recording()
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.state.error(str(e))
            self.state.recover_from_error()

    async def _on_key_release(self):
        """Handle hotkey release - stop recording and transcribe."""
        if not self.state.is_recording:
            logger.debug("Ignoring key release - not in RECORDING state")
            return

        logger.info("Hotkey released - stopping recording")

        # Stop recording
        if not self.state.stop_recording():
            return

        audio_file = await self.recorder.stop_recording()

        # Play stop sound
        await self.feedback.play_stop()

        if not audio_file:
            logger.warning("No audio file produced")
            self.state.finish()
            return

        # Check minimum duration
        file_size = os.path.getsize(audio_file) if os.path.exists(audio_file) else 0
        min_size = int(self.config.audio.sample_rate * self.config.audio.min_duration * 2)

        if file_size < min_size:
            logger.info("Recording too short, discarding")
            AudioRecorder.cleanup(audio_file)
            self.state.finish()
            return

        # Use the language detected at key press time
        detected_lang = self._detected_language

        # Transcribe in thread pool (CPU-bound)
        # Temporarily override language if keyboard layout was detected
        original_language = self.transcriber.language
        if detected_lang and self.config.whisper.language == "":
            self.transcriber.language = detected_lang
            logger.info(f"Using language from keyboard layout: {detected_lang}")

        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None,
                self.transcriber.transcribe,
                audio_file,
            )
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            AudioRecorder.cleanup(audio_file)
            self.state.error(str(e))
            self.state.recover_from_error()
            return
        finally:
            # Restore original language setting
            if detected_lang and self.config.whisper.language == "":
                self.transcriber.language = original_language
            # Clear detected language for next recording
            self._detected_language = None
            AudioRecorder.cleanup(audio_file)

        if not text or not text.strip():
            logger.info("No speech detected")
            self.state.finish()
            return

        # Strip trailing ellipsis/dots to avoid layout-dependent punctuation issues when typing
        cleaned_text = text.rstrip(" .…")
        if cleaned_text != text:
            logger.info("Removed trailing punctuation before typing")
            text = cleaned_text

        # Type text
        logger.info(f"Transcribed: {text[:50]}...")

        if not self.state.start_typing():
            return

        try:
            success = await self.text_input.type_text(text)
            if not success:
                logger.warning("Text typing may have failed")
        except Exception as e:
            logger.error(f"Typing failed: {e}")

        self.state.finish()

    async def run(self):
        """Run the service main loop."""
        logger.info("Starting Speech-to-Text service...")

        # Pre-load Whisper model
        logger.info("Pre-loading Whisper model...")
        try:
            self.transcriber.load_model()
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return

        # Set up hotkey listener (multi-device support for keyboard + mouse)
        trigger_keys = self.config.hotkey.trigger_keys
        double_tap_keys = self.config.hotkey.double_tap_key_list

        if len(trigger_keys) > 1:
            # Use multi-device listener for multiple triggers
            self.listener = MultiHotkeyListener(
                trigger_keys=trigger_keys,
                double_tap_keys=double_tap_keys,
                on_press=self._on_key_press,
                on_release=self._on_key_release,
                double_tap_timeout_ms=self.config.hotkey.double_tap_timeout_ms,
            )
        else:
            # Use single-device listener for backward compatibility
            self.listener = HotkeyListener(
                key_code=self.config.hotkey.key_code,
                device_path=self.config.hotkey.device_path or None,
                on_press=self._on_key_press,
                on_release=self._on_key_release,
                enable_double_tap=self.config.hotkey.enable_double_tap,
                double_tap_timeout_ms=self.config.hotkey.double_tap_timeout_ms,
            )

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal)

        # Build user-friendly message
        if double_tap_keys:
            double_tap_desc = " or ".join(double_tap_keys)
            single_tap_keys = [k for k in trigger_keys if k not in double_tap_keys]
            if single_tap_keys:
                single_tap_desc = " or ".join(single_tap_keys)
                logger.info(f"Service ready.")
                logger.info(f"  - Double-tap {double_tap_desc} and hold to record")
                logger.info(f"  - Hold {single_tap_desc} to record")
            else:
                logger.info(f"Service ready. Double-tap {double_tap_desc} and hold to record.")
        else:
            trigger_desc = " or ".join(trigger_keys)
            logger.info(f"Service ready. Hold {trigger_desc} to record.")

        try:
            await self.listener.start()
        except asyncio.CancelledError:
            logger.info("Service cancelled")
        except Exception as e:
            logger.error(f"Service error: {e}")
        finally:
            await self._cleanup()

    def _handle_signal(self):
        """Handle shutdown signals."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()
        if self.listener:
            self.listener.stop()

    async def _cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up...")

        # Cancel any ongoing recording
        if self.recorder.is_recording:
            await self.recorder.cancel_recording()

        logger.info("Service stopped")

    async def shutdown(self):
        """Initiate graceful shutdown."""
        self._handle_signal()


async def run_daemon(config: Config):
    """Run the speech-to-text daemon."""
    service = SpeechToTextService(config)
    await service.run()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__file__).rsplit("/", 3)[0])

    from ..config import Config
    from ..utils.logging import setup_logging

    config = Config.load()
    setup_logging(level=config.logging.level)

    asyncio.run(run_daemon(config))
