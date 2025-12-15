#!/bin/bash
# Speech-to-Text Runner Script
# Activates virtual environment and runs the speech-to-text application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$HOME/speech-env"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Create it with: python3 -m venv $VENV_PATH"
    exit 1
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Check for legacy mode (direct speech_to_text.py call)
if [[ "$1" == "--legacy" ]]; then
    shift
    python3 "$SCRIPT_DIR/src/speech_to_text.py" "$@"
else
    # Run the new main module
    python3 -m src.main "$@"
fi

# Deactivate when done (only for non-daemon mode)
if [[ "$1" != "--daemon" && "$1" != "-d" ]]; then
    deactivate
fi
