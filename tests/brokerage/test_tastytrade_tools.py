"""
Unit tests for TastyTrade trading tools.

Tests use mocked HTTP responses to verify tool behavior without
requiring actual API credentials.
"""

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from alex.brokerage.tastytrade_tools import (
    get_positions,
    get_account_balances,
    place_order_dry_run,
    close_position_dry_run,
    confirm_trade,
    cancel_pending_trade,
    _pending_trades,
    _pending_trades_lock,
    PendingTrade,
    TRADE_EXPIRATION_SECONDS,
)
from alex.brokerage.tastytrade_client import TastyTradeSession


@pytest.fixture
def mock_session():
    """Create a mock TastyTrade session."""
    return TastyTradeSession(
        session_token="mock_token_12345",
        remember_token=None,
        user_id="user123",
        email="test@example.com",
        is_sandbox=True,
    )


@pytest.fixture
def mock_account():
    """Create a mock account dictionary."""
    return {
        "account-number": "5WV12345",
        "nickname": "Test Account",
    }


@pytest.fixture
def mock_position():
    """Create a mock position dictionary."""
    return {
        "symbol": "AAPL",
        "quantity": 100,
        "quantity-direction": "Long",
        "average-open-price": "175.50",
        "close-price": "180.00",
        "instrument-type": "Equity",
        "underlying-symbol": None,
    }


@pytest.fixture
def mock_balances():
    """Create mock balance data."""
    return {
        "cash-balance": "10000.00",
        "net-liquidating-value": "25000.00",
        "equity-buying-power": "20000.00",
        "derivative-buying-power": "15000.00",
        "day-trading-buying-power": "80000.00",
    }


@pytest.fixture(autouse=True)
def clear_pending_trades():
    """Clear pending trades before each test."""
    with _pending_trades_lock:
        _pending_trades.clear()
    yield
    with _pending_trades_lock:
        _pending_trades.clear()


class TestGetPositions:
    """Tests for get_positions tool."""

    @pytest.mark.asyncio
    async def test_get_positions_success(self, mock_session, mock_account, mock_position):
        """Test successful position retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"items": [mock_position]}
        }

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", return_value=mock_account):
                with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                    with patch("httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                        result = await get_positions()

        assert result["success"] is True
        assert result["mode"] == "SANDBOX"
        assert result["count"] == 1
        assert len(result["positions"]) == 1
        assert result["positions"][0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, mock_session, mock_account):
        """Test position retrieval with no positions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"items": []}}

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", return_value=mock_account):
                with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                    with patch("httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                        result = await get_positions()

        assert result["success"] is True
        assert result["count"] == 0
        assert result["positions"] == []

    @pytest.mark.asyncio
    async def test_get_positions_error(self, mock_session):
        """Test position retrieval with error."""
        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", side_effect=ValueError("No accounts")):
                result = await get_positions()

        assert result["success"] is False
        assert "error" in result


class TestGetAccountBalances:
    """Tests for get_account_balances tool."""

    @pytest.mark.asyncio
    async def test_get_balances_success(self, mock_session, mock_account, mock_balances):
        """Test successful balance retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": mock_balances}

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", return_value=mock_account):
                with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                    with patch("httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                        result = await get_account_balances()

        assert result["success"] is True
        assert result["cash_balance"] == "10000.00"
        assert result["net_liquidating_value"] == "25000.00"
        assert result["equity_buying_power"] == "20000.00"


class TestPlaceOrderDryRun:
    """Tests for place_order_dry_run tool."""

    @pytest.mark.asyncio
    async def test_place_order_validates_action(self):
        """Test that invalid action is rejected."""
        result = await place_order_dry_run(
            symbol="AAPL",
            action="invalid",
            quantity=100,
        )

        assert result["success"] is False
        assert "buy" in result["error"].lower() or "sell" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_place_order_validates_order_type(self):
        """Test that invalid order type is rejected."""
        result = await place_order_dry_run(
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="invalid",
        )

        assert result["success"] is False
        assert "market" in result["error"].lower() or "limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_place_order_requires_limit_price(self):
        """Test that limit orders require a price."""
        result = await place_order_dry_run(
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="limit",
            limit_price=None,
        )

        assert result["success"] is False
        assert "limit price" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_place_order_validates_quantity(self):
        """Test that quantity must be positive."""
        result = await place_order_dry_run(
            symbol="AAPL",
            action="buy",
            quantity=0,
        )

        assert result["success"] is False
        assert "quantity" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_place_order_dry_run_success(self, mock_session, mock_account):
        """Test successful order dry-run."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "buying-power-effect": {"change-in-buying-power": "-17550.00"},
                "fee": "0.00",
            }
        }

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", return_value=mock_account):
                with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                    with patch("httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
                        result = await place_order_dry_run(
                            symbol="AAPL",
                            action="buy",
                            quantity=100,
                        )

        assert result["success"] is True
        assert "trade_id" in result
        assert result["requires_confirmation"] is True
        assert result["mode"] == "SANDBOX"
        assert "AAPL" in result["description"]
        with _pending_trades_lock:
            assert result["trade_id"] in _pending_trades


class TestConfirmTrade:
    """Tests for confirm_trade tool."""

    @pytest.mark.asyncio
    async def test_confirm_trade_not_found(self):
        """Test confirming a non-existent trade."""
        result = await confirm_trade("nonexistent123")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_confirm_trade_expired(self):
        """Test confirming an expired trade."""
        # Create an expired pending trade
        pending = PendingTrade(
            trade_id="expired123",
            account_number="5WV12345",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            instrument_type="equity",
            option_symbol=None,
            description="BUY 100 AAPL @ market",
            order_payload={},
            created_at=time.time() - TRADE_EXPIRATION_SECONDS - 100,  # Expired
        )
        with _pending_trades_lock:
            _pending_trades["expired123"] = pending

        result = await confirm_trade("expired123")

        assert result["success"] is False
        assert "expired" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_confirm_trade_success(self, mock_session):
        """Test successful trade confirmation."""
        # Create a valid pending trade
        pending = PendingTrade(
            trade_id="valid123",
            account_number="5WV12345",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            instrument_type="equity",
            option_symbol=None,
            description="BUY 100 AAPL @ market",
            order_payload={"time-in-force": "Day", "order-type": "Market", "legs": []},
            created_at=time.time(),
        )
        with _pending_trades_lock:
            _pending_trades["valid123"] = pending

        # Mock execution response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "data": {
                "order": {"id": "order_456", "status": "Filled"}
            }
        }

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                with patch("httpx.Client") as mock_client:
                    mock_client.return_value.__enter__.return_value.post.return_value = mock_response
                    result = await confirm_trade("valid123")

        assert result["success"] is True
        assert result["executed"] is True
        assert result["order_id"] == "order_456"
        with _pending_trades_lock:
            assert "valid123" not in _pending_trades  # Should be removed


class TestCancelPendingTrade:
    """Tests for cancel_pending_trade tool."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        """Test cancelling a non-existent trade."""
        result = await cancel_pending_trade("nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_cancel_success(self):
        """Test successful cancellation."""
        pending = PendingTrade(
            trade_id="cancel123",
            account_number="5WV12345",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            instrument_type="equity",
            option_symbol=None,
            description="BUY 100 AAPL @ market",
            order_payload={},
            created_at=time.time(),
        )
        with _pending_trades_lock:
            _pending_trades["cancel123"] = pending

        result = await cancel_pending_trade("cancel123")

        assert result["success"] is True
        assert result["cancelled"] is True
        with _pending_trades_lock:
            assert "cancel123" not in _pending_trades


class TestClosePositionDryRun:
    """Tests for close_position_dry_run tool."""

    @pytest.mark.asyncio
    async def test_close_position_not_found(self, mock_session, mock_account):
        """Test closing a position that doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"items": []}}

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", return_value=mock_account):
                with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                    with patch("httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                        result = await close_position_dry_run("AAPL")

        assert result["success"] is False
        assert "no position found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_close_position_quantity_too_high(self, mock_session, mock_account, mock_position):
        """Test closing more shares than owned."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"items": [mock_position]}}

        with patch("alex.brokerage.tastytrade_tools.get_session", return_value=mock_session):
            with patch("alex.brokerage.tastytrade_tools.get_primary_account", return_value=mock_account):
                with patch("alex.brokerage.tastytrade_tools.is_sandbox_mode", return_value=True):
                    with patch("httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
                        result = await close_position_dry_run("AAPL", quantity=500)  # Position only has 100

        assert result["success"] is False
        assert "cannot close" in result["error"].lower()


class TestPendingTradeExpiration:
    """Tests for pending trade expiration logic."""

    def test_is_expired_false(self):
        """Test that fresh trades are not expired."""
        pending = PendingTrade(
            trade_id="fresh",
            account_number="5WV12345",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            instrument_type="equity",
            option_symbol=None,
            description="BUY 100 AAPL @ market",
            order_payload={},
            created_at=time.time(),
        )

        assert pending.is_expired() is False

    def test_is_expired_true(self):
        """Test that old trades are expired."""
        pending = PendingTrade(
            trade_id="old",
            account_number="5WV12345",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            instrument_type="equity",
            option_symbol=None,
            description="BUY 100 AAPL @ market",
            order_payload={},
            created_at=time.time() - TRADE_EXPIRATION_SECONDS - 1,
        )

        assert pending.is_expired() is True
