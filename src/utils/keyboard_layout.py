#!/usr/bin/env python3
"""Keyboard layout detection and character-to-keycode mapping.

This module provides layout-aware character mapping for converting text strings
to Linux kernel keycodes and modifiers. Supports:
- ASCII letters (a-z, A-Z) with Shift for uppercase
- Numbers (0-9)
- Common punctuation (. , ! ? : ; ' " space enter tab)
- Ukrainian Cyrillic characters (і, ї, є, ю, а, б, в, г, etc.)

Layout detection uses GNOME gsettings when available, falls back to "us" layout.

IMPORTANT: For non-English text typing to work correctly, the system keyboard layout
must be set to the appropriate language (e.g., Ukrainian for Cyrillic text). The
character mappings are layout-aware and will automatically use the correct physical
key codes based on the detected layout.
"""

from typing import Tuple, List, Optional, Dict
import subprocess
import logging
import unicodedata
from evdev import ecodes

logger = logging.getLogger(__name__)


# Script detection constants
SCRIPT_LATIN = "latin"
SCRIPT_CYRILLIC = "cyrillic"
SCRIPT_MIXED = "mixed"
SCRIPT_OTHER = "other"


def detect_text_script(text: str) -> str:
    """Detect the dominant script of a text string.

    Analyzes Unicode categories to determine if text is primarily Latin,
    Cyrillic, mixed, or other script.

    Args:
        text: Text string to analyze.

    Returns:
        One of: "latin", "cyrillic", "mixed", "other"
    """
    if not text:
        return SCRIPT_OTHER

    latin_count = 0
    cyrillic_count = 0
    total_letters = 0

    for char in text:
        # Skip non-letter characters (spaces, punctuation, numbers)
        if not char.isalpha():
            continue

        total_letters += 1

        # Check Unicode script property
        try:
            name = unicodedata.name(char, "").upper()
            if "CYRILLIC" in name:
                cyrillic_count += 1
            elif "LATIN" in name or char.isascii():
                latin_count += 1
        except ValueError:
            pass

    if total_letters == 0:
        return SCRIPT_OTHER

    latin_ratio = latin_count / total_letters
    cyrillic_ratio = cyrillic_count / total_letters

    # Thresholds for classification
    if latin_ratio > 0.8:
        return SCRIPT_LATIN
    elif cyrillic_ratio > 0.8:
        return SCRIPT_CYRILLIC
    elif latin_ratio > 0.2 and cyrillic_ratio > 0.2:
        return SCRIPT_MIXED
    elif latin_ratio > cyrillic_ratio:
        return SCRIPT_LATIN
    elif cyrillic_ratio > latin_ratio:
        return SCRIPT_CYRILLIC
    else:
        return SCRIPT_OTHER


def get_layout_for_script(script: str) -> str:
    """Get the appropriate keyboard layout code for a script.

    Args:
        script: Script type from detect_text_script().

    Returns:
        Layout code ("us" for Latin, "ua" for Cyrillic, "us" as default).
    """
    if script == SCRIPT_LATIN:
        return "us"
    elif script == SCRIPT_CYRILLIC:
        return "ua"
    else:
        return "us"  # Default to US for mixed/other


def _get_char_script(char: str) -> str:
    """Get script type for a single character.

    Args:
        char: Single character.

    Returns:
        "latin", "cyrillic", or "neutral" (for spaces only).
    """
    # Space and newline are truly neutral
    if char in ' \t\n\r':
        return "neutral"

    # Numbers and ASCII punctuation should use Latin/US layout
    # because Ukrainian layout has different key positions
    if char.isdigit() or (char.isascii() and not char.isalpha()):
        return SCRIPT_LATIN

    if not char.isalpha():
        return "neutral"

    try:
        name = unicodedata.name(char, "").upper()
        if "CYRILLIC" in name:
            return SCRIPT_CYRILLIC
        elif "LATIN" in name or char.isascii():
            return SCRIPT_LATIN
    except ValueError:
        pass

    return "neutral"


def split_text_by_script(text: str) -> list:
    """Split text into segments by script (Latin vs Cyrillic).

    Groups consecutive characters of the same script together.
    Neutral characters (spaces, punctuation) are attached to the
    preceding segment or the following segment if at the start.

    Args:
        text: Text to split.

    Returns:
        List of (segment_text, script) tuples where script is
        "latin", "cyrillic", or "neutral".

    Example:
        >>> split_text_by_script("Hello Привіт World")
        [("Hello ", "latin"), ("Привіт ", "cyrillic"), ("World", "latin")]
    """
    if not text:
        return []

    segments = []
    current_segment = ""
    current_script = None

    for char in text:
        char_script = _get_char_script(char)

        if char_script == "neutral":
            # Neutral chars join the current segment
            current_segment += char
        elif current_script is None or current_script == "neutral":
            # First non-neutral char sets the script
            current_segment += char
            current_script = char_script
        elif char_script == current_script:
            # Same script, continue segment
            current_segment += char
        else:
            # Script changed - save current segment and start new one
            if current_segment:
                segments.append((current_segment, current_script or "neutral"))
            current_segment = char
            current_script = char_script

    # Don't forget the last segment
    if current_segment:
        segments.append((current_segment, current_script or "neutral"))

    return segments


def script_matches_layout(script: str, layout: str) -> bool:
    """Check if a text script matches the current keyboard layout.

    Args:
        script: Script type from detect_text_script().
        layout: Current keyboard layout code (e.g., "us", "ua", "uk").

    Returns:
        True if script and layout are compatible.
    """
    if script == SCRIPT_LATIN:
        return layout in ("us", "en", "gb")
    elif script == SCRIPT_CYRILLIC:
        return layout in ("ua", "uk")
    else:
        return True  # Mixed/other - assume compatible


class KeyboardLayoutMapper:
    """Maps characters to Linux keycodes based on keyboard layout.

    This class maintains character-to-keycode mappings for different keyboard
    layouts and provides methods to look up the appropriate keycode and
    modifiers for a given character.
    """

    def __init__(self):
        """Initialize keyboard layout mapper with predefined mappings."""
        self._current_layout: Optional[str] = None
        self._layout_cache_valid = False

        # Define character mappings for different layouts
        # Format: {layout: {char: (keycode, [modifier_keycodes])}}

        # US English layout mapping
        self._us_layout: Dict[str, Tuple[int, List[int]]] = {
            # Lowercase letters
            'a': (ecodes.KEY_A, []),
            'b': (ecodes.KEY_B, []),
            'c': (ecodes.KEY_C, []),
            'd': (ecodes.KEY_D, []),
            'e': (ecodes.KEY_E, []),
            'f': (ecodes.KEY_F, []),
            'g': (ecodes.KEY_G, []),
            'h': (ecodes.KEY_H, []),
            'i': (ecodes.KEY_I, []),
            'j': (ecodes.KEY_J, []),
            'k': (ecodes.KEY_K, []),
            'l': (ecodes.KEY_L, []),
            'm': (ecodes.KEY_M, []),
            'n': (ecodes.KEY_N, []),
            'o': (ecodes.KEY_O, []),
            'p': (ecodes.KEY_P, []),
            'q': (ecodes.KEY_Q, []),
            'r': (ecodes.KEY_R, []),
            's': (ecodes.KEY_S, []),
            't': (ecodes.KEY_T, []),
            'u': (ecodes.KEY_U, []),
            'v': (ecodes.KEY_V, []),
            'w': (ecodes.KEY_W, []),
            'x': (ecodes.KEY_X, []),
            'y': (ecodes.KEY_Y, []),
            'z': (ecodes.KEY_Z, []),

            # Uppercase letters (with Shift)
            'A': (ecodes.KEY_A, [ecodes.KEY_LEFTSHIFT]),
            'B': (ecodes.KEY_B, [ecodes.KEY_LEFTSHIFT]),
            'C': (ecodes.KEY_C, [ecodes.KEY_LEFTSHIFT]),
            'D': (ecodes.KEY_D, [ecodes.KEY_LEFTSHIFT]),
            'E': (ecodes.KEY_E, [ecodes.KEY_LEFTSHIFT]),
            'F': (ecodes.KEY_F, [ecodes.KEY_LEFTSHIFT]),
            'G': (ecodes.KEY_G, [ecodes.KEY_LEFTSHIFT]),
            'H': (ecodes.KEY_H, [ecodes.KEY_LEFTSHIFT]),
            'I': (ecodes.KEY_I, [ecodes.KEY_LEFTSHIFT]),
            'J': (ecodes.KEY_J, [ecodes.KEY_LEFTSHIFT]),
            'K': (ecodes.KEY_K, [ecodes.KEY_LEFTSHIFT]),
            'L': (ecodes.KEY_L, [ecodes.KEY_LEFTSHIFT]),
            'M': (ecodes.KEY_M, [ecodes.KEY_LEFTSHIFT]),
            'N': (ecodes.KEY_N, [ecodes.KEY_LEFTSHIFT]),
            'O': (ecodes.KEY_O, [ecodes.KEY_LEFTSHIFT]),
            'P': (ecodes.KEY_P, [ecodes.KEY_LEFTSHIFT]),
            'Q': (ecodes.KEY_Q, [ecodes.KEY_LEFTSHIFT]),
            'R': (ecodes.KEY_R, [ecodes.KEY_LEFTSHIFT]),
            'S': (ecodes.KEY_S, [ecodes.KEY_LEFTSHIFT]),
            'T': (ecodes.KEY_T, [ecodes.KEY_LEFTSHIFT]),
            'U': (ecodes.KEY_U, [ecodes.KEY_LEFTSHIFT]),
            'V': (ecodes.KEY_V, [ecodes.KEY_LEFTSHIFT]),
            'W': (ecodes.KEY_W, [ecodes.KEY_LEFTSHIFT]),
            'X': (ecodes.KEY_X, [ecodes.KEY_LEFTSHIFT]),
            'Y': (ecodes.KEY_Y, [ecodes.KEY_LEFTSHIFT]),
            'Z': (ecodes.KEY_Z, [ecodes.KEY_LEFTSHIFT]),

            # Numbers
            '0': (ecodes.KEY_0, []),
            '1': (ecodes.KEY_1, []),
            '2': (ecodes.KEY_2, []),
            '3': (ecodes.KEY_3, []),
            '4': (ecodes.KEY_4, []),
            '5': (ecodes.KEY_5, []),
            '6': (ecodes.KEY_6, []),
            '7': (ecodes.KEY_7, []),
            '8': (ecodes.KEY_8, []),
            '9': (ecodes.KEY_9, []),

            # Common punctuation
            ' ': (ecodes.KEY_SPACE, []),
            '\n': (ecodes.KEY_ENTER, []),
            '\t': (ecodes.KEY_TAB, []),
            '.': (ecodes.KEY_DOT, []),
            ',': (ecodes.KEY_COMMA, []),
            ';': (ecodes.KEY_SEMICOLON, []),
            ':': (ecodes.KEY_SEMICOLON, [ecodes.KEY_LEFTSHIFT]),
            '\'': (ecodes.KEY_APOSTROPHE, []),
            '"': (ecodes.KEY_APOSTROPHE, [ecodes.KEY_LEFTSHIFT]),
            '/': (ecodes.KEY_SLASH, []),
            '?': (ecodes.KEY_SLASH, [ecodes.KEY_LEFTSHIFT]),
            '!': (ecodes.KEY_1, [ecodes.KEY_LEFTSHIFT]),
            '@': (ecodes.KEY_2, [ecodes.KEY_LEFTSHIFT]),
            '#': (ecodes.KEY_3, [ecodes.KEY_LEFTSHIFT]),
            '$': (ecodes.KEY_4, [ecodes.KEY_LEFTSHIFT]),
            '%': (ecodes.KEY_5, [ecodes.KEY_LEFTSHIFT]),
            '^': (ecodes.KEY_6, [ecodes.KEY_LEFTSHIFT]),
            '&': (ecodes.KEY_7, [ecodes.KEY_LEFTSHIFT]),
            '*': (ecodes.KEY_8, [ecodes.KEY_LEFTSHIFT]),
            '(': (ecodes.KEY_9, [ecodes.KEY_LEFTSHIFT]),
            ')': (ecodes.KEY_0, [ecodes.KEY_LEFTSHIFT]),
            '-': (ecodes.KEY_MINUS, []),
            '_': (ecodes.KEY_MINUS, [ecodes.KEY_LEFTSHIFT]),
            '=': (ecodes.KEY_EQUAL, []),
            '+': (ecodes.KEY_EQUAL, [ecodes.KEY_LEFTSHIFT]),
            '[': (ecodes.KEY_LEFTBRACE, []),
            ']': (ecodes.KEY_RIGHTBRACE, []),
            '{': (ecodes.KEY_LEFTBRACE, [ecodes.KEY_LEFTSHIFT]),
            '}': (ecodes.KEY_RIGHTBRACE, [ecodes.KEY_LEFTSHIFT]),
            '\\': (ecodes.KEY_BACKSLASH, []),
            '|': (ecodes.KEY_BACKSLASH, [ecodes.KEY_LEFTSHIFT]),
            '`': (ecodes.KEY_GRAVE, []),
            '~': (ecodes.KEY_GRAVE, [ecodes.KEY_LEFTSHIFT]),
            '<': (ecodes.KEY_COMMA, [ecodes.KEY_LEFTSHIFT]),
            '>': (ecodes.KEY_DOT, [ecodes.KEY_LEFTSHIFT]),
        }

        # Ukrainian layout mapping
        # Based on standard Ukrainian (legacy) keyboard layout from XKB
        # This is the default Ukrainian typewriter layout, NOT phonetic
        self._uk_layout: Dict[str, Tuple[int, List[int]]] = {
            # Ukrainian Cyrillic lowercase - QWERTY row
            'й': (ecodes.KEY_Q, []),   # AD01
            'ц': (ecodes.KEY_W, []),   # AD02
            'у': (ecodes.KEY_E, []),   # AD03
            'к': (ecodes.KEY_R, []),   # AD04
            'е': (ecodes.KEY_T, []),   # AD05
            'н': (ecodes.KEY_Y, []),   # AD06
            'г': (ecodes.KEY_U, []),   # AD07
            'ш': (ecodes.KEY_I, []),   # AD08
            'щ': (ecodes.KEY_O, []),   # AD09
            'з': (ecodes.KEY_P, []),   # AD10
            'х': (ecodes.KEY_LEFTBRACE, []),  # AD11
            'ї': (ecodes.KEY_RIGHTBRACE, []), # AD12 - Ukrainian specific
            'ґ': (ecodes.KEY_BACKSLASH, []),  # BKSL - Ukrainian specific

            # Ukrainian Cyrillic lowercase - ASDF row
            'ф': (ecodes.KEY_A, []),   # AC01
            'і': (ecodes.KEY_S, []),   # AC02 - Ukrainian specific
            'в': (ecodes.KEY_D, []),   # AC03
            'а': (ecodes.KEY_F, []),   # AC04
            'п': (ecodes.KEY_G, []),   # AC05
            'р': (ecodes.KEY_H, []),   # AC06
            'о': (ecodes.KEY_J, []),   # AC07
            'л': (ecodes.KEY_K, []),   # AC08
            'д': (ecodes.KEY_L, []),   # AC09
            'ж': (ecodes.KEY_SEMICOLON, []),  # AC10
            'є': (ecodes.KEY_APOSTROPHE, []), # AC11 - Ukrainian specific

            # Ukrainian Cyrillic lowercase - ZXCV row
            'я': (ecodes.KEY_Z, []),   # AB01
            'ч': (ecodes.KEY_X, []),   # AB02
            'с': (ecodes.KEY_C, []),   # AB03
            'м': (ecodes.KEY_V, []),   # AB04
            'и': (ecodes.KEY_B, []),   # AB05
            'т': (ecodes.KEY_N, []),   # AB06
            'ь': (ecodes.KEY_M, []),   # AB07 - soft sign
            'б': (ecodes.KEY_COMMA, []),   # AB08
            'ю': (ecodes.KEY_DOT, []),     # AB09

            # Ukrainian Cyrillic uppercase (with Shift) - QWERTY row
            'Й': (ecodes.KEY_Q, [ecodes.KEY_LEFTSHIFT]),
            'Ц': (ecodes.KEY_W, [ecodes.KEY_LEFTSHIFT]),
            'У': (ecodes.KEY_E, [ecodes.KEY_LEFTSHIFT]),
            'К': (ecodes.KEY_R, [ecodes.KEY_LEFTSHIFT]),
            'Е': (ecodes.KEY_T, [ecodes.KEY_LEFTSHIFT]),
            'Н': (ecodes.KEY_Y, [ecodes.KEY_LEFTSHIFT]),
            'Г': (ecodes.KEY_U, [ecodes.KEY_LEFTSHIFT]),
            'Ш': (ecodes.KEY_I, [ecodes.KEY_LEFTSHIFT]),
            'Щ': (ecodes.KEY_O, [ecodes.KEY_LEFTSHIFT]),
            'З': (ecodes.KEY_P, [ecodes.KEY_LEFTSHIFT]),
            'Х': (ecodes.KEY_LEFTBRACE, [ecodes.KEY_LEFTSHIFT]),
            'Ї': (ecodes.KEY_RIGHTBRACE, [ecodes.KEY_LEFTSHIFT]),
            'Ґ': (ecodes.KEY_BACKSLASH, [ecodes.KEY_LEFTSHIFT]),

            # Ukrainian Cyrillic uppercase (with Shift) - ASDF row
            'Ф': (ecodes.KEY_A, [ecodes.KEY_LEFTSHIFT]),
            'І': (ecodes.KEY_S, [ecodes.KEY_LEFTSHIFT]),
            'В': (ecodes.KEY_D, [ecodes.KEY_LEFTSHIFT]),
            'А': (ecodes.KEY_F, [ecodes.KEY_LEFTSHIFT]),
            'П': (ecodes.KEY_G, [ecodes.KEY_LEFTSHIFT]),
            'Р': (ecodes.KEY_H, [ecodes.KEY_LEFTSHIFT]),
            'О': (ecodes.KEY_J, [ecodes.KEY_LEFTSHIFT]),
            'Л': (ecodes.KEY_K, [ecodes.KEY_LEFTSHIFT]),
            'Д': (ecodes.KEY_L, [ecodes.KEY_LEFTSHIFT]),
            'Ж': (ecodes.KEY_SEMICOLON, [ecodes.KEY_LEFTSHIFT]),
            'Є': (ecodes.KEY_APOSTROPHE, [ecodes.KEY_LEFTSHIFT]),

            # Ukrainian Cyrillic uppercase (with Shift) - ZXCV row
            'Я': (ecodes.KEY_Z, [ecodes.KEY_LEFTSHIFT]),
            'Ч': (ecodes.KEY_X, [ecodes.KEY_LEFTSHIFT]),
            'С': (ecodes.KEY_C, [ecodes.KEY_LEFTSHIFT]),
            'М': (ecodes.KEY_V, [ecodes.KEY_LEFTSHIFT]),
            'И': (ecodes.KEY_B, [ecodes.KEY_LEFTSHIFT]),
            'Т': (ecodes.KEY_N, [ecodes.KEY_LEFTSHIFT]),
            'Ь': (ecodes.KEY_M, [ecodes.KEY_LEFTSHIFT]),
            'Б': (ecodes.KEY_COMMA, [ecodes.KEY_LEFTSHIFT]),
            'Ю': (ecodes.KEY_DOT, [ecodes.KEY_LEFTSHIFT]),

            # Numbers and common punctuation (same as US)
            '0': (ecodes.KEY_0, []),
            '1': (ecodes.KEY_1, []),
            '2': (ecodes.KEY_2, []),
            '3': (ecodes.KEY_3, []),
            '4': (ecodes.KEY_4, []),
            '5': (ecodes.KEY_5, []),
            '6': (ecodes.KEY_6, []),
            '7': (ecodes.KEY_7, []),
            '8': (ecodes.KEY_8, []),
            '9': (ecodes.KEY_9, []),
            ' ': (ecodes.KEY_SPACE, []),
            '\n': (ecodes.KEY_ENTER, []),
            '\t': (ecodes.KEY_TAB, []),
            '.': (ecodes.KEY_DOT, []),
            ',': (ecodes.KEY_COMMA, []),
            '-': (ecodes.KEY_MINUS, []),
            '_': (ecodes.KEY_MINUS, [ecodes.KEY_LEFTSHIFT]),
        }

    def detect_current_layout(self) -> str:
        """Detect current keyboard layout from GNOME settings or IBus.

        Returns:
            str: Layout code (e.g., "us", "ua", "ru") or "us" as fallback.
        """
        # First try gsettings MRU (most reliable when switching via GNOME UI)
        try:
            import re

            # Get all needed gsettings values
            sources_result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources'],
                capture_output=True,
                text=True,
                timeout=2
            )

            current_result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'current'],
                capture_output=True,
                text=True,
                timeout=2
            )

            # Get MRU (Most Recently Used) sources - this updates on Wayland when you switch layouts
            mru_result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'mru-sources'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if sources_result.returncode == 0 and current_result.returncode == 0:
                # Parse sources: [('xkb', 'us'), ('xkb', 'ua')]
                sources_str = sources_result.stdout.strip()
                layouts = re.findall(r"'([a-z]{2,3})'(?:\),|\)])", sources_str)

                # Parse current index
                current_index = int(current_result.stdout.strip().split()[-1])

                # Parse MRU sources (most recently used)
                mru_layouts = []
                if mru_result.returncode == 0:
                    mru_str = mru_result.stdout.strip()
                    mru_layouts = re.findall(r"'([a-z]{2,3})'(?:\),|\)])", mru_str)

                logger.debug(f"Layouts: {layouts}, Current index: {current_index}, MRU: {mru_layouts}")

                selected_layout = None

                # Prefer MRU when available - GNOME leaves current index stale on Wayland
                if mru_layouts:
                    selected_layout = mru_layouts[0]  # First in MRU is most recent
                    if 0 <= current_index < len(layouts):
                        indexed_layout = layouts[current_index]
                        if mru_layouts[0] != indexed_layout:
                            logger.debug(f"MRU layout '{mru_layouts[0]}' differs from current index layout '{indexed_layout}'; using MRU")
                elif 0 <= current_index < len(layouts):
                    selected_layout = layouts[current_index]

                if selected_layout:
                    logger.debug(f"Detected keyboard layout via gsettings: {selected_layout}")
                    return selected_layout

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, IndexError) as e:
            logger.debug(f"Failed to detect keyboard layout via gsettings: {e}")
        except FileNotFoundError:
            logger.debug("gsettings not found, trying ibus")

        # Fallback to IBus engine query
        try:
            result = subprocess.run(
                ['ibus', 'engine'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                engine = result.stdout.strip()
                # Parse engine name: xkb:us::eng -> us, xkb:ua::ukr -> ua
                if engine.startswith('xkb:'):
                    parts = engine.split(':')
                    if len(parts) >= 2:
                        layout = parts[1]
                        logger.debug(f"Detected keyboard layout via ibus: {layout} (engine: {engine})")
                        return layout

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.debug(f"Failed to detect keyboard layout via ibus: {e}")
        except FileNotFoundError:
            logger.debug("ibus not found")

        # Fallback to US layout
        logger.debug("Using fallback layout: us")
        return "us"

    def get_layout(self) -> str:
        """Get current cached layout or detect it.

        Returns:
            str: Current keyboard layout code.
        """
        if not self._layout_cache_valid or self._current_layout is None:
            self._current_layout = self.detect_current_layout()
            self._layout_cache_valid = True

        return self._current_layout

    def invalidate_layout_cache(self):
        """Force re-detection of keyboard layout on next access."""
        self._layout_cache_valid = False

    def get_keycode_for_char(self, char: str, layout: Optional[str] = None) -> Tuple[int, List[int]]:
        """Get Linux keycode and modifiers for a character.

        Args:
            char: Single character to map.
            layout: Optional layout override (e.g., "us", "uk").
                   If None, uses detected layout.

        Returns:
            Tuple of (keycode, [modifier_keycodes]).
            Returns (ecodes.KEY_SPACE, []) for unmappable characters as fallback.

        Raises:
            ValueError: If char is not a single character.
        """
        if len(char) != 1:
            raise ValueError(f"Expected single character, got: {repr(char)}")

        # Determine which layout to use
        if layout is None:
            layout = self.get_layout()

        # Select appropriate mapping table
        if layout.startswith('uk') or layout.startswith('ua'):
            mapping = self._uk_layout
        else:
            mapping = self._us_layout

        # Look up character in mapping
        if char in mapping:
            return mapping[char]

        # Check if it's in US layout (fallback for mixed text)
        if layout != 'us' and char in self._us_layout:
            logger.debug(f"Character '{char}' not in {layout} layout, using US mapping")
            return self._us_layout[char]

        # Unmappable character - log warning and return space as fallback
        logger.warning(f"Character '{char}' (U+{ord(char):04X}) not mappable in layout '{layout}', using space")
        return (ecodes.KEY_SPACE, [])

    def get_available_layouts(self) -> List[str]:
        """Get list of available keyboard layouts from GNOME settings.

        Returns:
            List of layout codes (e.g., ["us", "ua"]).
        """
        try:
            import re

            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                sources_str = result.stdout.strip()
                layouts = re.findall(r"'([a-z]{2,3})'(?:\),|\)])", sources_str)
                return layouts

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.debug(f"Failed to get available layouts: {e}")
        except FileNotFoundError:
            logger.debug("gsettings not found")

        return ["us"]  # Fallback

    def get_layout_index(self, layout: str) -> int:
        """Get the index of a layout in the available layouts list.

        Args:
            layout: Layout code to find (e.g., "us", "ua").

        Returns:
            Index of layout, or -1 if not found.
        """
        layouts = self.get_available_layouts()
        for i, l in enumerate(layouts):
            if l == layout or l.startswith(layout) or layout.startswith(l):
                return i
        return -1

    def switch_layout(self, layout: str) -> bool:
        """Switch system keyboard layout via IBus and XKB.

        Args:
            layout: Layout code to switch to (e.g., "us", "ua").

        Returns:
            True if successful, False otherwise.
        """
        # Map layout codes to IBus engine names
        layout_to_engine = {
            'us': 'xkb:us::eng',
            'en': 'xkb:us::eng',
            'ua': 'xkb:ua::ukr',
            'uk': 'xkb:ua::ukr',
        }

        # Map layout codes to XKB layout names
        layout_to_xkb = {
            'us': 'us',
            'en': 'us',
            'ua': 'ua',
            'uk': 'ua',
        }

        xkb_layout = layout_to_xkb.get(layout, layout)
        engine = layout_to_engine.get(layout)

        success = False

        # Try IBus first
        if engine:
            try:
                result = subprocess.run(
                    ['ibus', 'engine', engine],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    logger.debug(f"IBus engine set to {engine}")
                    success = True
            except Exception as e:
                logger.debug(f"IBus switch failed: {e}")

        # Also try setxkbmap for XKB-level switch (affects uinput)
        try:
            result = subprocess.run(
                ['setxkbmap', xkb_layout],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                logger.debug(f"XKB layout set to {xkb_layout}")
                success = True
        except Exception as e:
            logger.debug(f"setxkbmap failed: {e}")

        if success:
            logger.info(f"Switched keyboard layout to '{layout}'")
            self._current_layout = layout
            self._layout_cache_valid = True
            return True
        else:
            logger.error(f"Failed to switch layout to '{layout}'")
            return False

    def switch_layout_for_text(self, text: str) -> Optional[str]:
        """Switch layout to match text script, return original layout.

        Detects the script of the text and switches to appropriate layout
        if there's a mismatch.

        Args:
            text: Text that will be typed.

        Returns:
            Original layout code if switched, None if no switch needed.
        """
        current_layout = self.detect_current_layout()
        text_script = detect_text_script(text)

        logger.debug(f"Text script: {text_script}, current layout: {current_layout}")

        if script_matches_layout(text_script, current_layout):
            logger.debug("Script matches layout, no switch needed")
            return None

        # Need to switch layout
        target_layout = get_layout_for_script(text_script)
        logger.info(f"Script mismatch: text is {text_script}, layout is {current_layout}. Switching to {target_layout}")

        if self.switch_layout(target_layout):
            return current_layout  # Return original for restoration
        else:
            logger.warning(f"Failed to switch layout to {target_layout}")
            return None

    def restore_layout(self, layout: str) -> bool:
        """Restore previously saved layout.

        Args:
            layout: Layout code to restore.

        Returns:
            True if successful, False otherwise.
        """
        logger.debug(f"Restoring layout to '{layout}'")
        return self.switch_layout(layout)


# Global singleton instance
_mapper: Optional[KeyboardLayoutMapper] = None


def get_keyboard_mapper() -> KeyboardLayoutMapper:
    """Get or create the global KeyboardLayoutMapper instance.

    Returns:
        KeyboardLayoutMapper: Singleton instance.
    """
    global _mapper
    if _mapper is None:
        _mapper = KeyboardLayoutMapper()
    return _mapper


def get_keycode_for_char(char: str, layout: Optional[str] = None) -> Tuple[int, List[int]]:
    """Convenience function to get keycode for a character.

    Args:
        char: Single character to map.
        layout: Optional layout override. If None, uses detected layout.

    Returns:
        Tuple of (keycode, [modifier_keycodes]).
    """
    return get_keyboard_mapper().get_keycode_for_char(char, layout)


def detect_current_layout() -> str:
    """Convenience function to detect current keyboard layout.

    Returns:
        str: Layout code (e.g., "us", "uk").
    """
    return get_keyboard_mapper().detect_current_layout()
