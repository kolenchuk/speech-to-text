"""Audio recording module."""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Audio recorder using arecord (ALSA)."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        audio_format: str = "S16_LE",
    ):
        """
        Initialize recorder.

        Args:
            sample_rate: Sample rate in Hz (16000 optimal for Whisper)
            channels: Number of channels (1 = mono)
            audio_format: Audio format (S16_LE = 16-bit signed little-endian)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_format = audio_format
        self._process: Optional[asyncio.subprocess.Process] = None
        self._audio_file: Optional[str] = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    def record_sync(self, duration: int, output_file: Optional[str] = None) -> Optional[str]:
        """
        Record audio synchronously for a fixed duration.

        Args:
            duration: Recording duration in seconds
            output_file: Path to save WAV file (auto-generated if None)

        Returns:
            Path to recorded audio file or None on failure
        """
        if output_file is None:
            fd, output_file = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

        logger.info(f"Recording for {duration} seconds...")

        try:
            cmd = [
                "arecord",
                "-d", str(duration),
                "-f", self.audio_format,
                "-r", str(self.sample_rate),
                "-c", str(self.channels),
                "-t", "wav",
                output_file,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration + 5,
            )

            if result.returncode == 0 and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                logger.info(f"Recording complete ({file_size / 1024:.1f} KB)")
                return output_file
            else:
                logger.error(f"Recording failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("Recording timed out")
            return None
        except FileNotFoundError:
            logger.error("arecord not found. Install with: sudo apt install alsa-utils")
            return None
        except Exception as e:
            logger.error(f"Recording error: {e}")
            return None

    async def start_recording(self, output_file: Optional[str] = None) -> str:
        """
        Start recording audio (async, non-blocking).

        Args:
            output_file: Path to save WAV file (auto-generated if None)

        Returns:
            Path to audio file being recorded
        """
        if self._is_recording:
            logger.warning("Already recording")
            return self._audio_file

        if output_file is None:
            fd, output_file = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

        self._audio_file = output_file
        logger.info("Starting recording...")

        cmd = [
            "arecord",
            "-f", self.audio_format,
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-t", "wav",
            output_file,
        ]

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._is_recording = True

        return output_file

    async def stop_recording(self) -> Optional[str]:
        """
        Stop recording and return audio file path.

        Returns:
            Path to recorded audio file or None if not recording
        """
        if not self._is_recording or self._process is None:
            logger.warning("Not currently recording")
            return None

        logger.info("Stopping recording...")

        # Send SIGTERM to stop arecord gracefully
        self._process.terminate()

        try:
            await asyncio.wait_for(self._process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("Recording process did not stop, killing...")
            self._process.kill()
            await self._process.wait()

        self._process = None
        self._is_recording = False

        if self._audio_file and os.path.exists(self._audio_file):
            file_size = os.path.getsize(self._audio_file)
            logger.info(f"Recording stopped ({file_size / 1024:.1f} KB)")
            return self._audio_file

        return None

    async def cancel_recording(self):
        """Cancel recording and delete audio file."""
        audio_file = await self.stop_recording()
        if audio_file and os.path.exists(audio_file):
            os.unlink(audio_file)
            logger.info("Recording cancelled and file deleted")

    @staticmethod
    def cleanup(audio_file: str):
        """Clean up temporary audio file."""
        if audio_file and os.path.exists(audio_file):
            os.unlink(audio_file)
            logger.debug(f"Cleaned up {audio_file}")
