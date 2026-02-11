"""
TastyTrade brokerage integration for Alex AI Assistant.

Provides trading capabilities with mandatory confirmation flow.
"""

from alex.brokerage.tastytrade_client import (
    get_session,
    get_accounts,
    get_primary_account,
    close_session,
    is_sandbox_mode,
    TastyTradeSession,
)
from alex.brokerage.tastytrade_tools import (
    get_positions,
    get_account_balances,
    place_order_dry_run,
    close_position_dry_run,
    confirm_trade,
    cancel_pending_trade,
    execute_trade_tool,
    TRADE_TOOL_DEFINITIONS,
)

__all__ = [
    # Client
    "get_session",
    "get_accounts",
    "get_primary_account",
    "close_session",
    "is_sandbox_mode",
    "TastyTradeSession",
    # Tools
    "get_positions",
    "get_account_balances",
    "place_order_dry_run",
    "close_position_dry_run",
    "confirm_trade",
    "cancel_pending_trade",
    "execute_trade_tool",
    "TRADE_TOOL_DEFINITIONS",
]
