"""Configuration management with TOML support."""

import os
import tomllib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WhisperConfig:
    """Whisper model configuration."""
    model: str = "small"  # 'small' recommended for multilingual
    local_model_path: str = ""  # Optional local path; skip network when set
    download_if_missing: bool = True  # Download model to local path if absent
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = ""  # Empty for system default, "auto" for auto-detect, or "uk", "en", etc.
    beam_size: int = 5
    vad_filter: bool = True
    initial_prompt: str = ""  # Optional prompt to guide transcription

    @property
    def language_or_none(self) -> Optional[str]:
        """Get language for Whisper (None for auto-detect, or detected from system)."""
        if self.language == "auto":
            return None  # Auto-detect
        elif self.language == "":
            # Use system language
            return self._detect_system_language()
        else:
            return self.language

    @staticmethod
    def _detect_system_language() -> Optional[str]:
        """Detect system language from keyboard layout or locale."""
        import subprocess
        import locale

        # First, try to detect from keyboard layout (most accurate for typing)
        try:
            # Try GNOME/Wayland keyboard layout detection
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                # Get current layout index
                current = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.input-sources", "current"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if current.returncode == 0:
                    # Parse sources: [('xkb', 'us'), ('xkb', 'ua')]
                    sources_str = result.stdout.strip()
                    current_index = int(current.stdout.strip().split()[-1])

                    # Extract layout codes
                    import re
                    layouts = re.findall(r"'([a-z]{2,3})'(?:\),|\)])", sources_str)
                    if current_index < len(layouts):
                        layout = layouts[current_index]
                        # Map keyboard layouts to Whisper language codes
                        layout_map = {
                            'us': 'en', 'gb': 'en', 'uk': 'en',  # English layouts
                            'ua': 'uk',  # Ukrainian
                            'de': 'de', 'fr': 'fr', 'es': 'es', 'it': 'it',
                            'pl': 'pl', 'cz': 'cs', 'sk': 'sk',
                        }
                        lang = layout_map.get(layout, layout)
                        logger.info(f"Detected keyboard layout '{layout}' -> language '{lang}'")
                        return lang
        except Exception as e:
            logger.debug(f"Keyboard layout detection failed: {e}")

        # Fallback to locale detection
        try:
            lang_code, _ = locale.getdefaultlocale()
            if lang_code:
                lang = lang_code.split('_')[0].lower()
                logger.info(f"Detected system locale: {lang}")
                return lang
        except Exception as e:
            logger.debug(f"Locale detection failed: {e}")

        logger.warning("Could not detect system language, using auto-detect")
        return None


@dataclass
class AudioConfig:
    """Audio recording configuration."""
    sample_rate: int = 16000
    channels: int = 1
    format: str = "S16_LE"
    min_duration: float = 0.5
    max_duration: int = 60


@dataclass
class HotkeyConfig:
    """Hotkey configuration."""
    trigger_key: str = "KEY_RIGHTCTRL"
    device_path: str = ""  # Empty for auto-detect
    enable_double_tap: bool = False  # Require double-tap to activate (prevents conflicts with Ctrl combinations)
    double_tap_timeout_ms: int = 300  # Max time between taps in milliseconds

    @property
    def key_code(self) -> int:
        """Get evdev key code for trigger key."""
        from evdev import ecodes
        return getattr(ecodes, self.trigger_key, 97)  # 97 = KEY_RIGHTCTRL


@dataclass
class FeedbackConfig:
    """Audio feedback configuration."""
    enabled: bool = True
    start_sound: str = "/usr/share/sounds/freedesktop/stereo/message.oga"
    stop_sound: str = "/usr/share/sounds/freedesktop/stereo/complete.oga"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = ""  # Empty for stderr only


@dataclass
class DisplayConfig:
    """Display server configuration."""
    server: str = ""  # Empty for auto-detect
    tool: str = ""  # Force specific tool: "ydotool", "wtype", "xdotool"

    @property
    def actual_server(self) -> str:
        """Get actual display server (auto-detect if not set)."""
        if self.server:
            return self.server
        return os.environ.get("XDG_SESSION_TYPE", "x11")


@dataclass
class TextInputConfig:
    """Text input configuration."""
    mode: str = "uinput"  # Input mode: "uinput" or "clipboard"
    paste_key_combination: str = "shift+insert"  # Paste key for clipboard mode
    key_delay_ms: int = 10  # Delay between key events in milliseconds (uinput mode)


@dataclass
class Config:
    """Main configuration container."""
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    text_input: TextInputConfig = field(default_factory=TextInputConfig)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """
        Load configuration from TOML file.

        Args:
            path: Path to config file. Uses default if None.

        Returns:
            Config object with loaded or default values
        """
        if path is None:
            path = Path.home() / ".config" / "speech-to-text" / "config.toml"

        config = cls()

        if path.exists():
            logger.info(f"Loading configuration from {path}")
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                config = cls._from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}, using defaults")
        else:
            logger.info("No config file found, using defaults")

        return config

    @classmethod
    def _from_dict(cls, data: dict) -> "Config":
        """Create Config from dictionary."""
        config = cls()

        # Allow future model backends: accept [whisper] (current) or [model] as alias
        whisper_section = data.get("model") or data.get("whisper")
        if whisper_section:
            w = whisper_section
            config.whisper = WhisperConfig(
                model=w.get("model", config.whisper.model),
                local_model_path=w.get("local_model_path", config.whisper.local_model_path),
                download_if_missing=w.get("download_if_missing", config.whisper.download_if_missing),
                device=w.get("device", config.whisper.device),
                compute_type=w.get("compute_type", config.whisper.compute_type),
                language=w.get("language", config.whisper.language),
                beam_size=w.get("beam_size", config.whisper.beam_size),
                vad_filter=w.get("vad_filter", config.whisper.vad_filter),
                initial_prompt=w.get("initial_prompt", config.whisper.initial_prompt),
            )

        if "audio" in data:
            a = data["audio"]
            config.audio = AudioConfig(
                sample_rate=a.get("sample_rate", config.audio.sample_rate),
                channels=a.get("channels", config.audio.channels),
                format=a.get("format", config.audio.format),
                min_duration=a.get("min_duration", config.audio.min_duration),
                max_duration=a.get("max_duration", config.audio.max_duration),
            )

        if "hotkey" in data:
            h = data["hotkey"]
            config.hotkey = HotkeyConfig(
                trigger_key=h.get("trigger_key", config.hotkey.trigger_key),
                device_path=h.get("device_path", config.hotkey.device_path),
                enable_double_tap=h.get("enable_double_tap", config.hotkey.enable_double_tap),
                double_tap_timeout_ms=h.get("double_tap_timeout_ms", config.hotkey.double_tap_timeout_ms),
            )

        if "feedback" in data:
            f = data["feedback"]
            config.feedback = FeedbackConfig(
                enabled=f.get("enabled", config.feedback.enabled),
                start_sound=f.get("start_sound", config.feedback.start_sound),
                stop_sound=f.get("stop_sound", config.feedback.stop_sound),
            )

        if "logging" in data:
            l = data["logging"]
            config.logging = LoggingConfig(
                level=l.get("level", config.logging.level),
                file=l.get("file", config.logging.file),
            )

        if "display" in data:
            d = data["display"]
            config.display = DisplayConfig(
                server=d.get("server", config.display.server),
                tool=d.get("tool", config.display.tool),
            )

        if "text_input" in data:
            ti = data["text_input"]
            config.text_input = TextInputConfig(
                mode=ti.get("mode", config.text_input.mode),
                paste_key_combination=ti.get("paste_key_combination", config.text_input.paste_key_combination),
                key_delay_ms=ti.get("key_delay_ms", config.text_input.key_delay_ms),
            )

        return config

    def print_config(self):
        """Print current configuration."""
        print("Current Configuration:")
        print("=" * 60)
        print(f"Whisper Model:     {self.whisper.model}")
        print(f"Whisper Device:    {self.whisper.device}")
        print(f"Compute Type:      {self.whisper.compute_type}")
        print(f"Language:          {self.whisper.language or 'auto-detect'}")
        print()
        print(f"Audio Rate:        {self.audio.sample_rate} Hz")
        print(f"Audio Channels:    {self.audio.channels}")
        print()
        print(f"Hotkey:            {self.hotkey.trigger_key}")
        print(f"Device Path:       {self.hotkey.device_path or 'auto-detect'}")
        print(f"Double-Tap Mode:   {'enabled' if self.hotkey.enable_double_tap else 'disabled'}")
        if self.hotkey.enable_double_tap:
            print(f"Double-Tap Timeout: {self.hotkey.double_tap_timeout_ms} ms")
        print()
        print(f"Display Server:    {self.display.actual_server}")
        print(f"Audio Feedback:    {'enabled' if self.feedback.enabled else 'disabled'}")
        print(f"Log Level:         {self.logging.level}")
        print()
        print(f"Text Input Mode:   {self.text_input.mode}")
        print(f"Paste Key Combo:   {self.text_input.paste_key_combination}")
        print(f"Key Delay:         {self.text_input.key_delay_ms} ms")
        print("=" * 60)


# Default config path
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "speech-to-text" / "config.toml"


def ensure_config_dir():
    """Ensure configuration directory exists."""
    config_dir = Path.home() / ".config" / "speech-to-text"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


# For backward compatibility with the old Config class
class LegacyConfig:
    """Legacy configuration for backward compatibility."""

    WHISPER_MODEL = "base"
    WHISPER_DEVICE = "cpu"
    WHISPER_COMPUTE_TYPE = "int8"
    WHISPER_LANGUAGE = None

    AUDIO_RATE = 16000
    AUDIO_CHANNELS = 1
    AUDIO_FORMAT = "S16_LE"
    DEFAULT_DURATION = 5

    DISPLAY_SERVER = os.environ.get("XDG_SESSION_TYPE", "x11")
    TEXT_TOOL = "ydotool" if DISPLAY_SERVER == "wayland" else "xdotool"

    HOTKEY = "KEY_RIGHTCTRL"
    INPUT_DEVICE = None

    VAD_FILTER = True
    BEAM_SIZE = 5


if __name__ == "__main__":
    config = Config.load()
    config.print_config()
