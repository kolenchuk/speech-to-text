#!/usr/bin/env python3
"""Find mouse button event codes for speech-to-text configuration."""

import asyncio
from evdev import InputDevice, categorize, ecodes, list_devices


async def find_mouse_and_buttons():
    """List all input devices and wait for button press to identify code."""

    print("=== Available Input Devices ===\n")

    devices = []
    for path in list_devices():
        try:
            device = InputDevice(path)
            caps = device.capabilities()

            # Check if device has mouse buttons
            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                has_mouse_buttons = any(
                    btn in keys for btn in [
                        ecodes.BTN_LEFT,
                        ecodes.BTN_RIGHT,
                        ecodes.BTN_MIDDLE,
                        ecodes.BTN_SIDE,
                        ecodes.BTN_EXTRA,
                        ecodes.BTN_FORWARD,
                        ecodes.BTN_BACK,
                    ]
                )

                if has_mouse_buttons:
                    print(f"[{len(devices)}] {device.name}")
                    print(f"    Path: {path}")
                    print(f"    Capabilities: {len(keys)} buttons")
                    devices.append((path, device))
        except (PermissionError, OSError) as e:
            # Skip devices we can't access
            pass

    if not devices:
        print("No mouse devices found!")
        return

    print("\n" + "="*50)
    choice = input("\nSelect device number to monitor (or 'q' to quit): ").strip()

    if choice.lower() == 'q':
        return

    try:
        idx = int(choice)
        if idx < 0 or idx >= len(devices):
            print(f"Invalid choice. Must be 0-{len(devices)-1}")
            return
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    path, selected_device = devices[idx]
    print(f"\nMonitoring: {selected_device.name}")
    print(f"Path: {path}")
    print("\n🔍 Press any button on this device to see its event code...")
    print("   (Press Ctrl+C to stop)\n")

    try:
        async for event in selected_device.async_read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                if event.value == 1:  # Key down
                    print(f"✅ Button pressed: {key_event.keycode} (code: {event.code})")
                    print(f"   → Use this in config.toml: trigger_key = \"{key_event.keycode}\"")
                elif event.value == 0:  # Key up
                    print(f"   Released: {key_event.keycode}")
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
    finally:
        selected_device.close()


if __name__ == "__main__":
    asyncio.run(find_mouse_and_buttons())
