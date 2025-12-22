"""Whisper transcription module."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Transcriber:
    """Wrapper for Whisper speech recognition model."""

    def __init__(
        self,
        model: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        initial_prompt: str = "",
        local_model_path: str | None = None,
        download_if_missing: bool = True,
    ):
        """
        Initialize transcriber.

        Args:
            model: Whisper model size (tiny, base, small, medium, large)
            device: Device to run on (cpu or cuda)
            compute_type: Computation type (int8, float16, float32)
            language: Language code or None for auto-detect
            beam_size: Beam size for search (higher = more accurate but slower)
            vad_filter: Enable voice activity detection filtering
            initial_prompt: Optional prompt to guide transcription
            local_model_path: Optional local path to model directory; skips network if present
            download_if_missing: Download model to local path if not found
        """
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language if language else None
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.initial_prompt = initial_prompt if initial_prompt else None
        self.local_model_path = Path(local_model_path).expanduser() if local_model_path else None
        self.download_if_missing = download_if_missing
        self._model = None

    def _repo_id_for_download(self) -> str:
        """
        Resolve the repository ID to download when a local path is missing.

        Returns:
            Hugging Face repo_id string
        """
        # If user already passed a repo-style string, keep it
        if "/" in self.model_name:
            return self.model_name

        # Map shorthand sizes to known faster-whisper repos
        size_map = {
            "tiny": "Systran/faster-whisper-tiny",
            "base": "Systran/faster-whisper-base",
            "small": "Systran/faster-whisper-small",
            "medium": "Systran/faster-whisper-medium",
            "large": "Systran/faster-whisper-large",
            "large-v2": "Systran/faster-whisper-large-v2",
            "large-v3": "Systran/faster-whisper-large-v3",
        }
        return size_map.get(self.model_name, self.model_name)

    def _resolve_model_source(self) -> str:
        """
        Determine model source (local path or remote ID).

        Returns:
            Path or model name usable by WhisperModel
        """
        if not self.local_model_path:
            return self.model_name

        # Check if the directory exists AND contains model files
        model_exists = False
        if self.local_model_path.exists():
            # Check for required model files (model.bin is the main file)
            model_bin = self.local_model_path / "model.bin"
            if model_bin.exists():
                model_exists = True

        if model_exists:
            logger.info(f"Using local Whisper model at {self.local_model_path}")
            return str(self.local_model_path)

        if not self.download_if_missing:
            raise FileNotFoundError(
                f"Local model not found at {self.local_model_path} and download_if_missing is False"
            )

        # Attempt download
        try:
            from huggingface_hub import snapshot_download
        except ImportError as e:
            raise RuntimeError(
                "huggingface-hub not installed; cannot download model automatically. "
                "Install with: pip install \"huggingface-hub>=0.23\"."
            ) from e

        repo_id = self._repo_id_for_download()
        logger.info(f"Local model not found at {self.local_model_path}, downloading '{repo_id}'...")
        logger.info(f"This may take a few minutes (model size varies by type)...")

        # Create directory if it doesn't exist
        self.local_model_path.mkdir(parents=True, exist_ok=True)

        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(self.local_model_path),
                local_dir_use_symlinks=False,
                revision="main",
            )
            logger.info(f"Model downloaded successfully to {self.local_model_path}")
            return str(self.local_model_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise RuntimeError(f"Failed to download model '{self.model_name}' from '{repo_id}': {e}") from e

    def load_model(self):
        """
        Pre-load the Whisper model.

        Call this once at startup to avoid delay on first transcription.
        """
        if self._model is not None:
            return self._model

        model_source = self._resolve_model_source()
        logger.info(f"Loading Whisper model from '{model_source}'...")

        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                model_source,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Model loaded successfully")
            return self._model

        except ImportError:
            logger.error("faster-whisper not installed")
            raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def transcribe(self, audio_file: str | Path) -> str:
        """
        Transcribe audio file to text.

        Args:
            audio_file: Path to WAV audio file

        Returns:
            Transcribed text
        """
        model = self.load_model()
        audio_path = str(audio_file)

        logger.info(f"Transcribing {audio_path}...")

        try:
            segments, info = model.transcribe(
                audio_path,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                initial_prompt=self.initial_prompt,
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            full_text = " ".join(text_parts)

            logger.info(
                f"Detected language: {info.language} ({info.language_probability:.1%})"
            )
            logger.debug(f"Transcribed text: {full_text[:100]}...")

            return full_text

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

    def transcribe_sync(self, audio_file: str | Path) -> str:
        """Synchronous transcription (alias for transcribe)."""
        return self.transcribe(audio_file)
