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
import shutil
import subprocess
from typing import Optional

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
        paste_key_combination: str = "shift+insert"
    ):
        """Initialize text input handler.

        Args:
            display_server: Ignored (kept for API compatibility).
            key_delay_ms: Delay between key events in milliseconds.
            mode: Input mode - "uinput" or "clipboard".
            paste_key_combination: Key combination for clipboard paste (e.g., "shift+insert").

        Raises:
            RuntimeError: If uinput is not accessible.
            ValueError: If mode is invalid or clipboard mode requirements not met.
        """
        self.key_delay_ms = key_delay_ms
        self.mode = mode.lower()
        self.paste_key_combination = paste_key_combination
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

    def _clipboard_get(self, primary: bool = False) -> bytes:
        """Get current clipboard contents.

        Args:
            primary: If True, use PRIMARY selection instead of CLIPBOARD.

        Returns:
            Clipboard contents as bytes, or empty bytes if clipboard is empty/unavailable.
        """
        try:
            if self.display_server == "wayland":
                # Wayland: use wl-paste with --primary flag
                cmd = ["wl-paste", "--primary"] if primary else ["wl-paste"]
            else:
                # X11: use xclip with -selection flag
                selection = "primary" if primary else "clipboard"
                cmd = ["xclip", "-selection", selection, "-o"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=1.0,
                check=False
            )
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
                cmd = ["wl-copy", "--primary"] if primary else ["wl-copy"]

                # Use Popen to fire-and-forget wl-copy (it forks to background)
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                process.stdin.write(text.encode('utf-8'))
                process.stdin.close()

                # Don't wait for it - wl-copy forks to background
                # Just give it a moment to start
                import time
                time.sleep(0.05)
            else:
                # X11: use xclip with -selection flag
                selection = "primary" if primary else "clipboard"
                cmd = ["xclip", "-selection", selection, "-i"]

                # xclip waits for input on stdin
                result = subprocess.run(
                    cmd,
                    input=text.encode('utf-8'),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                    check=True
                )

            return True
        except Exception as e:
            logger.error(f"Failed to set clipboard: {e}")
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
            # Save original PRIMARY selection (not CLIPBOARD)
            # This avoids interfering with the user's regular clipboard (Ctrl+C/V)
            original_primary = self._clipboard_get(primary=True)
            if original_primary:
                logger.debug("Saved original PRIMARY selection")

            # Copy text to PRIMARY selection
            if not self._clipboard_set(text, primary=True):
                return False

            logger.debug("Text copied to PRIMARY selection (avoiding clipboard history)")

            # Small delay to ensure PRIMARY selection is ready
            await asyncio.sleep(0.05)

            # Emulate paste key combination (Shift+Insert pastes from PRIMARY)
            await self._emulate_paste_key()

            logger.info("Text pasted successfully via PRIMARY selection")

            # Wait for paste to complete
            await asyncio.sleep(0.1)

            # Restore original PRIMARY selection
            if original_primary:
                self._clipboard_set(original_primary.decode('utf-8', errors='replace'), primary=True)
                logger.debug("Restored original PRIMARY selection")

            return True

        except Exception as e:
            logger.error(f"Failed to type text via clipboard: {e}")
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
