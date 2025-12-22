#!/usr/bin/env python3
"""Text input using python-uinput or clipboard-based paste.

This module provides a unified interface for typing text on both X11 and Wayland
using two modes:

1. **uinput mode**: Uses python-uinput for direct keycode injection (kernel level)
   - Works on both X11 and Wayland
   - Excellent Unicode/Cyrillic support
   - LIMITATION: Mixed Latin/Cyrillic text may be garbled (keycodes interpreted by active layout)

2. **clipboard mode**: Uses clipboard + paste key combination
   - Bypasses keyboard layout issues by pasting Unicode text directly
   - Better for mixed-script text (e.g., "Він сказав hello")
   - Requires wl-clipboard package on Wayland or xclip package on X11

Requirements:
    - User must be in 'input' group
    - /dev/uinput must be accessible
    - For clipboard mode on Wayland: wl-clipboard package (wl-copy/wl-paste commands)
    - For clipboard mode on X11: xclip package (xclip command)
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Optional, List, Tuple

from evdev import ecodes
from .uinput_keyboard import UInputKeyboard

logger = logging.getLogger(__name__)


class TextInput:
    """Text input using python-uinput or clipboard-based paste.

    Supports two modes:
    - "uinput": Direct keycode injection (default)
    - "clipboard": Copy to clipboard and emulate paste key

    Example:
        >>> text_input = TextInput(mode="clipboard", paste_key="shift+insert")
        >>> await text_input.type_text("Він сказав hello world")
    """

    def __init__(
        self,
        display_server: Optional[str] = None,
        key_delay_ms: int = 10,
        mode: str = "uinput",
        paste_key_combination: str = "shift+insert",
        pre_paste_delay_ms: int = 0
    ):
        """Initialize text input handler.

        Args:
            display_server: Ignored (kept for API compatibility).
            key_delay_ms: Delay between key events in milliseconds.
            mode: Input mode - "uinput" or "clipboard".
            paste_key_combination: Key combination for clipboard paste (e.g., "shift+insert").
            pre_paste_delay_ms: Delay before pasting (gives time to restore window focus).

        Raises:
            RuntimeError: If uinput is not accessible.
            ValueError: If mode is invalid or clipboard mode requirements not met.
        """
        self.key_delay_ms = key_delay_ms
        self.mode = mode.lower()
        self.paste_key_combination = paste_key_combination
        self.pre_paste_delay_ms = pre_paste_delay_ms
        self._uinput_keyboard: Optional[UInputKeyboard] = None
        self.tool = f"python-uinput ({self.mode} mode)"

        # Validate mode
        if self.mode not in ("uinput", "clipboard"):
            raise ValueError(f"Invalid mode '{self.mode}'. Must be 'uinput' or 'clipboard'")

        # Detect display server (for logging only)
        self.display_server = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        logger.info(f"Display server: {self.display_server}")

        # Check clipboard mode requirements
        if self.mode == "clipboard":
            self._validate_clipboard_mode()

        # Check uinput availability
        if not self._is_uinput_available():
            raise RuntimeError(
                "python-uinput not available. "
                "Ensure user is in 'input' group and /dev/uinput is accessible. "
                "Run: sudo usermod -aG input $USER && logout/login"
            )

        # Initialize uinput keyboard
        self._init_uinput()

        # Log clipboard backend info
        if self.mode == "clipboard":
            clipboard_tool = "wl-clipboard" if self.display_server == "wayland" else "xclip"
            logger.info(f"Using python-uinput in {self.mode} mode with {clipboard_tool} ({self.display_server})")
        else:
            logger.info(f"Using python-uinput in {self.mode} mode")

        # Special command mapping: word -> key code
        # These are voice commands that trigger key presses instead of typing
        # Pattern: Maps the spoken word to the corresponding evdev keycode
        # Why: Enables hands-free form submission, navigation, etc.
        # Includes English and Ukrainian variants
        self._special_commands = {
            "ENTER": ecodes.KEY_ENTER,
            "ЕНТЕР": ecodes.KEY_ENTER,  # Ukrainian transliteration
            # Future extensions can be added here:
            # "TAB": ecodes.KEY_TAB,
            # "ESCAPE": ecodes.KEY_ESC,
            # "BACKSPACE": ecodes.KEY_BACKSPACE,
        }

    def _is_uinput_available(self) -> bool:
        """Check if uinput is accessible."""
        return os.path.exists('/dev/uinput') and os.access('/dev/uinput', os.W_OK)

    def _init_uinput(self):
        """Initialize python-uinput keyboard."""
        try:
            self._uinput_keyboard = UInputKeyboard(key_delay_ms=self.key_delay_ms)
            logger.info("Python uinput keyboard initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize python-uinput: {e}")
            raise RuntimeError(f"Failed to initialize python-uinput: {e}") from e

    def _validate_clipboard_mode(self):
        """Validate clipboard mode requirements.

        Raises:
            RuntimeError: If clipboard mode requirements are not met.
        """
        if self.display_server == "wayland":
            # Wayland requires wl-clipboard
            if not shutil.which("wl-copy") or not shutil.which("wl-paste"):
                raise RuntimeError(
                    "Clipboard mode on Wayland requires wl-clipboard package.\n"
                    "Install with: sudo apt install wl-clipboard"
                )
            logger.info("Clipboard mode validated: wl-clipboard available (Wayland)")
        else:
            # X11 requires xclip
            if not shutil.which("xclip"):
                raise RuntimeError(
                    "Clipboard mode on X11 requires xclip package.\n"
                    "Install with: sudo apt install xclip"
                )
            logger.info("Clipboard mode validated: xclip available (X11)")

    def _parse_paste_key_combination(self) -> list:
        """Parse paste key combination string into evdev key codes.

        Returns:
            List of evdev key codes for the paste combination.

        Raises:
            ValueError: If key combination format is invalid.

        Example:
            "shift+insert" -> [KEY_LEFTSHIFT, KEY_INSERT]
            "ctrl+shift+v" -> [KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_V]
        """
        # Map of key names to evdev codes
        key_map = {
            "shift": ecodes.KEY_LEFTSHIFT,
            "ctrl": ecodes.KEY_LEFTCTRL,
            "alt": ecodes.KEY_LEFTALT,
            "insert": ecodes.KEY_INSERT,
            "v": ecodes.KEY_V,
        }

        parts = self.paste_key_combination.lower().split("+")
        keys = []

        for part in parts:
            part = part.strip()
            if part not in key_map:
                raise ValueError(
                    f"Invalid key '{part}' in paste combination '{self.paste_key_combination}'. "
                    f"Supported keys: {', '.join(key_map.keys())}"
                )
            keys.append(key_map[part])

        if len(keys) < 2:
            raise ValueError(
                f"Paste key combination must have at least 2 keys, got: '{self.paste_key_combination}'"
            )

        return keys

    async def _emulate_paste_key(self):
        """Emulate paste key combination using uinput.

        Example: For "shift+insert", presses Shift, then Insert, then releases both.
        """
        keys = self._parse_paste_key_combination()

        # Press all modifier keys first (all except the last key)
        for key in keys[:-1]:
            self._uinput_keyboard._device.write(ecodes.EV_KEY, key, 1)  # Press
            self._uinput_keyboard._device.syn()
            await asyncio.sleep(self.key_delay_ms / 1000.0)

        # Press and release the final key
        final_key = keys[-1]
        self._uinput_keyboard._device.write(ecodes.EV_KEY, final_key, 1)  # Press
        self._uinput_keyboard._device.syn()
        await asyncio.sleep(self.key_delay_ms / 1000.0)

        self._uinput_keyboard._device.write(ecodes.EV_KEY, final_key, 0)  # Release
        self._uinput_keyboard._device.syn()
        await asyncio.sleep(self.key_delay_ms / 1000.0)

        # Release all modifier keys in reverse order
        for key in reversed(keys[:-1]):
            self._uinput_keyboard._device.write(ecodes.EV_KEY, key, 0)  # Release
            self._uinput_keyboard._device.syn()
            await asyncio.sleep(self.key_delay_ms / 1000.0)

        logger.debug(f"Emulated paste key combination: {self.paste_key_combination}")

    async def _emulate_middle_click(self):
        """Emulate middle mouse button click to paste from PRIMARY selection.

        Middle-click is the traditional X11/Wayland way to paste from PRIMARY selection.
        This works reliably across display servers when Shift+Insert doesn't.
        """
        # Click middle button (press and release)
        self._uinput_keyboard._device.write(ecodes.EV_KEY, ecodes.BTN_MIDDLE, 1)  # Press
        self._uinput_keyboard._device.syn()
        await asyncio.sleep(0.01)

        self._uinput_keyboard._device.write(ecodes.EV_KEY, ecodes.BTN_MIDDLE, 0)  # Release
        self._uinput_keyboard._device.syn()
        await asyncio.sleep(0.01)

        logger.debug("Emulated middle-click to paste from PRIMARY selection")

    def _clipboard_get(self, primary: bool = False) -> bytes:
        """Get current clipboard contents.

        Args:
            primary: If True, use PRIMARY selection instead of CLIPBOARD.

        Returns:
            Clipboard contents as bytes, or empty bytes if clipboard is empty/unavailable.
        """
        try:
            selection = "primary" if primary else "clipboard"
            if self.display_server == "wayland":
                # Wayland: use wl-paste with --primary flag
                cmd = ["wl-paste", "--primary"] if primary else ["wl-paste"]
            else:
                # X11: use xclip with -selection flag
                cmd = ["xclip", "-selection", selection, "-o"]

            logger.debug(f"Reading {selection} selection with: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=1.0,
                check=False
            )

            if result.returncode != 0:
                logger.debug(f"xclip read failed with exit code {result.returncode}")
                if result.stderr:
                    stderr_text = result.stderr.decode('utf-8', errors='replace')
                    logger.debug(f"xclip read stderr: {stderr_text}")

            return result.stdout if result.returncode == 0 else b""
        except Exception as e:
            logger.debug(f"Could not read clipboard: {e}")
            return b""

    def _clipboard_set(self, text: str, primary: bool = False) -> bool:
        """Set clipboard contents.

        Args:
            text: Text to copy to clipboard.
            primary: If True, use PRIMARY selection instead of CLIPBOARD.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Use PRIMARY selection to avoid clipboard history managers
            # Most clipboard managers only track CLIPBOARD, not PRIMARY
            if self.display_server == "wayland":
                # Wayland: use wl-copy with --primary flag
                selection = "primary" if primary else "clipboard"
                cmd = ["wl-copy", "--primary"] if primary else ["wl-copy"]

                # Log Wayland environment for debugging
                wayland_display = os.environ.get('WAYLAND_DISPLAY', 'NOT SET')
                xdg_runtime = os.environ.get('XDG_RUNTIME_DIR', 'NOT SET')
                logger.info(f"Wayland environment: WAYLAND_DISPLAY={wayland_display}, XDG_RUNTIME_DIR={xdg_runtime}")

                try:
                    # Spawn wl-copy and send to background (don't wait for it)
                    # wl-copy needs to stay running to maintain selection ownership
                    logger.info(f"Spawning wl-copy for {selection} selection: {' '.join(cmd)}")
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True  # Detach from parent process group
                    )

                    # Write data to stdin and close (non-blocking)
                    try:
                        proc.stdin.write(text.encode('utf-8'))
                        proc.stdin.close()
                    except Exception as e:
                        logger.error(f"Failed to write to wl-copy stdin: {e}")
                        proc.kill()
                        return False

                    # Don't wait or poll on Wayland; wl-copy ownership timing varies
                    logger.info(f"wl-copy spawned for {selection} selection (PID: {proc.pid})")

                except Exception as e:
                    logger.error(f"wl-copy error: {e}")
                    return False
            else:
                # X11: use xclip with -selection flag
                selection = "primary" if primary else "clipboard"

                # Log X11 environment for debugging
                display = os.environ.get('DISPLAY', 'NOT SET')
                xauth = os.environ.get('XAUTHORITY', 'NOT SET')
                logger.info(f"X11 environment: DISPLAY={display}, XAUTHORITY={xauth}")

                # Quick test: can we run xclip at all?
                try:
                    test_result = subprocess.run(
                        ["xclip", "-version"],
                        capture_output=True,
                        timeout=0.5,
                        check=False
                    )
                    logger.debug(f"xclip -version returned: {test_result.returncode}")
                except Exception as e:
                    logger.warning(f"xclip -version test failed: {e}")

                # Use xclip to set selection
                # Use Popen and don't wait - like running "echo text | xclip &" in bash
                cmd = ["xclip", "-selection", selection, "-i"]

                try:
                    # Spawn xclip and send to background (don't wait for it)
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True  # Detach from parent process group
                    )

                    # Write data to stdin and close (non-blocking)
                    try:
                        proc.stdin.write(text.encode('utf-8'))
                        proc.stdin.flush()
                        proc.stdin.close()
                    except Exception as e:
                        logger.error(f"Failed to write to xclip stdin: {e}")
                        proc.kill()
                        return False

                    # Give xclip time to fork and become selection owner
                    # Don't wait for process to exit - it's running in background
                    time.sleep(0.15)
                    logger.debug(f"xclip spawned for {selection} selection (PID may have changed after fork)")

                except Exception as e:
                    logger.error(f"xclip error: {e}")
                    return False

            return True
        except Exception as e:
            logger.error(f"Failed to set clipboard: {e}")
            return False

    def _parse_special_commands(self, text: str) -> List[Tuple[str, str]]:
        """Parse text for special command words and split into segments.

        This method detects voice commands (like "ENTER") in the transcribed text
        and creates a sequence of actions: either type text or press a key.

        Args:
            text: Transcribed text that may contain special command words.

        Returns:
            List of (action_type, content) tuples where:
            - action_type is either "text" or "key"
            - content is the text to type or the command word

        Example:
            >>> parser._parse_special_commands("submit form ENTER")
            [("text", "submit form "), ("key", "ENTER")]

            >>> parser._parse_special_commands("hello ENTER world")
            [("text", "hello "), ("key", "ENTER"), ("text", " world")]

        Implementation Notes:
        - Uses word boundaries (\\b) to avoid matching "ENTER" within other words
          (e.g., "CENTER" won't trigger the command)
        - Case-insensitive matching handles variations from voice recognition
        - Preserves spaces around commands for natural typing flow
        """
        if not text or not self._special_commands:
            return [("text", text)]

        # Build regex pattern for all special commands
        # Pattern: \b(ENTER|TAB|ESCAPE)\b with word boundaries
        # Flags: re.IGNORECASE for case-insensitive matching
        command_words = "|".join(re.escape(cmd) for cmd in self._special_commands.keys())
        pattern = rf'\b({command_words})\b'

        segments = []
        last_end = 0
        prev_was_command = False

        # Find all command occurrences
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Add text before this command (if any)
            if match.start() > last_end:
                text_segment = text[last_end:match.start()]
                # Strip leading punctuation/space if previous segment was a command
                if prev_was_command:
                    text_segment = text_segment.lstrip(' .,;:!?')
                if text_segment:
                    segments.append(("text", text_segment))

            # Add the command
            # Normalize to uppercase to match dictionary keys
            command_word = match.group(1).upper()
            segments.append(("key", command_word))
            prev_was_command = True

            last_end = match.end()

        # Add remaining text after last command (if any)
        if last_end < len(text):
            remaining = text[last_end:]
            # Strip leading punctuation/space if previous segment was a command
            if prev_was_command:
                remaining = remaining.lstrip(' .,;:!?')
            if remaining:
                segments.append(("text", remaining))

        # If no commands found, return original text
        if not segments:
            segments = [("text", text)]

        logger.debug(f"Parsed command segments: {segments}")
        return segments

    async def press_key(self, keycode: int):
        """Press and release a key using uinput.

        This method emulates a physical key press: press down, wait, release.
        Works in both uinput and clipboard modes since both use uinput keyboard.

        Args:
            keycode: Linux evdev keycode (e.g., ecodes.KEY_ENTER).

        Example:
            >>> await text_input.press_key(ecodes.KEY_ENTER)
        """
        if self._uinput_keyboard is None or self._uinput_keyboard._device is None:
            logger.error("Cannot press key: uinput device not initialized")
            return

        # Press the key
        self._uinput_keyboard._device.write(ecodes.EV_KEY, keycode, 1)
        self._uinput_keyboard._device.syn()
        await asyncio.sleep(0.02)  # 20ms hold time

        # Release the key
        self._uinput_keyboard._device.write(ecodes.EV_KEY, keycode, 0)
        self._uinput_keyboard._device.syn()
        await asyncio.sleep(0.02)  # 20ms after release

        logger.debug(f"Pressed key: {keycode}")

    def press_key_sync(self, keycode: int):
        """Press and release a key using uinput (synchronous version).

        Args:
            keycode: Linux evdev keycode (e.g., ecodes.KEY_ENTER).

        Example:
            >>> text_input.press_key_sync(ecodes.KEY_ENTER)
        """
        if self._uinput_keyboard is None or self._uinput_keyboard._device is None:
            logger.error("Cannot press key: uinput device not initialized")
            return

        # Press the key
        self._uinput_keyboard._device.write(ecodes.EV_KEY, keycode, 1)
        self._uinput_keyboard._device.syn()
        time.sleep(self.key_delay_ms / 1000.0)

        # Release the key
        self._uinput_keyboard._device.write(ecodes.EV_KEY, keycode, 0)
        self._uinput_keyboard._device.syn()
        time.sleep(self.key_delay_ms / 1000.0)

        logger.debug(f"Pressed key: {keycode}")

    async def process_and_type_with_commands(self, text: str, auto_switch_layout: bool = True) -> bool:
        """Type text with special command recognition.

        This is the main entry point for command-aware text input. It:
        1. Parses text for special commands (like "ENTER")
        2. Splits into segments of text and key presses
        3. Executes each segment in order

        Args:
            text: Transcribed text that may contain special commands.
            auto_switch_layout: Ignored (kept for API compatibility).

        Returns:
            bool: True if successful, False on error.

        Example:
            >>> # User says: "submit form ENTER"
            >>> await text_input.process_and_type_with_commands("submit form ENTER")
            >>> # Result: Types "submit form " then presses ENTER key

        Edge Cases Handled:
        - Multiple commands: "first ENTER second ENTER" types text then presses ENTER twice
        - Mixed text/commands: "hello ENTER world" types "hello ", presses ENTER, types " world"
        - No commands: "just plain text" behaves like normal type_text()
        - Word boundaries: "did you center that" types normally (doesn't trigger ENTER)
        """
        if not text:
            logger.warning("Empty text provided to process_and_type_with_commands()")
            return True

        # Parse text into command segments
        segments = self._parse_special_commands(text)
        logger.debug(f"Parsed {len(segments)} segments: {segments}")

        try:
            for action_type, content in segments:
                if action_type == "text":
                    # Type the text segment
                    success = await self.type_text(content, auto_switch_layout)
                    if not success:
                        logger.warning(f"Failed to type text segment: {content[:50]}")
                        return False

                elif action_type == "key":
                    # Press the special key
                    if content in self._special_commands:
                        keycode = self._special_commands[content]
                        logger.info(f"Executing voice command: {content} -> pressing key {keycode}")
                        # Small delay to ensure previous paste is fully processed
                        await asyncio.sleep(0.05)
                        await self.press_key(keycode)
                    else:
                        logger.warning(f"Unknown special command: {content}")

            logger.info("Command-aware text input completed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to process text with commands: {e}")
            return False

    def process_and_type_with_commands_sync(self, text: str, auto_switch_layout: bool = True) -> bool:
        """Type text with special command recognition (synchronous version).

        Args:
            text: Transcribed text that may contain special commands.
            auto_switch_layout: Ignored (kept for API compatibility).

        Returns:
            bool: True if successful, False on error.

        Example:
            >>> text_input.process_and_type_with_commands_sync("submit form ENTER")
        """
        if not text:
            logger.warning("Empty text provided to process_and_type_with_commands_sync()")
            return True

        # Parse text into command segments
        segments = self._parse_special_commands(text)

        logger.debug(f"Processing {len(segments)} segments with commands (sync)")

        try:
            for action_type, content in segments:
                if action_type == "text":
                    # Type the text segment
                    success = self.type_text_sync(content, auto_switch_layout)
                    if not success:
                        logger.warning(f"Failed to type text segment: {content[:50]}")
                        return False

                elif action_type == "key":
                    # Press the special key
                    if content in self._special_commands:
                        keycode = self._special_commands[content]
                        logger.info(f"Executing voice command: {content} -> pressing key {keycode}")
                        self.press_key_sync(keycode)
                    else:
                        logger.warning(f"Unknown special command: {content}")

            logger.info("Command-aware text input completed successfully (sync)")
            return True

        except Exception as e:
            logger.error(f"Failed to process text with commands: {e}")
            return False

    async def _type_text_clipboard(self, text: str) -> bool:
        """Type text using clipboard paste method.

        Uses PRIMARY selection to avoid polluting clipboard history.
        Most clipboard managers only track CLIPBOARD, not PRIMARY.

        Args:
            text: Text to type.

        Returns:
            bool: True if successful, False on error.
        """
        try:
            logger.debug(f"Setting PRIMARY selection to: {repr(text[:100])}...")

            # Copy text to PRIMARY selection
            if self._clipboard_set(text, primary=True):
                # Wayland primary readback can be unreliable with wl-copy ownership;
                # skip verification and paste immediately.
                if self.display_server == "wayland":
                    await asyncio.sleep(0.05)

                    # Pre-paste delay: gives user time to restore window focus
                    if self.pre_paste_delay_ms > 0:
                        logger.info(f"Waiting {self.pre_paste_delay_ms}ms before pasting (gives time to restore focus)...")
                        await asyncio.sleep(self.pre_paste_delay_ms / 1000.0)

                    await self._emulate_middle_click()
                    logger.info("Text pasted successfully via PRIMARY selection (middle-click)")
                    await asyncio.sleep(0.05)
                    return True

                # Delay to ensure clipboard tool has registered as PRIMARY owner
                # X11 xclip needs time to become selection owner
                await asyncio.sleep(0.2)

                # Verify PRIMARY was set correctly
                readback = self._clipboard_get(primary=True).decode('utf-8', errors='replace')
                if readback != text:
                    logger.warning("PRIMARY verification failed!")
                    logger.warning(f"Expected: {repr(text[:100])}")
                    logger.warning(f"Got: {repr(readback[:100])}")
                    logger.warning("Retrying with longer delay...")

                    # Retry with longer delay
                    await asyncio.sleep(0.15)
                    readback = self._clipboard_get(primary=True).decode('utf-8', errors='replace')

                if readback == text:
                    logger.debug("PRIMARY verified successfully")

                    # Give applications time to register the PRIMARY selection change
                    # Some apps (terminals, etc.) need time to notice the selection changed
                    await asyncio.sleep(0.1)

                    # Pre-paste delay: gives user time to restore window focus
                    if self.pre_paste_delay_ms > 0:
                        logger.info(f"Waiting {self.pre_paste_delay_ms}ms before pasting (gives time to restore focus)...")
                        await asyncio.sleep(self.pre_paste_delay_ms / 1000.0)

                    # Emulate middle-click to paste from PRIMARY selection
                    await self._emulate_middle_click()

                    logger.info("Text pasted successfully via PRIMARY selection (middle-click)")
                    await asyncio.sleep(0.05)
                    return True

                logger.warning("PRIMARY still incorrect after retry - falling back to CLIPBOARD")
            else:
                logger.warning("Failed to set PRIMARY selection - falling back to CLIPBOARD")

            # Fallback to CLIPBOARD selection + paste key combination
            logger.debug(f"Setting CLIPBOARD selection to: {repr(text[:100])}...")
            if not self._clipboard_set(text, primary=False):
                logger.error("Failed to set CLIPBOARD selection")
                return False

            if self.display_server != "wayland":
                await asyncio.sleep(0.2)
                readback = self._clipboard_get(primary=False).decode('utf-8', errors='replace')
                if readback != text:
                    logger.warning("CLIPBOARD verification failed!")
                    logger.warning(f"Expected: {repr(text[:100])}")
                    logger.warning(f"Got: {repr(readback[:100])}")
                    logger.warning("Retrying with longer delay...")
                    await asyncio.sleep(0.15)
                    readback = self._clipboard_get(primary=False).decode('utf-8', errors='replace')
                    if readback != text:
                        logger.error("CLIPBOARD still incorrect after retry - falling back to uinput typing")
                        return await self._type_text_uinput_fallback(text)
                logger.debug("CLIPBOARD verified successfully")

            await asyncio.sleep(0.1)

            # Pre-paste delay: gives user time to restore window focus
            if self.pre_paste_delay_ms > 0:
                logger.info(f"Waiting {self.pre_paste_delay_ms}ms before pasting (gives time to restore focus)...")
                await asyncio.sleep(self.pre_paste_delay_ms / 1000.0)

            # Use paste key combination for CLIPBOARD
            await self._emulate_paste_key()
            logger.info("Text pasted successfully via CLIPBOARD (paste key)")
            await asyncio.sleep(0.05)
            return True

        except Exception as e:
            logger.error(f"Failed to type text via clipboard: {e}")
            return await self._type_text_uinput_fallback(text)

    async def _type_text_uinput_fallback(self, text: str) -> bool:
        if self._uinput_keyboard is None:
            logger.error("Cannot fall back to uinput typing: uinput device not initialized")
            return False

        try:
            await self._uinput_keyboard.type_text(text)
            logger.info("Text typed successfully via uinput fallback")
            return True
        except Exception as e:
            logger.error(f"Uinput fallback typing failed: {e}")
            return False

    async def type_text(self, text: str, auto_switch_layout: bool = True) -> bool:
        """Type text using configured mode (async interface).

        Args:
            text: Text to type. May contain newlines and special characters.
            auto_switch_layout: Ignored (kept for API compatibility).

        Returns:
            bool: True if successful, False on error.

        Example:
            >>> text_input = TextInput(mode="clipboard")
            >>> await text_input.type_text("Він сказав hello world")
        """
        if not text:
            logger.warning("Empty text provided to type_text()")
            return True

        logger.debug(f"Typing text ({self.mode} mode): {repr(text[:50])}...")

        # Route to appropriate method based on mode
        if self.mode == "clipboard":
            return await self._type_text_clipboard(text)
        else:  # uinput mode
            try:
                await self._uinput_keyboard.type_text(text)
                logger.info("Text typing completed successfully with python-uinput")
                return True
            except Exception as e:
                logger.error(f"Failed to type text: {e}")
                return False

    def type_text_sync(self, text: str, auto_switch_layout: bool = True) -> bool:
        """Type text using configured mode (synchronous interface).

        Args:
            text: Text to type. May contain newlines and special characters.
            auto_switch_layout: Ignored (kept for API compatibility).

        Returns:
            bool: True if successful, False on error.

        Example:
            >>> text_input = TextInput(mode="clipboard")
            >>> text_input.type_text_sync("Він сказав hello world")
        """
        if not text:
            logger.warning("Empty text provided to type_text_sync()")
            return True

        logger.debug(f"Typing text (sync, {self.mode} mode): {repr(text[:50])}...")

        # Route to appropriate method based on mode
        if self.mode == "clipboard":
            # Run async clipboard method in sync context
            return asyncio.run(self._type_text_clipboard(text))
        else:  # uinput mode
            try:
                self._uinput_keyboard.type_text_sync(text)
                logger.debug("Text typing completed successfully (sync)")
                return True
            except Exception as e:
                logger.error(f"Failed to type text: {e}")
                return False

    def close(self):
        """Cleanup resources.

        Should be called when done using TextInput to release resources.
        """
        if self._uinput_keyboard is not None:
            self._uinput_keyboard.close()
            self._uinput_keyboard = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()

    def __del__(self):
        """Destructor - ensure cleanup."""
        self.close()


async def test_text_input():
    """Test function for TextInput abstraction.

    Demonstrates usage and can be run standalone to verify functionality.
    """
    print("Testing TextInput abstraction...")
    print("Text will be typed in 3 seconds. Focus a text editor!")

    await asyncio.sleep(3)

    async with TextInput() as text_input:
        print(f"Using tool: {text_input.tool}")

        # Test English
        await text_input.type_text("Hello from TextInput!\n")
        await asyncio.sleep(0.5)

        # Test Ukrainian (if supported)
        await text_input.type_text("Привіт, світ!\n")
        await asyncio.sleep(0.5)

        # Test mixed
        await text_input.type_text("Mixed: English + Українська\n")

    print("Test complete!")


if __name__ == '__main__':
    # Allow running this module directly for testing
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(test_text_input())
