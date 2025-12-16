#!/usr/bin/env python3
"""Text input using python-uinput.

This module provides a unified interface for typing text on both X11 and Wayland
using python-uinput, which works at the kernel level and is display-server agnostic.

Requirements:
    - User must be in 'input' group
    - /dev/uinput must be accessible
"""

import asyncio
import logging
import os
from typing import Optional

from .uinput_keyboard import UInputKeyboard

logger = logging.getLogger(__name__)


class TextInput:
    """Text input using python-uinput (works on both X11 and Wayland).

    Example:
        >>> text_input = TextInput(key_delay_ms=10)
        >>> await text_input.type_text("Hello, world!")
    """

    def __init__(self, display_server: Optional[str] = None, key_delay_ms: int = 10):
        """Initialize text input handler.

        Args:
            display_server: Ignored (kept for API compatibility).
            key_delay_ms: Delay between key events in milliseconds.

        Raises:
            RuntimeError: If uinput is not accessible.
        """
        self.key_delay_ms = key_delay_ms
        self._uinput_keyboard: Optional[UInputKeyboard] = None
        self.tool = "python-uinput"

        # Detect display server (for logging only)
        self.display_server = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        logger.info(f"Display server: {self.display_server}")

        # Check uinput availability
        if not self._is_uinput_available():
            raise RuntimeError(
                "python-uinput not available. "
                "Ensure user is in 'input' group and /dev/uinput is accessible. "
                "Run: sudo usermod -aG input $USER && logout/login"
            )

        # Initialize uinput keyboard
        self._init_uinput()
        logger.info("Using python-uinput for text input")

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

    async def type_text(self, text: str) -> bool:
        """Type text using python-uinput (async interface).

        Args:
            text: Text to type. May contain newlines and special characters.

        Returns:
            bool: True if successful, False on error.

        Example:
            >>> text_input = TextInput()
            >>> await text_input.type_text("Hello, світ!")
        """
        if not text:
            logger.warning("Empty text provided to type_text()")
            return True

        logger.debug(f"Typing text: {repr(text[:50])}...")

        try:
            # Invalidate layout cache to detect current layout
            self._uinput_keyboard._mapper.invalidate_layout_cache()
            await self._uinput_keyboard.type_text(text)
            logger.info("Text typing completed successfully with python-uinput")
            return True
        except Exception as e:
            logger.error(f"Failed to type text: {e}")
            return False

    def type_text_sync(self, text: str) -> bool:
        """Type text using python-uinput (synchronous interface).

        Args:
            text: Text to type. May contain newlines and special characters.

        Returns:
            bool: True if successful, False on error.

        Example:
            >>> text_input = TextInput()
            >>> text_input.type_text_sync("Hello, world!")
        """
        if not text:
            logger.warning("Empty text provided to type_text_sync()")
            return True

        logger.debug(f"Typing text (sync): {repr(text[:50])}...")

        try:
            # Invalidate layout cache to detect current layout
            self._uinput_keyboard._mapper.invalidate_layout_cache()
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
