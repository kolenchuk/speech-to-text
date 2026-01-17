# Architecture Overview

## Daemon Entrypoint Flow
There is a single entrypoint for daemon operation:

1. `run.sh --daemon` activates the venv and runs `python3 -m src.main --daemon`.
2. `src/main.py` parses CLI args and switches into daemon mode.
3. `src/daemon/service.py` runs the main loop.
4. `src/daemon/hotkey_listener.py` captures the configured hotkey.
5. `src/daemon/state_machine.py` manages state transitions:
   `IDLE -> RECORDING -> TRANSCRIBING -> TYPING -> IDLE`.
6. Core actions are invoked in order:
   - `src/core/recorder.py` records audio.
   - `src/core/transcriber.py` runs Whisper transcription.
   - `src/core/text_input.py` types or pastes the result.

## Systemd Integration
The systemd user unit in `systemd/speech-to-text.service` invokes `run.sh --daemon`,
so both manual and service runs share the same code path.
