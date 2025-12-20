"""Multi-device hotkey listener supporting keyboard and mouse buttons simultaneously."""

import asyncio
import logging
import time
from typing import Callable, Optional, Awaitable, List, Dict
from evdev import InputDevice, ecodes, list_devices

logger = logging.getLogger(__name__)


class MultiHotkeyListener:
    """
    Async hotkey listener that monitors multiple devices for multiple trigger keys.

    Allows using both keyboard keys (e.g., KEY_RIGHTCTRL) and mouse buttons (e.g., BTN_FORWARD)
    as triggers for the same action.
    """

    def __init__(
        self,
        trigger_keys: List[str],  # e.g., ["KEY_RIGHTCTRL", "BTN_FORWARD"]
        double_tap_keys: Optional[List[str]] = None,  # Keys that require double-tap
        on_press: Optional[Callable[[], Awaitable[None]]] = None,
        on_release: Optional[Callable[[], Awaitable[None]]] = None,
        enable_double_tap: bool = False,  # Legacy: apply to all keys
        double_tap_timeout_ms: int = 300,
    ):
        """
        Initialize multi-device hotkey listener.

        Args:
            trigger_keys: List of key names to monitor (e.g., ["KEY_RIGHTCTRL", "BTN_FORWARD"])
            double_tap_keys: List of keys that require double-tap (None = use enable_double_tap)
            on_press: Async callback for key press
            on_release: Async callback for key release
            enable_double_tap: If True and double_tap_keys is None, require double-tap for all keys
            double_tap_timeout_ms: Max time between taps in milliseconds
        """
        self.trigger_keys = trigger_keys
        self.on_press = on_press
        self.on_release = on_release
        self.double_tap_timeout_ms = double_tap_timeout_ms

        # Determine which keys require double-tap
        if double_tap_keys is not None:
            self.double_tap_key_names = double_tap_keys
        elif enable_double_tap:
            self.double_tap_key_names = trigger_keys
        else:
            self.double_tap_key_names = []

        # Convert key names to codes
        self.key_codes = []
        self.double_tap_codes = set()

        for key_name in trigger_keys:
            code = getattr(ecodes, key_name, None)
            if code is None:
                logger.warning(f"Unknown key name: {key_name}")
            else:
                self.key_codes.append(code)
                logger.debug(f"Added trigger: {key_name} (code: {code})")

                # Check if this key requires double-tap
                if key_name in self.double_tap_key_names:
                    self.double_tap_codes.add(code)
                    logger.info(f"  → {key_name} requires double-tap")
                else:
                    logger.info(f"  → {key_name} is single-tap mode")

        self._devices: List[InputDevice] = []
        self._running = False
        self._key_held: Dict[int, bool] = {}  # Track each key separately
        self._last_release_time: Dict[int, float] = {}  # Track per key
        self._double_tap_armed: Dict[int, bool] = {}  # Track per key
        self._tasks = []

        # Initialize tracking for each key
        for code in self.key_codes:
            self._key_held[code] = False
            self._last_release_time[code] = 0.0
            self._double_tap_armed[code] = False

    def _find_devices_with_keys(self) -> List[tuple]:
        """
        Find all input devices that have at least one of our trigger keys.

        Returns:
            List of (device_path, device_name, [key_codes]) tuples
        """
        matching_devices = []

        for path in list_devices():
            try:
                device = InputDevice(path)
                caps = device.capabilities()

                if ecodes.EV_KEY not in caps:
                    continue

                available_keys = caps[ecodes.EV_KEY]
                matching_keys = [k for k in self.key_codes if k in available_keys]

                if matching_keys:
                    matching_devices.append((path, device.name, matching_keys))
                    logger.info(f"Found device: {device.name} at {path} with keys: {matching_keys}")

            except (PermissionError, OSError) as e:
                logger.debug(f"Cannot access {path}: {e}")
                continue

        return matching_devices

    async def _monitor_device(self, device_path: str, device_name: str, key_codes: List[int]):
        """Monitor a single device for key events."""
        try:
            device = InputDevice(device_path)
            self._devices.append(device)

            logger.info(f"Monitoring {device_name} ({device_path}) for keys: {key_codes}")

            async for event in device.async_read_loop():
                if not self._running:
                    break

                if event.type == ecodes.EV_KEY and event.code in key_codes:
                    logger.debug(f"Event detected: device={device_name}, code={event.code}, value={event.value}")
                    await self._handle_key_event(event.code, event.value)

        except asyncio.CancelledError:
            logger.debug(f"Monitor cancelled for {device_name}")
        except Exception as e:
            logger.error(f"Error monitoring {device_name}: {e}")
        finally:
            try:
                device.close()
            except:
                pass

    async def _handle_key_event(self, key_code: int, value: int):
        """Handle key press/release events with per-key double-tap support."""
        # Check if this specific key requires double-tap
        requires_double_tap = key_code in self.double_tap_codes

        if value == 1:  # Key pressed
            if not self._key_held[key_code]:
                self._key_held[key_code] = True

                if requires_double_tap:
                    # Check if this is a double-tap
                    current_time = time.time()
                    time_since_last_release = (current_time - self._last_release_time[key_code]) * 1000

                    if time_since_last_release < self.double_tap_timeout_ms and self._last_release_time[key_code] > 0:
                        # Double-tap detected!
                        self._double_tap_armed[key_code] = True
                        logger.info(f"Double-tap detected on key {key_code} - hold to record")

                        if self.on_press:
                            try:
                                await self.on_press()
                            except Exception as e:
                                logger.error(f"Error in on_press callback: {e}")
                    else:
                        logger.debug(f"First tap on key {key_code}")
                else:
                    # No double-tap required - trigger immediately
                    logger.debug(f"Key {key_code} pressed (single-tap mode)")
                    if self.on_press:
                        try:
                            await self.on_press()
                        except Exception as e:
                            logger.error(f"Error in on_press callback: {e}")

        elif value == 0:  # Key released
            if self._key_held[key_code]:
                self._key_held[key_code] = False
                current_time = time.time()

                if requires_double_tap:
                    if self._double_tap_armed[key_code]:
                        if self.on_release:
                            try:
                                await self.on_release()
                            except Exception as e:
                                logger.error(f"Error in on_release callback: {e}")
                        self._double_tap_armed[key_code] = False

                    self._last_release_time[key_code] = current_time
                else:
                    # No double-tap required - trigger immediately
                    logger.debug(f"Key {key_code} released (single-tap mode)")
                    if self.on_release:
                        try:
                            await self.on_release()
                        except Exception as e:
                            logger.error(f"Error in on_release callback: {e}")

    async def start(self):
        """Start listening for hotkey events on all matching devices."""
        if not self.key_codes:
            raise RuntimeError("No valid trigger keys configured")

        # Find all devices that have our trigger keys
        matching_devices = self._find_devices_with_keys()

        if not matching_devices:
            raise RuntimeError(f"No devices found with any of the trigger keys: {self.trigger_keys}")

        self._running = True

        # Start monitoring each device in parallel
        for device_path, device_name, key_codes in matching_devices:
            task = asyncio.create_task(self._monitor_device(device_path, device_name, key_codes))
            self._tasks.append(task)

        # Wait for all tasks
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Multi-listener cancelled")
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Clean up resources."""
        self._running = False

        # Cancel all monitoring tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close all devices
        for device in self._devices:
            try:
                device.close()
            except:
                pass

        self._devices.clear()
        self._tasks.clear()

    def stop(self):
        """Stop listening."""
        self._running = False
        logger.info("Stopping multi-hotkey listener")

        # Cancel all monitoring tasks to break out of async_read_loop()
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Close devices to release file handles immediately
        for device in self._devices:
            try:
                device.close()
            except:
                pass

    @property
    def is_running(self) -> bool:
        """Check if listener is running."""
        return self._running

    @property
    def is_any_key_held(self) -> bool:
        """Check if any hotkey is currently held down."""
        return any(self._key_held.values())
