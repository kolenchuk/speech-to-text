"""Keyboard layout detection utilities."""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _run_gsettings(key: str) -> Optional[str]:
    """Run gsettings for the given key and return stdout or None on error."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.input-sources", key],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.warning("gsettings %s failed: rc=%s, stderr=%s", key, result.returncode, result.stderr.strip())
    except subprocess.TimeoutExpired:
        logger.warning("gsettings %s timed out", key)
    return None


def detect_current_keyboard_layout() -> Optional[str]:
    """
    Detect the currently active keyboard layout and map to Whisper language code.

    Returns:
        Whisper language code (e.g., 'en', 'uk', 'ru') or None if detection fails
    """
    logger.info("=== KEYBOARD LAYOUT DETECTION START ===")
    try:
        # Try GNOME/Wayland keyboard layout detection
        sources_str = _run_gsettings("sources")
        current_str = _run_gsettings("current")
        mru_str = _run_gsettings("mru-sources")
        per_window_str = _run_gsettings("per-window")

        if sources_str and current_str:
            import re

            # Parse sources: [('xkb', 'us'), ('xkb', 'ua')]
            layouts = re.findall(r"'([a-z]{2,3})'(?:\),|\)])", sources_str)
            current_index = int(current_str.split()[-1])

            # mru-sources gives most recently used layouts, helpful when per-window is enabled
            mru_layouts = re.findall(r"'([a-z]{2,3})'(?:\),|\)])", mru_str or "")
            per_window = per_window_str.lower() == "true" if per_window_str else None

            logger.info("Parsed layouts from sources: %s", layouts)
            logger.info("Current layout index from gsettings: %s", current_index)
            if mru_layouts:
                logger.info("MRU layouts from gsettings: %s", mru_layouts)
            if per_window is not None:
                logger.info("per-window input sources: %s", per_window)

            selected_layout = None

            # Prefer MRU when available; GNOME sometimes leaves current index stale on Wayland
            if mru_layouts:
                if 0 <= current_index < len(layouts):
                    indexed_layout = layouts[current_index]
                    if mru_layouts[0] != indexed_layout:
                        logger.info("MRU layout '%s' differs from current index '%s'; preferring MRU",
                                    mru_layouts[0], indexed_layout)
                selected_layout = mru_layouts[0]
            elif 0 <= current_index < len(layouts):
                selected_layout = layouts[current_index]
                logger.info("Selected layout at index %s: '%s'", current_index, selected_layout)
            else:
                logger.warning("Current index %s out of range for layouts %s", current_index, layouts)

            if not selected_layout:
                logger.info("=== KEYBOARD LAYOUT DETECTION FAILED (no layout selected) ===")
                return None

            layout_map = {
                'us': 'en', 'gb': 'en', 'uk': 'en',  # English layouts (note: 'uk' means United Kingdom)
                'ua': 'uk',  # Ukrainian layout -> Whisper 'uk' code
                'ru': 'ru',  # Russian
                'de': 'de', 'fr': 'fr', 'es': 'es', 'it': 'it',
                'pl': 'pl', 'cz': 'cs', 'sk': 'sk',
                'pt': 'pt', 'nl': 'nl', 'se': 'sv', 'no': 'no',
            }

            lang = layout_map.get(selected_layout, selected_layout)
            logger.info("Mapped layout '%s' -> Whisper language '%s'", selected_layout, lang)
            logger.info("=== KEYBOARD LAYOUT DETECTION SUCCESS ===")
            return lang

    except Exception as e:
        logger.error("Keyboard layout detection failed with exception: %s", e, exc_info=True)
        logger.info("=== KEYBOARD LAYOUT DETECTION FAILED (exception) ===")

    return None
