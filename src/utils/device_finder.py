"""Keyboard device finder for evdev."""

import logging
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


def find_keyboard_device(preferred_path: Optional[str] = None) -> Optional[str]:
    """
    Find a suitable keyboard device for hotkey detection.

    Args:
        preferred_path: Preferred device path (e.g., /dev/input/event4)

    Returns:
        Path to keyboard device or None if not found
    """
    try:
        from evdev import InputDevice, ecodes, list_devices
    except ImportError:
        logger.error("evdev not installed. Run: pip install evdev")
        return None

    # If preferred path is specified and exists, use it
    if preferred_path:
        if Path(preferred_path).exists():
            try:
                dev = InputDevice(preferred_path)
                logger.info(f"Using configured device: {preferred_path} ({dev.name})")
                dev.close()
                return preferred_path
            except Exception as e:
                logger.warning(f"Could not open {preferred_path}: {e}")
        else:
            logger.warning(f"Configured device not found: {preferred_path}")

    # Auto-detect keyboard
    logger.info("Auto-detecting keyboard device...")

    keyboards = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()

            # Check if device has key capabilities
            if ecodes.EV_KEY not in caps:
                dev.close()
                continue

            keys = caps[ecodes.EV_KEY]

            # Check for typical keyboard keys (A-Z and control keys)
            has_letters = ecodes.KEY_A in keys and ecodes.KEY_Z in keys
            has_ctrl = ecodes.KEY_LEFTCTRL in keys or ecodes.KEY_RIGHTCTRL in keys

            if has_letters and has_ctrl:
                keyboards.append({
                    "path": path,
                    "name": dev.name,
                    "phys": dev.phys or "",
                })
                logger.debug(f"Found keyboard: {path} - {dev.name}")

            dev.close()
        except Exception as e:
            logger.debug(f"Could not check {path}: {e}")

    if not keyboards:
        logger.error("No keyboard device found")
        return None

    # Prefer physical keyboards over virtual ones
    # Physical keyboards often have "usb" or "i8042" in phys
    for kbd in keyboards:
        if "usb" in kbd["phys"].lower() or "i8042" in kbd["phys"].lower():
            logger.info(f"Selected physical keyboard: {kbd['path']} ({kbd['name']})")
            return kbd["path"]

    # Fall back to first found keyboard
    selected = keyboards[0]
    logger.info(f"Selected keyboard: {selected['path']} ({selected['name']})")
    return selected["path"]


def list_keyboard_devices() -> List[Dict[str, str]]:
    """
    List all available keyboard devices.

    Returns:
        List of dictionaries with device info
    """
    try:
        from evdev import InputDevice, ecodes, list_devices
    except ImportError:
        logger.error("evdev not installed")
        return []

    keyboards = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()

            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                has_letters = ecodes.KEY_A in keys and ecodes.KEY_Z in keys
                has_ctrl = ecodes.KEY_LEFTCTRL in keys or ecodes.KEY_RIGHTCTRL in keys

                if has_letters and has_ctrl:
                    keyboards.append({
                        "path": path,
                        "name": dev.name,
                        "phys": dev.phys or "N/A",
                    })
            dev.close()
        except Exception:
            pass

    return keyboards


def get_key_code(key_name: str) -> Optional[int]:
    """
    Get evdev key code from key name.

    Args:
        key_name: Key name (e.g., 'KEY_RIGHTCTRL')

    Returns:
        Key code or None if not found
    """
    try:
        from evdev import ecodes
        return getattr(ecodes, key_name, None)
    except ImportError:
        return None
