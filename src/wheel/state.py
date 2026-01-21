"""State machine enums for wheel strategy positions."""

from enum import Enum


class WheelState(Enum):
    """
    State machine for wheel positions.

    The wheel alternates between two fundamental states:
    - CASH: Have capital, can sell puts (hoping to NOT get assigned)
    - SHARES: Have shares, can sell calls (hoping to NOT get called away)

    Open positions track when an option is sold and awaiting expiration.
    """

    CASH = "cash"  # Have capital, no shares, can sell puts
    CASH_PUT_OPEN = "cash_put_open"  # Sold put, awaiting expiration
    SHARES = "shares"  # Have shares, can sell calls
    SHARES_CALL_OPEN = "shares_call_open"  # Sold call, awaiting expiration


class TradeOutcome(Enum):
    """Possible outcomes for a trade."""

    OPEN = "open"  # Trade still active
    EXPIRED_WORTHLESS = "expired_worthless"  # Option expired OTM - KEEP PREMIUM
    ASSIGNED = "assigned"  # Put assigned - BOUGHT SHARES at strike
    CALLED_AWAY = "called_away"  # Call exercised - SOLD SHARES at strike
    CLOSED_EARLY = "closed_early"  # Bought back before expiration


# Valid state transitions for the wheel state machine
VALID_TRANSITIONS: dict[WheelState, dict[str, WheelState]] = {
    WheelState.CASH: {
        "sell_put": WheelState.CASH_PUT_OPEN,
    },
    WheelState.CASH_PUT_OPEN: {
        "expired_otm": WheelState.CASH,
        "assigned": WheelState.SHARES,
        "closed_early": WheelState.CASH,
    },
    WheelState.SHARES: {
        "sell_call": WheelState.SHARES_CALL_OPEN,
    },
    WheelState.SHARES_CALL_OPEN: {
        "expired_otm": WheelState.SHARES,
        "called_away": WheelState.CASH,
        "closed_early": WheelState.SHARES,
    },
}


def get_valid_actions(state: WheelState) -> list[str]:
    """Get list of valid actions from a given state."""
    return list(VALID_TRANSITIONS.get(state, {}).keys())


def can_transition(from_state: WheelState, action: str) -> bool:
    """Check if a transition is valid from the current state."""
    return action in VALID_TRANSITIONS.get(from_state, {})


def get_next_state(from_state: WheelState, action: str) -> WheelState:
    """
    Get the next state after an action.

    Raises:
        ValueError: If the transition is not valid.
    """
    transitions = VALID_TRANSITIONS.get(from_state, {})
    if action not in transitions:
        valid = get_valid_actions(from_state)
        raise ValueError(
            f"Invalid action '{action}' from state '{from_state.value}'. "
            f"Valid actions: {valid}"
        )
    return transitions[action]
