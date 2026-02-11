"""
Trade response node for Alex AI Assistant.

Handles trading operations through TastyTrade with mandatory confirmation flow.
All trades go through dry-run validation before execution.
"""

import json
import time
from typing import Any
from uuid import uuid4

import structlog
from google import genai
from langchain_core.messages import AIMessage

from alex.agents.state import AlexState, get_last_user_message
from alex.brokerage.tastytrade_client import is_sandbox_mode
from alex.brokerage.tastytrade_tools import (
    TRADE_TOOL_DEFINITIONS,
    execute_trade_tool,
)
from alex.config import settings
from alex.cortex.flash import get_client
from alex.memory.postgres_store import PostgresStore

logger = structlog.get_logger()


def _get_trading_mode_display() -> str:
    """Get display string for current trading mode."""
    return "🧪 SANDBOX (Paper Trading)" if is_sandbox_mode() else "🔴 LIVE TRADING"


TRADE_SYSTEM_PROMPT = """You are Alex, an AI assistant with trading capabilities through TastyTrade.

## Current Trading Mode
{trading_mode}

## CRITICAL SAFETY RULES
1. **ALWAYS use dry-run first**: Before ANY trade execution, call place_order_dry_run or close_position_dry_run
2. **ALWAYS require confirmation**: After dry-run, present the trade details to the user and wait for explicit confirmation (e.g., "yes", "confirm", "do it")
3. **NEVER auto-execute**: Do not call confirm_trade until the user explicitly confirms
4. **Be transparent**: Always show the mode (SANDBOX/LIVE) and order details

## Available Trading Tools
- get_positions: View current stock/option positions
- get_account_balances: Check cash, buying power, net liquidating value
- place_order_dry_run: Validate a buy/sell order (returns trade_id for confirmation)
- close_position_dry_run: Validate closing a position (returns trade_id for confirmation)
- confirm_trade: Execute a validated trade (only after user confirms!)
- cancel_pending_trade: Cancel a pending trade

## Confirmation Flow
1. User requests a trade
2. Call dry-run tool to validate → get trade_id
3. Present trade details: "Ready to [action] [quantity] [symbol] at [price]. This is [mode] mode. Confirm?"
4. WAIT for user to say "yes", "confirm", "execute", etc.
5. Only then call confirm_trade(trade_id)

## When User Confirms
If the user says "yes", "confirm", "do it", "execute", or similar affirmative:
- If there's a pending trade_id from the previous message, call confirm_trade with that trade_id
- If no trade_id exists, ask them to specify the trade first

## Response Style
- Be concise but informative
- Always show P&L for positions
- Format numbers with commas and appropriate decimals
- Use tables for multiple positions
"""


def _get_gemini_trade_tools() -> list:
    """Convert trade tool definitions to Gemini function declarations."""
    declarations = []
    for tool in TRADE_TOOL_DEFINITIONS:
        declarations.append(
            genai.types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["parameters"],
            )
        )
    return [genai.types.Tool(function_declarations=declarations)]


async def respond_trade(state: AlexState) -> dict[str, Any]:
    """
    Handle trading requests using TastyTrade tools.

    This node:
    1. Processes trading requests (positions, balances, orders)
    2. Enforces dry-run → confirmation flow for all trades
    3. Logs executed trades for audit

    Args:
        state: Current agent state

    Returns:
        Updated state with response
    """
    start_time = time.time()
    metadata = state.get("metadata")
    session_id = state.get("session_id")
    user_id = state.get("user_id", "primary_user")

    logger.info(
        "Trade node processing",
        session_id=session_id,
        mode="sandbox" if is_sandbox_mode() else "live",
    )

    executed_trades = []

    try:
        user_message = get_last_user_message(state)
        if not user_message:
            raise ValueError("No user message found")

        # Build system prompt with trading mode
        system_prompt = TRADE_SYSTEM_PROMPT.format(
            trading_mode=_get_trading_mode_display()
        )

        # Initialize Gemini client with trading tools
        client = get_client()
        tools = _get_gemini_trade_tools()

        # Build conversation
        contents = [
            genai.types.Content(
                role="user",
                parts=[
                    genai.types.Part(
                        text=f"{system_prompt}\n\nUser request: {user_message}"
                    )
                ],
            )
        ]

        # Track tool calls
        tool_results = []
        max_iterations = 10
        iteration = 0

        # Agentic loop with tool calling
        while iteration < max_iterations:
            iteration += 1

            response = await client.aio.models.generate_content(
                model=settings.flash_model,
                contents=contents,
                config=genai.types.GenerateContentConfig(
                    tools=tools,
                    temperature=0.3,  # Lower temperature for trading
                ),
            )

            # Check for function calls
            if response.candidates and response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts
                has_function_call = any(
                    hasattr(part, "function_call") and part.function_call
                    for part in parts
                )

                if has_function_call:
                    function_responses = []

                    for part in parts:
                        if hasattr(part, "function_call") and part.function_call:
                            func_call = part.function_call
                            func_name = func_call.name
                            # Handle different arg formats from Gemini SDK
                            if func_call.args:
                                try:
                                    # Try direct dict conversion
                                    func_args = dict(func_call.args)
                                except (TypeError, ValueError):
                                    # Fallback: iterate over items if it's a protobuf map
                                    func_args = {k: v for k, v in func_call.args.items()}
                            else:
                                func_args = {}

                            logger.info(
                                "Executing trade tool",
                                tool=func_name,
                                args=func_args,
                                args_type=type(func_call.args).__name__ if func_call.args else "None",
                            )

                            # Execute the tool
                            result = await execute_trade_tool(func_name, func_args)
                            tool_results.append(
                                {
                                    "tool": func_name,
                                    "args": func_args,
                                    "result": result,
                                }
                            )

                            # Track executed trades for audit logging
                            if func_name == "confirm_trade" and result.get("success"):
                                executed_trades.append(
                                    {
                                        "trade_id": result.get("trade_id"),
                                        "order_id": result.get("order_id"),
                                        "description": result.get("description"),
                                    }
                                )

                            function_responses.append(
                                genai.types.Part(
                                    function_response=genai.types.FunctionResponse(
                                        name=func_name,
                                        response={
                                            "result": json.dumps(result, default=str)
                                        },
                                    )
                                )
                            )

                    # Add to conversation
                    contents.append(response.candidates[0].content)
                    contents.append(
                        genai.types.Content(
                            role="user",
                            parts=function_responses,
                        )
                    )

                    continue

            # No more function calls, we have the final response
            break

        # Extract final text response
        final_response = ""
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    final_response += part.text

        # Store executed trades in database for audit
        if executed_trades:
            postgres_store = PostgresStore()
            for trade in executed_trades:
                try:
                    # Parse description to extract details
                    await postgres_store.store_trade(
                        trade_id=trade.get("trade_id", str(uuid4())[:8]),
                        user_id=user_id,
                        order_id=trade.get("order_id"),
                        description=trade.get("description", ""),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to store trade audit log",
                        error=str(e),
                        trade_id=trade.get("trade_id"),
                    )

        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)

        # Update metadata
        if metadata:
            metadata.model_used = settings.flash_model
            metadata.latency_ms = latency_ms

        logger.info(
            "Trade node complete",
            tool_calls=len(tool_results),
            executed_trades=len(executed_trades),
            latency_ms=latency_ms,
        )

        return {
            "messages": [AIMessage(content=final_response)],
            "current_cortex": "trade",
            "processing_stage": "trade",
            "tool_outputs": {
                "tool_results": tool_results,
                "executed_trades": executed_trades,
            },
            "metadata": metadata,
        }

    except ValueError as e:
        # Configuration errors (credentials not set)
        logger.warning("Trade configuration error", error=str(e))
        error_response = (
            f"Trading is not available: {str(e)}\n\n"
            "To enable trading, configure your TastyTrade credentials:\n"
            "- For sandbox: TASTY_SANDBOX_USERNAME and TASTY_SANDBOX_PASSWORD\n"
            "- For live: TASTY_USERNAME and TASTY_PASSWORD"
        )
        return {
            "messages": [AIMessage(content=error_response)],
            "current_cortex": "flash",
            "processing_stage": "error",
            "error": str(e),
        }

    except Exception as e:
        logger.error("Trade node failed", error=str(e))
        error_response = (
            f"I encountered an error while processing your trading request: {str(e)}\n\n"
            "Please try again or check your request."
        )
        return {
            "messages": [AIMessage(content=error_response)],
            "current_cortex": "flash",
            "processing_stage": "error",
            "error": str(e),
        }
