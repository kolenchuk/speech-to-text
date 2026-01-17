#!/bin/bash
# Speech-to-Text Runner Script
# Activates virtual environment and runs the speech-to-text application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine venv path based on installation method
if [ -d "$SCRIPT_DIR/venv" ]; then
    # Package installation: venv in same directory as script
    VENV_PATH="$SCRIPT_DIR/venv"
elif [ -d "$HOME/speech-env" ]; then
    # Manual installation: user's home directory
    VENV_PATH="$HOME/speech-env"
else
    echo "Error: Virtual environment not found!"
    echo ""
    echo "Searched locations:"
    echo "  - $SCRIPT_DIR/venv (package installation)"
    echo "  - $HOME/speech-env (manual installation)"
    echo ""
    echo "If installed via .deb package, the venv should have been created automatically."
    echo "If manual install, create it with: python3 -m venv ~/speech-env"
    exit 1
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Run the main module
python3 -m src.main "$@"

# Deactivate when done (only for non-daemon mode)
if [[ "$1" != "--daemon" && "$1" != "-d" ]]; then
    deactivate
fi
