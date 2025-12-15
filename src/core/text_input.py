"""Text input automation module for X11 and Wayland."""

import asyncio
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class TextInput:
    """Text automation using wtype (Wayland) or xdotool (X11)."""

    def __init__(self, display_server: Optional[str] = None, tool: Optional[str] = None):
        """
        Initialize text input handler.

        Args:
            display_server: Force display server type ('x11' or 'wayland').
                          Auto-detected if None.
            tool: Force specific tool ('ydotool', 'wtype', 'xdotool').
                 Auto-detected based on display server if None.
        """
        if display_server:
            self.display_server = display_server
        else:
            self.display_server = os.environ.get("XDG_SESSION_TYPE", "x11")

        # Use specified tool or auto-detect
        if tool:
            self.tool = tool
        else:
            # Use wtype for Wayland (supports Unicode/Cyrillic)
            # ydotool 0.1.8 in Ubuntu 24.04 doesn't support Unicode
            self.tool = "wtype" if self.display_server == "wayland" else "xdotool"
        logger.info(f"Display server: {self.display_server}, using: {self.tool}")

    def _check_tool_available(self, tool: str) -> bool:
        """Check if the text automation tool is available."""
        result = subprocess.run(
            ["which", tool],
            capture_output=True,
        )
        if result.returncode != 0:
            logger.error(f"{tool} not found")
            if tool == "wtype":
                logger.error("Install with: sudo apt install wtype")
            else:
                logger.error("Install with: sudo apt install xdotool")
            return False
        return True

    def type_text_sync(self, text: str) -> bool:
        """
        Type text into active application (synchronous).

        Args:
            text: Text to type

        Returns:
            True if successful
        """
        if not text:
            logger.warning("No text to type")
            return False

        if not self._check_tool_available(self.tool):
            return False

        logger.info(f"Typing text using {self.tool}...")

        try:
            if self.tool == "wtype":
                # wtype takes text directly as argument
                cmd = ["wtype", text]
            elif self.tool == "ydotool":
                # ydotool type command
                cmd = ["ydotool", "type", text]
            else:
                cmd = ["xdotool", "type", "--", text]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("Text typed successfully")
                return True
            else:
                logger.error(f"Typing failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Typing timed out")
            return False
        except Exception as e:
            logger.error(f"Typing error: {e}")
            return False

    async def type_text(self, text: str) -> bool:
        """
        Type text into active application (async).

        Args:
            text: Text to type

        Returns:
            True if successful
        """
        if not text:
            logger.warning("No text to type")
            return False

        if not self._check_tool_available(self.tool):
            return False

        logger.info(f"Typing text using {self.tool}...")

        try:
            if self.tool == "wtype":
                cmd = ["wtype", text]
            elif self.tool == "ydotool":
                cmd = ["ydotool", "type", text]
            else:
                cmd = ["xdotool", "type", "--", text]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode == 0:
                logger.info("Text typed successfully")
                return True
            else:
                logger.error(f"Typing failed: {stderr.decode()}")
                return False

        except asyncio.TimeoutError:
            logger.error("Typing timed out")
            return False
        except Exception as e:
            logger.error(f"Typing error: {e}")
            return False

    @staticmethod
    def detect_display_server() -> str:
        """Detect the current display server."""
        return os.environ.get("XDG_SESSION_TYPE", "x11")
