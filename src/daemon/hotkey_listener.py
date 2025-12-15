"""Hotkey listener using evdev for keyboard monitoring."""

import asyncio
import logging
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


class HotkeyListener:
    """
    Async hotkey listener using evdev.

    Monitors a keyboard device for press/release of a specific key.
    """

    def __init__(
        self,
        key_code: int,
        device_path: Optional[str] = None,
        on_press: Optional[Callable[[], Awaitable[None]]] = None,
        on_release: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """
        Initialize hotkey listener.

        Args:
            key_code: evdev key code to monitor (e.g., 97 for KEY_RIGHTCTRL)
            device_path: Path to input device (auto-detect if None)
            on_press: Async callback for key press
            on_release: Async callback for key release
        """
        self.key_code = key_code
        self.device_path = device_path
        self.on_press = on_press
        self.on_release = on_release
        self._device = None
        self._running = False
        self._key_held = False

    def _find_device(self) -> str:
        """Find keyboard device if not specified."""
        if self.device_path:
            return self.device_path

        from ..utils.device_finder import find_keyboard_device
        device = find_keyboard_device()
        if not device:
            raise RuntimeError("No keyboard device found")
        return device

    async def start(self):
        """Start listening for hotkey events."""
        try:
            from evdev import InputDevice, ecodes
        except ImportError:
            raise RuntimeError("evdev not installed. Run: pip install evdev")

        device_path = self._find_device()
        self._device = InputDevice(device_path)
        self._running = True

        logger.info(f"Listening for key {self.key_code} on {device_path} ({self._device.name})")

        try:
            async for event in self._device.async_read_loop():
                if not self._running:
                    break

                if event.type == ecodes.EV_KEY and event.code == self.key_code:
                    if event.value == 1:  # Key pressed
                        if not self._key_held:
                            self._key_held = True
                            logger.debug(f"Key {self.key_code} pressed")
                            if self.on_press:
                                try:
                                    await self.on_press()
                                except Exception as e:
                                    logger.error(f"Error in on_press callback: {e}")

                    elif event.value == 0:  # Key released
                        if self._key_held:
                            self._key_held = False
                            logger.debug(f"Key {self.key_code} released")
                            if self.on_release:
                                try:
                                    await self.on_release()
                                except Exception as e:
                                    logger.error(f"Error in on_release callback: {e}")

                    # value == 2 is key repeat, ignore it

        except asyncio.CancelledError:
            logger.info("Listener cancelled")
        finally:
            self._running = False
            if self._device:
                self._device.close()
                self._device = None

    def stop(self):
        """Stop listening."""
        self._running = False
        logger.info("Stopping hotkey listener")

    @property
    def is_running(self) -> bool:
        """Check if listener is running."""
        return self._running

    @property
    def is_key_held(self) -> bool:
        """Check if the hotkey is currently held down."""
        return self._key_held


async def test_hotkey_listener():
    """Test the hotkey listener interactively."""
    from evdev import ecodes

    print("Testing hotkey listener...")
    print("Press and release Right Ctrl to test. Press Ctrl+C to exit.")
    print()

    async def on_press():
        print(">>> KEY PRESSED - Recording would start")

    async def on_release():
        print("<<< KEY RELEASED - Recording would stop")

    listener = HotkeyListener(
        key_code=ecodes.KEY_RIGHTCTRL,
        on_press=on_press,
        on_release=on_release,
    )

    try:
        await listener.start()
    except KeyboardInterrupt:
        print("\nTest stopped.")
        listener.stop()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__file__).rsplit("/", 3)[0])

    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(test_hotkey_listener())
