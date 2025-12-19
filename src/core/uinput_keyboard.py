#!/usr/bin/env python3
"""Pure-Python virtual keyboard using Linux uinput subsystem.

This module provides a UInputKeyboard class that creates a virtual keyboard
device using the evdev.UInput API. It translates text strings to keyboard
events with full Unicode/Cyrillic support.

Key Features:
- No external tools required (xdotool/ydotool/wtype)
- Full Unicode support (Ukrainian Cyrillic, English, etc.)
- Layout-aware character mapping
- Async and sync typing interfaces
- Configurable key delay for reliability
- No clipboard modification (pure keyboard events)

Requirements:
- User must be in 'input' group for /dev/uinput access
- python-evdev package installed
- Kernel CONFIG_INPUT_UINPUT enabled (standard on Ubuntu)

Supported Characters:
- ASCII letters (a-z, A-Z)
- Numbers (0-9)
- Common punctuation (. , ! ? : ; ' " / - _ = + etc.)
- Ukrainian Cyrillic (а-я, А-Я, і, ї, є, ґ)
- Whitespace (space, newline, tab)

Unsupported:
- Dead keys and compose sequences
- Non-printable control characters (beyond newline/tab)
- Characters not in standard keyboard layouts
"""

import asyncio
import logging
import time
from typing import Optional
from evdev import UInput, ecodes

from ..utils.keyboard_layout import get_keyboard_mapper, KeyboardLayoutMapper

logger = logging.getLogger(__name__)


class UInputKeyboard:
    """Virtual keyboard using Linux uinput for text injection.

    This class creates a virtual keyboard device that can inject keyboard
    events into the system. It provides both async and sync interfaces
    for typing text.

    Example:
        >>> keyboard = UInputKeyboard(key_delay_ms=10)
        >>> await keyboard.type_text("Hello, світ!")
        >>> keyboard.close()
    """

    def __init__(self, key_delay_ms: int = 10):
        """Initialize virtual keyboard device.

        Args:
            key_delay_ms: Delay in milliseconds between key events.
                Higher values = slower typing but more reliable.
                Default: 10ms (reasonable for most systems).

        Raises:
            PermissionError: If user lacks access to /dev/uinput.
                User must be in 'input' group.
            OSError: If uinput kernel module is not loaded.
        """
        self.key_delay_ms = key_delay_ms
        self.key_delay_sec = key_delay_ms / 1000.0
        self._device: Optional[UInput] = None
        self._mapper: KeyboardLayoutMapper = get_keyboard_mapper()

        # Initialize the virtual keyboard device
        self._init_device()

    def _init_device(self):
        """Create the uinput virtual keyboard device.

        Raises:
            PermissionError: If /dev/uinput is not accessible.
            OSError: If uinput module is not loaded.
        """
        try:
            # Define the capabilities of our virtual keyboard
            # We need all alphanumeric keys, modifiers, and common symbols
            capabilities = {
                ecodes.EV_KEY: [
                    # Letter keys
                    ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_C, ecodes.KEY_D,
                    ecodes.KEY_E, ecodes.KEY_F, ecodes.KEY_G, ecodes.KEY_H,
                    ecodes.KEY_I, ecodes.KEY_J, ecodes.KEY_K, ecodes.KEY_L,
                    ecodes.KEY_M, ecodes.KEY_N, ecodes.KEY_O, ecodes.KEY_P,
                    ecodes.KEY_Q, ecodes.KEY_R, ecodes.KEY_S, ecodes.KEY_T,
                    ecodes.KEY_U, ecodes.KEY_V, ecodes.KEY_W, ecodes.KEY_X,
                    ecodes.KEY_Y, ecodes.KEY_Z,

                    # Number keys
                    ecodes.KEY_0, ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_3,
                    ecodes.KEY_4, ecodes.KEY_5, ecodes.KEY_6, ecodes.KEY_7,
                    ecodes.KEY_8, ecodes.KEY_9,

                    # Modifier keys
                    ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
                    ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
                    ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,

                    # Special keys
                    ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_TAB,
                    ecodes.KEY_BACKSPACE, ecodes.KEY_ESC,

                    # Punctuation and symbols
                    ecodes.KEY_MINUS, ecodes.KEY_EQUAL, ecodes.KEY_LEFTBRACE,
                    ecodes.KEY_RIGHTBRACE, ecodes.KEY_BACKSLASH, ecodes.KEY_SEMICOLON,
                    ecodes.KEY_APOSTROPHE, ecodes.KEY_GRAVE, ecodes.KEY_COMMA,
                    ecodes.KEY_DOT, ecodes.KEY_SLASH,

                    # Mouse buttons (for middle-click paste from PRIMARY selection)
                    ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE,
                ]
            }

            # Create the virtual keyboard
            self._device = UInput(
                capabilities,
                name='speech-to-text-virtual-keyboard',
                bustype=ecodes.BUS_USB,
                vendor=0x1234,  # Arbitrary vendor ID
                product=0x5678,  # Arbitrary product ID
                version=1
            )

            logger.info("Virtual keyboard device created successfully")

        except PermissionError as e:
            logger.error(
                "Permission denied accessing /dev/uinput. "
                "User must be in 'input' group. "
                "Run: sudo usermod -aG input $USER && logout/login"
            )
            raise PermissionError(
                "Cannot access /dev/uinput. User must be in 'input' group."
            ) from e

        except OSError as e:
            if 'No such file or directory' in str(e):
                logger.error(
                    "/dev/uinput not found. "
                    "Load uinput kernel module: sudo modprobe uinput"
                )
                raise OSError(
                    "/dev/uinput not found. Run: sudo modprobe uinput"
                ) from e
            raise

    def _send_key_event(self, keycode: int, press: bool):
        """Send a single key event (press or release).

        Args:
            keycode: Linux keycode (from ecodes).
            press: True for key press, False for key release.
        """
        if self._device is None:
            raise RuntimeError("Virtual keyboard device not initialized")

        # Send key press (1) or release (0) event
        self._device.write(ecodes.EV_KEY, keycode, 1 if press else 0)
        # Synchronize the event
        self._device.syn()

    def _type_char_sync(self, char: str, layout: Optional[str] = None):
        """Type a single character synchronously.

        Args:
            char: Single character to type.
            layout: Optional layout override. If None, uses detected layout.
        """
        # Get keycode and modifiers for this character
        keycode, modifiers = self._mapper.get_keycode_for_char(char, layout)

        # Press modifier keys first
        for mod in modifiers:
            self._send_key_event(mod, press=True)
            time.sleep(self.key_delay_sec)

        # Press main key
        self._send_key_event(keycode, press=True)
        time.sleep(self.key_delay_sec)

        # Release main key
        self._send_key_event(keycode, press=False)
        time.sleep(self.key_delay_sec)

        # Release modifier keys in reverse order
        for mod in reversed(modifiers):
            self._send_key_event(mod, press=False)
            time.sleep(self.key_delay_sec)

    async def _type_char_async(self, char: str, layout: Optional[str] = None):
        """Type a single character asynchronously.

        Args:
            char: Single character to type.
            layout: Optional layout override. If None, uses detected layout.
        """
        # Get keycode and modifiers for this character
        keycode, modifiers = self._mapper.get_keycode_for_char(char, layout)

        # Press modifier keys first
        for mod in modifiers:
            self._send_key_event(mod, press=True)
            await asyncio.sleep(self.key_delay_sec)

        # Press main key
        self._send_key_event(keycode, press=True)
        await asyncio.sleep(self.key_delay_sec)

        # Release main key
        self._send_key_event(keycode, press=False)
        await asyncio.sleep(self.key_delay_sec)

        # Release modifier keys in reverse order
        for mod in reversed(modifiers):
            self._send_key_event(mod, press=False)
            await asyncio.sleep(self.key_delay_sec)

    def type_text_sync(self, text: str, layout: Optional[str] = None):
        """Type text synchronously (blocking).

        Args:
            text: Text to type. May contain newlines and tabs.
            layout: Optional layout override. If None, auto-detects layout
                for each character.

        Example:
            >>> keyboard = UInputKeyboard()
            >>> keyboard.type_text_sync("Hello, world!")
        """
        if not text:
            return

        logger.debug(f"Typing text (sync): {repr(text[:50])}...")

        for char in text:
            self._type_char_sync(char, layout)

        logger.debug("Text typing completed (sync)")

    async def type_text(self, text: str, layout: Optional[str] = None):
        """Type text asynchronously (non-blocking).

        Args:
            text: Text to type. May contain newlines and tabs.
            layout: Optional layout override. If None, auto-detects layout
                for each character.

        Example:
            >>> keyboard = UInputKeyboard()
            >>> await keyboard.type_text("Hello, світ!")
        """
        if not text:
            return

        logger.debug(f"Typing text (async): {repr(text[:50])}...")

        for char in text:
            await self._type_char_async(char, layout)

        logger.debug("Text typing completed (async)")

    def close(self):
        """Close and cleanup the virtual keyboard device.

        This should be called when done using the keyboard to properly
        release system resources.
        """
        if self._device is not None:
            self._device.close()
            self._device = None
            logger.info("Virtual keyboard device closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup device."""
        self.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup device."""
        self.close()

    def __del__(self):
        """Destructor - ensure device is closed."""
        self.close()


async def test_uinput_keyboard():
    """Test function for UInputKeyboard.

    This function demonstrates basic usage and can be run standalone
    to verify the virtual keyboard works correctly.
    """
    print("Testing UInputKeyboard...")
    print("Text will be typed in 3 seconds. Focus a text editor!")

    await asyncio.sleep(3)

    async with UInputKeyboard(key_delay_ms=10) as keyboard:
        # Test English text
        await keyboard.type_text("Hello from UInputKeyboard!\n")
        await asyncio.sleep(0.5)

        # Test Ukrainian text (if layout supports it)
        await keyboard.type_text("Привіт, світ!\n")
        await asyncio.sleep(0.5)

        # Test mixed text
        await keyboard.type_text("Mixed: English + Українська\n")

    print("Test complete!")


if __name__ == '__main__':
    # Allow running this module directly for testing
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(test_uinput_keyboard())
