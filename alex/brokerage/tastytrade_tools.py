"""
TastyTrade trading tools for Alex AI Assistant.

Provides tools for Gemini function calling to interact with TastyTrade API.
All order placements require a two-step confirmation flow:
1. Dry-run validates the order and returns a trade_id
2. confirm_trade() executes the validated trade

Safety mechanisms:
- All orders go through dry-run first
- Trade IDs expire after 5 minutes
- Explicit user confirmation required before execution
"""

import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import structlog

from alex.brokerage.tastytrade_client import get_session, get_primary_account, is_sandbox_mode

logger = structlog.get_logger()

# In-memory store for pending trades (trade_id -> PendingTrade)
# Thread-safe using a lock. In production, consider using Redis or database
_pending_trades: dict[str, "PendingTrade"] = {}
_pending_trades_lock = threading.Lock()

# Trade expiration time in seconds (5 minutes)
TRADE_EXPIRATION_SECONDS = 300


@dataclass
class PendingTrade:
    """Represents a validated but not yet executed trade."""

    trade_id: str
    account_number: str
    symbol: str
    action: str  # "buy" or "sell"
    quantity: int
    order_type: str  # "market" or "limit"
    limit_price: Decimal | None
    instrument_type: str  # "equity" or "option"
    option_symbol: str | None  # Full OCC symbol for options
    description: str
    order_payload: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if the pending trade has expired."""
        return time.time() - self.created_at > TRADE_EXPIRATION_SECONDS


def _cleanup_expired_trades():
    """Remove expired pending trades. Thread-safe."""
    with _pending_trades_lock:
        expired = [tid for tid, trade in _pending_trades.items() if trade.is_expired()]
        for tid in expired:
            del _pending_trades[tid]
            logger.info("Expired pending trade removed", trade_id=tid)


async def get_positions() -> dict[str, Any]:
    """
    Get all current positions with P&L information.

    Returns:
        Dictionary with positions data and metadata
    """
    try:
        session = get_session()
        account = get_primary_account()
        account_number = account.get("account-number", "")

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{session.api_url}/accounts/{account_number}/positions",
                headers=session.headers,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get positions: {response.status_code}",
                }

            data = response.json()
            items = data.get("data", {}).get("items", [])

            position_list = []
            for item in items:
                position_list.append({
                    "symbol": item.get("symbol"),
                    "quantity": item.get("quantity"),
                    "quantity_direction": item.get("quantity-direction"),
                    "average_open_price": item.get("average-open-price"),
                    "close_price": item.get("close-price"),
                    "instrument_type": item.get("instrument-type"),
                    "underlying_symbol": item.get("underlying-symbol"),
                })

            logger.info("Retrieved positions", count=len(position_list))

            return {
                "success": True,
                "account_number": account_number,
                "mode": "SANDBOX" if is_sandbox_mode() else "LIVE",
                "positions": position_list,
                "count": len(position_list),
            }

    except Exception as e:
        logger.error("Failed to get positions", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


async def get_account_balances() -> dict[str, Any]:
    """
    Get account balances including cash, buying power, and net liquidating value.

    Returns:
        Dictionary with balance information
    """
    try:
        session = get_session()
        account = get_primary_account()
        account_number = account.get("account-number", "")

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{session.api_url}/accounts/{account_number}/balances",
                headers=session.headers,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get balances: {response.status_code}",
                }

            data = response.json().get("data", {})

            result = {
                "success": True,
                "account_number": account_number,
                "mode": "SANDBOX" if is_sandbox_mode() else "LIVE",
                "cash_balance": data.get("cash-balance"),
                "net_liquidating_value": data.get("net-liquidating-value"),
                "equity_buying_power": data.get("equity-buying-power"),
                "derivative_buying_power": data.get("derivative-buying-power"),
                "day_trading_buying_power": data.get("day-trading-buying-power"),
            }

            logger.info("Retrieved account balances", account=account_number[:4] + "****")

            return result

    except Exception as e:
        logger.error("Failed to get balances", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


async def place_order_dry_run(
    symbol: str,
    action: str,
    quantity: int,
    order_type: str = "market",
    limit_price: float | None = None,
    instrument_type: str = "equity",
    option_symbol: str | None = None,
) -> dict[str, Any]:
    """
    Validate an order without executing it. Returns a trade_id for confirmation.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL")
        action: "buy" or "sell"
        quantity: Number of shares or contracts
        order_type: "market" or "limit"
        limit_price: Required for limit orders
        instrument_type: "equity" or "option"
        option_symbol: Full OCC symbol for options (e.g., "AAPL  240119C00185000")

    Returns:
        Dictionary with trade_id and order details for user confirmation
    """
    _cleanup_expired_trades()

    try:
        # Validate inputs
        action = action.lower()
        if action not in ("buy", "sell"):
            return {"success": False, "error": "Action must be 'buy' or 'sell'"}

        order_type = order_type.lower()
        if order_type not in ("market", "limit"):
            return {"success": False, "error": "Order type must be 'market' or 'limit'"}

        if order_type == "limit" and limit_price is None:
            return {"success": False, "error": "Limit price required for limit orders"}

        if quantity <= 0:
            return {"success": False, "error": "Quantity must be positive"}

        instrument_type = instrument_type.lower()
        if instrument_type not in ("equity", "option"):
            return {"success": False, "error": "Instrument type must be 'equity' or 'option'"}

        if instrument_type == "option" and not option_symbol:
            return {"success": False, "error": "Option symbol required for option orders"}

        session = get_session()
        account = get_primary_account()
        account_number = account.get("account-number", "")

        # Build order payload for TastyTrade API
        if action == "buy":
            order_action = "Buy to Open"
        else:
            order_action = "Sell to Close"

        leg_symbol = option_symbol if instrument_type == "option" else symbol

        order_payload = {
            "time-in-force": "Day",
            "order-type": "Market" if order_type == "market" else "Limit",
            "legs": [
                {
                    "action": order_action,
                    "symbol": leg_symbol,
                    "quantity": quantity,
                    "instrument-type": "Equity" if instrument_type == "equity" else "Equity Option",
                }
            ],
        }

        if order_type == "limit" and limit_price is not None:
            order_payload["price"] = str(limit_price)
            order_payload["price-effect"] = "Debit" if action == "buy" else "Credit"

        # Validate by doing a dry run
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{session.api_url}/accounts/{account_number}/orders/dry-run",
                headers=session.headers,
                json=order_payload,
            )

            if response.status_code not in (200, 201):
                error_data = response.json().get("error", {})
                return {
                    "success": False,
                    "error": error_data.get("message", f"Order validation failed: {response.status_code}"),
                }

            validation_data = response.json().get("data", {})

        # Generate trade_id and store pending trade
        trade_id = str(uuid4())[:8]

        # Build description
        price_str = f" @ ${limit_price}" if limit_price else " @ market"
        if instrument_type == "option":
            description = f"{action.upper()} {quantity} {option_symbol}{price_str}"
        else:
            description = f"{action.upper()} {quantity} {symbol}{price_str}"

        pending = PendingTrade(
            trade_id=trade_id,
            account_number=account_number,
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            limit_price=Decimal(str(limit_price)) if limit_price else None,
            instrument_type=instrument_type,
            option_symbol=option_symbol,
            description=description,
            order_payload=order_payload,
        )
        with _pending_trades_lock:
            _pending_trades[trade_id] = pending

        logger.info(
            "Order validated (dry run)",
            trade_id=trade_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
        )

        return {
            "success": True,
            "trade_id": trade_id,
            "mode": "SANDBOX" if is_sandbox_mode() else "LIVE",
            "description": description,
            "requires_confirmation": True,
            "expires_in_seconds": TRADE_EXPIRATION_SECONDS,
            "order_details": {
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": str(limit_price) if limit_price else None,
                "instrument_type": instrument_type,
            },
            "validation_response": {
                "buying_power_effect": validation_data.get("buying-power-effect", {}).get(
                    "change-in-buying-power"
                ),
                "fee": validation_data.get("fee"),
            },
            "message": f"Ready to execute: {description}. Say 'confirm' or use confirm_trade('{trade_id}') to execute.",
        }

    except Exception as e:
        logger.error("Order validation failed", error=str(e), symbol=symbol)
        return {
            "success": False,
            "error": str(e),
        }


async def close_position_dry_run(
    symbol: str,
    quantity: int | None = None,
) -> dict[str, Any]:
    """
    Validate closing a position without executing. Returns a trade_id for confirmation.

    Args:
        symbol: Stock ticker symbol to close
        quantity: Number of shares to close (None = close entire position)

    Returns:
        Dictionary with trade_id and order details for user confirmation
    """
    _cleanup_expired_trades()

    try:
        # Get current positions
        positions_result = await get_positions()
        if not positions_result.get("success"):
            return positions_result

        positions = positions_result.get("positions", [])

        # Find the position
        position = None
        for pos in positions:
            if pos.get("symbol") == symbol or pos.get("underlying_symbol") == symbol:
                position = pos
                break

        if not position:
            return {
                "success": False,
                "error": f"No position found for {symbol}",
            }

        # Determine quantity to close
        pos_quantity = abs(int(position.get("quantity", 0)))
        close_quantity = quantity if quantity else pos_quantity

        if close_quantity > pos_quantity:
            return {
                "success": False,
                "error": f"Cannot close {close_quantity} shares. Position only has {pos_quantity}.",
            }

        # Determine action based on position direction
        if int(position.get("quantity", 0)) > 0:
            action = "sell"
        else:
            action = "buy"  # Short position, buy to close

        # Use place_order_dry_run for the actual validation
        instrument_type = (position.get("instrument_type") or "equity").lower()
        if "option" in instrument_type:
            instrument_type = "option"
        else:
            instrument_type = "equity"

        option_symbol = position.get("symbol") if instrument_type == "option" else None

        result = await place_order_dry_run(
            symbol=symbol if instrument_type == "equity" else (position.get("underlying_symbol") or symbol),
            action=action,
            quantity=close_quantity,
            order_type="market",
            instrument_type=instrument_type,
            option_symbol=option_symbol,
        )

        if result.get("success"):
            result["message"] = f"Ready to close: {result['description']}. Say 'confirm' or use confirm_trade('{result['trade_id']}') to execute."
            result["position_info"] = {
                "current_quantity": pos_quantity,
                "closing_quantity": close_quantity,
                "remaining_after_close": pos_quantity - close_quantity,
            }

        return result

    except Exception as e:
        logger.error("Close position validation failed", error=str(e), symbol=symbol)
        return {
            "success": False,
            "error": str(e),
        }


async def confirm_trade(trade_id: str) -> dict[str, Any]:
    """
    Execute a previously validated trade.

    Args:
        trade_id: The trade_id returned from place_order_dry_run or close_position_dry_run

    Returns:
        Dictionary with execution results
    """
    _cleanup_expired_trades()

    try:
        with _pending_trades_lock:
            pending = _pending_trades.get(trade_id)

            if not pending:
                return {
                    "success": False,
                    "error": f"Trade {trade_id} not found or has expired. Please create a new order.",
                }

            if pending.is_expired():
                del _pending_trades[trade_id]
                return {
                    "success": False,
                    "error": f"Trade {trade_id} has expired. Please create a new order.",
                }

            # Remove from pending before execution to prevent double execution
            del _pending_trades[trade_id]

        session = get_session()

        # Execute the order (outside lock to avoid holding it during API call)
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{session.api_url}/accounts/{pending.account_number}/orders",
                headers=session.headers,
                json=pending.order_payload,
            )

            if response.status_code not in (200, 201):
                error_data = response.json().get("error", {})
                return {
                    "success": False,
                    "error": error_data.get("message", f"Order execution failed: {response.status_code}"),
                    "trade_id": trade_id,
                }

            order_data = response.json().get("data", {})
            order = order_data.get("order", {})

        logger.info(
            "Trade executed",
            trade_id=trade_id,
            order_id=order.get("id"),
            description=pending.description,
        )

        return {
            "success": True,
            "trade_id": trade_id,
            "mode": "SANDBOX" if is_sandbox_mode() else "LIVE",
            "description": pending.description,
            "executed": True,
            "order_id": order.get("id"),
            "status": order.get("status"),
            "message": f"Trade executed successfully: {pending.description}",
        }

    except Exception as e:
        logger.error("Trade execution failed", error=str(e), trade_id=trade_id)
        return {
            "success": False,
            "error": str(e),
            "trade_id": trade_id,
        }


async def cancel_pending_trade(trade_id: str) -> dict[str, Any]:
    """
    Cancel a pending trade without executing it.

    Args:
        trade_id: The trade_id to cancel

    Returns:
        Dictionary with cancellation result
    """
    with _pending_trades_lock:
        pending = _pending_trades.pop(trade_id, None)

    if pending:
        logger.info("Pending trade cancelled", trade_id=trade_id)
        return {
            "success": True,
            "trade_id": trade_id,
            "cancelled": True,
            "message": f"Trade {trade_id} cancelled: {pending.description}",
        }
    else:
        return {
            "success": False,
            "error": f"Trade {trade_id} not found or already expired/executed.",
        }


# Tool definitions for Gemini function calling
TRADE_TOOL_DEFINITIONS = [
    {
        "name": "get_positions",
        "description": "Get all current stock and option positions with P&L information from the TastyTrade account.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_account_balances",
        "description": "Get account balances including cash, buying power, and net liquidating value from TastyTrade.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "place_order_dry_run",
        "description": "Validate a stock or option order WITHOUT executing it. Returns a trade_id that must be confirmed to execute. Use this for buying or selling.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL', 'TSLA')",
                },
                "action": {
                    "type": "string",
                    "enum": ["buy", "sell"],
                    "description": "Whether to buy or sell",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of shares or contracts",
                },
                "order_type": {
                    "type": "string",
                    "enum": ["market", "limit"],
                    "description": "Order type (default: market)",
                },
                "limit_price": {
                    "type": "number",
                    "description": "Limit price (required for limit orders)",
                },
                "instrument_type": {
                    "type": "string",
                    "enum": ["equity", "option"],
                    "description": "Type of instrument (default: equity)",
                },
                "option_symbol": {
                    "type": "string",
                    "description": "Full OCC option symbol for option trades",
                },
            },
            "required": ["symbol", "action", "quantity"],
        },
    },
    {
        "name": "close_position_dry_run",
        "description": "Validate closing an existing position WITHOUT executing it. Returns a trade_id that must be confirmed to execute.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol to close",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of shares to close (omit to close entire position)",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "confirm_trade",
        "description": "Execute a previously validated trade. Requires the trade_id from a dry-run order.",
        "parameters": {
            "type": "object",
            "properties": {
                "trade_id": {
                    "type": "string",
                    "description": "The trade_id from the dry-run validation",
                },
            },
            "required": ["trade_id"],
        },
    },
    {
        "name": "cancel_pending_trade",
        "description": "Cancel a pending trade without executing it.",
        "parameters": {
            "type": "object",
            "properties": {
                "trade_id": {
                    "type": "string",
                    "description": "The trade_id to cancel",
                },
            },
            "required": ["trade_id"],
        },
    },
]


async def execute_trade_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a trading tool by name.

    Args:
        tool_name: Name of the tool to execute
        args: Tool arguments

    Returns:
        Tool execution result
    """
    tools = {
        "get_positions": get_positions,
        "get_account_balances": get_account_balances,
        "place_order_dry_run": place_order_dry_run,
        "close_position_dry_run": close_position_dry_run,
        "confirm_trade": confirm_trade,
        "cancel_pending_trade": cancel_pending_trade,
    }

    if tool_name not in tools:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    return await tools[tool_name](**args)
