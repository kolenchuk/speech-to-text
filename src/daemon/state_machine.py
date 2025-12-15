"""State machine for speech-to-text service."""

import logging
from enum import Enum, auto
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class State(Enum):
    """Service states."""
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    TYPING = auto()
    ERROR = auto()


class StateMachine:
    """
    State machine for managing service workflow.

    Valid transitions:
    - IDLE -> RECORDING (on hotkey press)
    - RECORDING -> TRANSCRIBING (on hotkey release)
    - RECORDING -> IDLE (on cancel/error)
    - TRANSCRIBING -> TYPING (transcription complete with text)
    - TRANSCRIBING -> IDLE (transcription complete, no text)
    - TRANSCRIBING -> ERROR (transcription failed)
    - TYPING -> IDLE (typing complete)
    - TYPING -> ERROR (typing failed)
    - ERROR -> IDLE (error handled)
    """

    VALID_TRANSITIONS = {
        State.IDLE: {State.RECORDING},
        State.RECORDING: {State.TRANSCRIBING, State.IDLE, State.ERROR},
        State.TRANSCRIBING: {State.TYPING, State.IDLE, State.ERROR},
        State.TYPING: {State.IDLE, State.ERROR},
        State.ERROR: {State.IDLE},
    }

    def __init__(self, on_state_change: Optional[Callable[[State, State], None]] = None):
        """
        Initialize state machine.

        Args:
            on_state_change: Optional callback(old_state, new_state) on transitions
        """
        self._state = State.IDLE
        self._on_state_change = on_state_change
        self._error_message: Optional[str] = None

    @property
    def state(self) -> State:
        """Current state."""
        return self._state

    @property
    def is_idle(self) -> bool:
        """Check if in IDLE state."""
        return self._state == State.IDLE

    @property
    def is_recording(self) -> bool:
        """Check if in RECORDING state."""
        return self._state == State.RECORDING

    @property
    def is_busy(self) -> bool:
        """Check if service is busy (not idle)."""
        return self._state != State.IDLE

    @property
    def error_message(self) -> Optional[str]:
        """Get last error message."""
        return self._error_message

    def can_transition_to(self, new_state: State) -> bool:
        """Check if transition to new_state is valid."""
        valid_targets = self.VALID_TRANSITIONS.get(self._state, set())
        return new_state in valid_targets

    def transition(self, new_state: State, error_message: Optional[str] = None) -> bool:
        """
        Transition to a new state.

        Args:
            new_state: Target state
            error_message: Error message (for ERROR state)

        Returns:
            True if transition was successful
        """
        if not self.can_transition_to(new_state):
            logger.warning(
                f"Invalid state transition: {self._state.name} -> {new_state.name}"
            )
            return False

        old_state = self._state
        self._state = new_state

        if new_state == State.ERROR:
            self._error_message = error_message
            logger.error(f"Entered ERROR state: {error_message}")
        else:
            self._error_message = None

        logger.info(f"State: {old_state.name} -> {new_state.name}")

        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

        return True

    def reset(self):
        """Reset to IDLE state (unconditional)."""
        old_state = self._state
        self._state = State.IDLE
        self._error_message = None
        logger.info(f"State reset: {old_state.name} -> IDLE")

    def start_recording(self) -> bool:
        """Transition to RECORDING state."""
        return self.transition(State.RECORDING)

    def stop_recording(self) -> bool:
        """Transition to TRANSCRIBING state."""
        return self.transition(State.TRANSCRIBING)

    def cancel_recording(self) -> bool:
        """Cancel recording and return to IDLE."""
        return self.transition(State.IDLE)

    def start_typing(self) -> bool:
        """Transition to TYPING state."""
        return self.transition(State.TYPING)

    def finish(self) -> bool:
        """Finish workflow and return to IDLE."""
        return self.transition(State.IDLE)

    def error(self, message: str) -> bool:
        """Transition to ERROR state."""
        return self.transition(State.ERROR, error_message=message)

    def recover_from_error(self) -> bool:
        """Recover from ERROR state to IDLE."""
        if self._state == State.ERROR:
            return self.transition(State.IDLE)
        return False

    def __str__(self) -> str:
        return f"StateMachine({self._state.name})"

    def __repr__(self) -> str:
        return self.__str__()
