"""Hotkey listener using evdev for keyboard monitoring."""

import asyncio
import logging
import time
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


class HotkeyListener:
    """
    Async hotkey listener using evdev.

    Monitors a keyboard device for press/release of a specific key.
    Supports double-tap detection to avoid conflicts with key combinations.
    """

    def __init__(
        self,
        key_code: int,
        device_path: Optional[str] = None,
        on_press: Optional[Callable[[], Awaitable[None]]] = None,
        on_release: Optional[Callable[[], Awaitable[None]]] = None,
        enable_double_tap: bool = False,
        double_tap_timeout_ms: int = 300,
    ):
        """
        Initialize hotkey listener.

        Args:
            key_code: evdev key code to monitor (e.g., 97 for KEY_RIGHTCTRL)
            device_path: Path to input device (auto-detect if None)
            on_press: Async callback for key press
            on_release: Async callback for key release
            enable_double_tap: If True, require double-tap to activate (prevents conflicts)
            double_tap_timeout_ms: Max time between taps in milliseconds
        """
        self.key_code = key_code
        self.device_path = device_path
        self.on_press = on_press
        self.on_release = on_release
        self.enable_double_tap = enable_double_tap
        self.double_tap_timeout_ms = double_tap_timeout_ms
        self._device = None
        self._running = False
        self._key_held = False
        self._last_release_time = 0.0
        self._double_tap_armed = False

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

                            if self.enable_double_tap:
                                # Check if this is a double-tap
                                current_time = time.time()
                                time_since_last_release = (current_time - self._last_release_time) * 1000  # Convert to ms

                                if time_since_last_release < self.double_tap_timeout_ms and self._last_release_time > 0:
                                    # Double-tap detected! Arm the listener
                                    self._double_tap_armed = True
                                    logger.debug(f"Double-tap detected ({time_since_last_release:.0f}ms since last release)")
                                    logger.info("Double-tap detected - hold to record")

                                    # Trigger on_press callback now that we're armed
                                    if self.on_press:
                                        try:
                                            await self.on_press()
                                        except Exception as e:
                                            logger.error(f"Error in on_press callback: {e}")
                                else:
                                    # First tap - just wait for potential second tap
                                    logger.debug(f"First tap detected (time since last: {time_since_last_release:.0f}ms)")
                            else:
                                # Double-tap disabled - trigger immediately (original behavior)
                                logger.debug(f"Key {self.key_code} pressed")
                                if self.on_press:
                                    try:
                                        await self.on_press()
                                    except Exception as e:
                                        logger.error(f"Error in on_press callback: {e}")

                    elif event.value == 0:  # Key released
                        if self._key_held:
                            self._key_held = False
                            current_time = time.time()

                            if self.enable_double_tap:
                                # Only trigger on_release if we were armed (double-tap happened)
                                if self._double_tap_armed:
                                    logger.debug(f"Key {self.key_code} released (armed)")
                                    if self.on_release:
                                        try:
                                            await self.on_release()
                                        except Exception as e:
                                            logger.error(f"Error in on_release callback: {e}")
                                    # Disarm after release
                                    self._double_tap_armed = False
                                else:
                                    logger.debug(f"Key {self.key_code} released (not armed, awaiting second tap)")

                                # Always update last release time
                                self._last_release_time = current_time
                            else:
                                # Double-tap disabled - trigger immediately (original behavior)
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
    import sys

    # Check if user wants to test double-tap mode
    enable_double_tap = "--double-tap" in sys.argv

    print("Testing hotkey listener...")
    if enable_double_tap:
        print("DOUBLE-TAP MODE: Tap Right Ctrl twice quickly, then hold on second tap.")
        print("Single Ctrl press/release will be ignored (use for Ctrl+Insert, etc.)")
    else:
        print("SINGLE-TAP MODE: Press and hold Right Ctrl to test.")
    print("Press Ctrl+C to exit.")
    print()

    async def on_press():
        print(">>> KEY PRESSED - Recording would start")

    async def on_release():
        print("<<< KEY RELEASED - Recording would stop")

    listener = HotkeyListener(
        key_code=ecodes.KEY_RIGHTCTRL,
        on_press=on_press,
        on_release=on_release,
        enable_double_tap=enable_double_tap,
        double_tap_timeout_ms=300,
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
