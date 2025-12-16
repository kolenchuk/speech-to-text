#!/usr/bin/env python3
"""Display server abstraction for text input automation.

This module provides a unified interface for typing text across different
display servers (X11 and Wayland) using various tools with graceful fallback.

Tool Hierarchy:
    Wayland: wtype → xdotool → ydotool → python-uinput
    X11:     xdotool → python-uinput → ydotool

The abstraction layer automatically detects the display server and selects
the best available tool, falling back to alternatives if the preferred
tool is unavailable.

Supported Tools:
    - wtype: Wayland tool with excellent Unicode support (preferred)
    - xdotool: X11 tool with good Unicode support
    - ydotool: Universal tool but poor Unicode/Cyrillic support
    - python-uinput: Pure Python fallback with full Unicode support

All tools provide the same async interface for consistency.
"""

import asyncio
import logging
import os
import shutil
import subprocess
from typing import Optional

from .uinput_keyboard import UInputKeyboard

logger = logging.getLogger(__name__)


class TextInput:
    """Unified text input interface across display servers.

    This class automatically detects the display server type and selects
    the best available text input tool, with fallback to alternatives.

    Example:
        >>> text_input = TextInput(key_delay_ms=10)
        >>> await text_input.type_text("Hello, world!")
    """

    def __init__(self, display_server: Optional[str] = None, key_delay_ms: int = 10):
        """Initialize text input handler.

        Args:
            display_server: Override display server detection.
                Options: "x11", "wayland", or None for auto-detect.
            key_delay_ms: Delay between key events for python-uinput fallback.
                Only used if python-uinput is selected.

        Raises:
            RuntimeError: If no suitable text input tool is available.
        """
        self.key_delay_ms = key_delay_ms
        self._uinput_keyboard: Optional[UInputKeyboard] = None

        # Detect display server
        if display_server:
            self.display_server = display_server.lower()
        else:
            self.display_server = os.environ.get("XDG_SESSION_TYPE", "x11").lower()

        logger.info(f"Display server: {self.display_server}")

        # Select tool based on display server and availability
        self.tool = self._select_tool()
        logger.info(f"Selected text input tool: {self.tool}")

        # Initialize python-uinput if selected
        if self.tool == "python-uinput":
            self._init_uinput()

    def _select_tool(self) -> str:
        """Select the best available text input tool.

        Returns:
            str: Selected tool name.

        Raises:
            RuntimeError: If no suitable tool is available.
        """
        # Define tool preference order based on display server
        if self.display_server == "wayland":
            tool_order = ["wtype", "xdotool", "ydotool", "python-uinput"]
        else:  # x11 or unknown
            tool_order = ["xdotool", "python-uinput", "ydotool"]

        # Check each tool in order
        for tool in tool_order:
            if self._is_tool_available(tool):
                return tool

        # No tool available
        raise RuntimeError(
            f"No text input tool available for {self.display_server}. "
            f"Tried: {', '.join(tool_order)}. "
            "Install one of: wtype (Wayland), xdotool (X11), or ensure user is in 'input' group for python-uinput."
        )

    def _is_tool_available(self, tool: str) -> bool:
        """Check if a text input tool is available.

        Args:
            tool: Tool name to check.

        Returns:
            bool: True if tool is available and usable.
        """
        if tool == "python-uinput":
            # Check if we can access /dev/uinput
            return os.path.exists('/dev/uinput') and os.access('/dev/uinput', os.W_OK)

        # Check if external tool is installed
        return shutil.which(tool) is not None

    def _init_uinput(self):
        """Initialize python-uinput keyboard.

        Raises:
            RuntimeError: If initialization fails.
        """
        try:
            self._uinput_keyboard = UInputKeyboard(key_delay_ms=self.key_delay_ms)
            logger.info("Python uinput keyboard initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize python-uinput: {e}")
            raise RuntimeError(f"Failed to initialize python-uinput: {e}") from e

    async def type_text(self, text: str) -> bool:
        """Type text using the selected tool (async interface).

        Automatically falls back to next available tool if primary fails.

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

        # Build fallback chain starting with selected tool
        if self.display_server == "wayland":
            tool_order = ["wtype", "xdotool", "ydotool", "python-uinput"]
        else:  # X11
            tool_order = ["xdotool", "python-uinput", "ydotool"]

        # Move primary tool to front
        if self.tool in tool_order:
            tool_order.remove(self.tool)
            tool_order.insert(0, self.tool)

        # Try each tool in order
        for tool in tool_order:
            if not self._is_tool_available(tool):
                logger.debug(f"Tool '{tool}' not available, skipping")
                continue

            logger.debug(f"Trying to type text with {tool}: {repr(text[:50])}...")

            try:
                if tool == "python-uinput":
                    await self._type_with_uinput(text)
                elif tool == "wtype":
                    await self._type_with_wtype(text)
                elif tool == "xdotool":
                    await self._type_with_xdotool(text)
                elif tool == "ydotool":
                    await self._type_with_ydotool(text)
                else:
                    continue

                logger.info(f"Text typing completed successfully with {tool}")
                return True

            except Exception as e:
                logger.error(f"Failed to type text with {tool}: {e}")
                logger.debug(f"Falling back to next tool...")
                continue

        # All tools failed
        logger.error("All text input tools failed")
        return False

    def type_text_sync(self, text: str) -> bool:
        """Type text using the selected tool (synchronous interface).

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

        logger.debug(f"Typing text (sync) with {self.tool}: {repr(text[:50])}...")

        try:
            if self.tool == "python-uinput":
                self._type_with_uinput_sync(text)
            elif self.tool == "wtype":
                self._type_with_wtype_sync(text)
            elif self.tool == "xdotool":
                self._type_with_xdotool_sync(text)
            elif self.tool == "ydotool":
                self._type_with_ydotool_sync(text)
            else:
                logger.error(f"Unknown tool: {self.tool}")
                return False

            logger.debug("Text typing completed successfully (sync)")
            return True

        except Exception as e:
            logger.error(f"Failed to type text with {self.tool}: {e}")
            return False

    async def _type_with_uinput(self, text: str):
        """Type text using python-uinput (async).

        Args:
            text: Text to type.
        """
        if self._uinput_keyboard is None:
            self._init_uinput()

        # Invalidate layout cache to detect current layout (important on Wayland)
        self._uinput_keyboard._mapper.invalidate_layout_cache()
        await self._uinput_keyboard.type_text(text)

    def _type_with_uinput_sync(self, text: str):
        """Type text using python-uinput (sync).

        Args:
            text: Text to type.
        """
        if self._uinput_keyboard is None:
            self._init_uinput()

        # Invalidate layout cache to detect current layout (important on Wayland)
        self._uinput_keyboard._mapper.invalidate_layout_cache()
        self._uinput_keyboard.type_text_sync(text)

    async def _type_with_wtype(self, text: str):
        """Type text using wtype (Wayland).

        Args:
            text: Text to type.
        """
        # wtype takes text as stdin or as argument
        # Using argument is simpler
        proc = await asyncio.create_subprocess_exec(
            'wtype',
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"wtype failed: {stderr.decode()}")

    def _type_with_wtype_sync(self, text: str):
        """Type text using wtype (Wayland) synchronously.

        Args:
            text: Text to type.
        """
        result = subprocess.run(
            ['wtype', text],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"wtype failed: {result.stderr}")

    async def _type_with_xdotool(self, text: str):
        """Type text using xdotool (X11).

        Args:
            text: Text to type.
        """
        # xdotool uses -- to separate options from text
        proc = await asyncio.create_subprocess_exec(
            'xdotool',
            'type',
            '--',
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"xdotool failed: {stderr.decode()}")

    def _type_with_xdotool_sync(self, text: str):
        """Type text using xdotool (X11) synchronously.

        Args:
            text: Text to type.
        """
        result = subprocess.run(
            ['xdotool', 'type', '--', text],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"xdotool failed: {result.stderr}")

    async def _type_with_ydotool(self, text: str):
        """Type text using ydotool (universal but slower).

        Args:
            text: Text to type.
        """
        proc = await asyncio.create_subprocess_exec(
            'ydotool',
            'type',
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ydotool failed: {stderr.decode()}")

    def _type_with_ydotool_sync(self, text: str):
        """Type text using ydotool (universal but slower) synchronously.

        Args:
            text: Text to type.
        """
        result = subprocess.run(
            ['ydotool', 'type', text],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"ydotool failed: {result.stderr}")

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
