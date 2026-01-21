"""Tests for wheel state machine."""

import pytest

from src.wheel.state import (
    VALID_TRANSITIONS,
    TradeOutcome,
    WheelState,
    can_transition,
    get_next_state,
    get_valid_actions,
)


class TestWheelState:
    """Tests for WheelState enum."""

    def test_wheel_states_exist(self) -> None:
        """All expected states should exist."""
        assert WheelState.CASH.value == "cash"
        assert WheelState.CASH_PUT_OPEN.value == "cash_put_open"
        assert WheelState.SHARES.value == "shares"
        assert WheelState.SHARES_CALL_OPEN.value == "shares_call_open"

    def test_trade_outcomes_exist(self) -> None:
        """All expected outcomes should exist."""
        assert TradeOutcome.OPEN.value == "open"
        assert TradeOutcome.EXPIRED_WORTHLESS.value == "expired_worthless"
        assert TradeOutcome.ASSIGNED.value == "assigned"
        assert TradeOutcome.CALLED_AWAY.value == "called_away"
        assert TradeOutcome.CLOSED_EARLY.value == "closed_early"


class TestStateTransitions:
    """Tests for state transition logic."""

    def test_valid_transitions_from_cash(self) -> None:
        """CASH state should only allow sell_put."""
        actions = get_valid_actions(WheelState.CASH)
        assert actions == ["sell_put"]

    def test_valid_transitions_from_cash_put_open(self) -> None:
        """CASH_PUT_OPEN should allow expiry outcomes."""
        actions = get_valid_actions(WheelState.CASH_PUT_OPEN)
        assert "expired_otm" in actions
        assert "assigned" in actions
        assert "closed_early" in actions

    def test_valid_transitions_from_shares(self) -> None:
        """SHARES state should only allow sell_call."""
        actions = get_valid_actions(WheelState.SHARES)
        assert actions == ["sell_call"]

    def test_valid_transitions_from_shares_call_open(self) -> None:
        """SHARES_CALL_OPEN should allow expiry outcomes."""
        actions = get_valid_actions(WheelState.SHARES_CALL_OPEN)
        assert "expired_otm" in actions
        assert "called_away" in actions
        assert "closed_early" in actions

    def test_can_transition_valid(self) -> None:
        """can_transition should return True for valid actions."""
        assert can_transition(WheelState.CASH, "sell_put") is True
        assert can_transition(WheelState.SHARES, "sell_call") is True
        assert can_transition(WheelState.CASH_PUT_OPEN, "expired_otm") is True
        assert can_transition(WheelState.CASH_PUT_OPEN, "assigned") is True

    def test_can_transition_invalid(self) -> None:
        """can_transition should return False for invalid actions."""
        assert can_transition(WheelState.CASH, "sell_call") is False
        assert can_transition(WheelState.SHARES, "sell_put") is False
        assert can_transition(WheelState.CASH, "assigned") is False

    def test_get_next_state_sell_put(self) -> None:
        """Selling put from CASH should go to CASH_PUT_OPEN."""
        next_state = get_next_state(WheelState.CASH, "sell_put")
        assert next_state == WheelState.CASH_PUT_OPEN

    def test_get_next_state_put_expired_otm(self) -> None:
        """Put expiring OTM should return to CASH."""
        next_state = get_next_state(WheelState.CASH_PUT_OPEN, "expired_otm")
        assert next_state == WheelState.CASH

    def test_get_next_state_put_assigned(self) -> None:
        """Put being assigned should go to SHARES."""
        next_state = get_next_state(WheelState.CASH_PUT_OPEN, "assigned")
        assert next_state == WheelState.SHARES

    def test_get_next_state_sell_call(self) -> None:
        """Selling call from SHARES should go to SHARES_CALL_OPEN."""
        next_state = get_next_state(WheelState.SHARES, "sell_call")
        assert next_state == WheelState.SHARES_CALL_OPEN

    def test_get_next_state_call_expired_otm(self) -> None:
        """Call expiring OTM should stay in SHARES."""
        next_state = get_next_state(WheelState.SHARES_CALL_OPEN, "expired_otm")
        assert next_state == WheelState.SHARES

    def test_get_next_state_call_called_away(self) -> None:
        """Call being exercised should go to CASH."""
        next_state = get_next_state(WheelState.SHARES_CALL_OPEN, "called_away")
        assert next_state == WheelState.CASH

    def test_get_next_state_closed_early_from_put(self) -> None:
        """Closing put early should return to CASH."""
        next_state = get_next_state(WheelState.CASH_PUT_OPEN, "closed_early")
        assert next_state == WheelState.CASH

    def test_get_next_state_closed_early_from_call(self) -> None:
        """Closing call early should stay in SHARES."""
        next_state = get_next_state(WheelState.SHARES_CALL_OPEN, "closed_early")
        assert next_state == WheelState.SHARES

    def test_get_next_state_invalid_action(self) -> None:
        """Invalid action should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_next_state(WheelState.CASH, "invalid_action")

        assert "Invalid action" in str(exc_info.value)

    def test_get_next_state_invalid_from_state(self) -> None:
        """Selling call from CASH should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_next_state(WheelState.CASH, "sell_call")

        assert "Invalid action" in str(exc_info.value)


class TestFullWheelCycle:
    """Test complete wheel strategy cycles."""

    def test_cash_to_cash_cycle(self) -> None:
        """Test a complete put-expired-worthless cycle."""
        state = WheelState.CASH

        # Sell put
        state = get_next_state(state, "sell_put")
        assert state == WheelState.CASH_PUT_OPEN

        # Put expires OTM
        state = get_next_state(state, "expired_otm")
        assert state == WheelState.CASH

    def test_cash_to_shares_to_cash_cycle(self) -> None:
        """Test a complete wheel cycle with assignment."""
        state = WheelState.CASH

        # Sell put
        state = get_next_state(state, "sell_put")
        assert state == WheelState.CASH_PUT_OPEN

        # Put assigned
        state = get_next_state(state, "assigned")
        assert state == WheelState.SHARES

        # Sell call
        state = get_next_state(state, "sell_call")
        assert state == WheelState.SHARES_CALL_OPEN

        # Call exercised
        state = get_next_state(state, "called_away")
        assert state == WheelState.CASH

    def test_shares_to_shares_cycle(self) -> None:
        """Test a complete call-expired-worthless cycle."""
        state = WheelState.SHARES

        # Sell call
        state = get_next_state(state, "sell_call")
        assert state == WheelState.SHARES_CALL_OPEN

        # Call expires OTM
        state = get_next_state(state, "expired_otm")
        assert state == WheelState.SHARES
