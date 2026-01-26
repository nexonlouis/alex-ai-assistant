"""
Cortex router for Alex AI Assistant.

Determines which cortex (Flash or Pro) should handle a request
based on complexity, intent, and other factors.
"""

from typing import Literal

import structlog

from alex.agents.state import AlexState, get_last_assistant_message
from alex.config import settings

logger = structlog.get_logger()


def route_to_cortex(state: AlexState) -> Literal["flash", "pro", "claude_code"]:
    """
    Determine which cortex should handle the current request.

    Routing logic:
    1. Engineering tasks -> Claude Code
    2. High complexity -> Pro
    3. Ambiguous requests -> Pro
    4. Everything else -> Flash

    Args:
        state: Current agent state

    Returns:
        Cortex identifier: "flash", "pro", or "claude_code"
    """
    metadata = state.get("metadata")
    intent = metadata.intent if metadata else "chat"
    complexity = metadata.complexity_score if metadata else 0.3

    # Engineering tasks go to Claude Code
    engineering_intents = {"code_change", "refactor", "debug", "test", "deploy"}
    if intent in engineering_intents:
        logger.info("Routing to Claude Code", intent=intent)
        return "claude_code"

    # High complexity goes to Pro
    if complexity >= settings.complexity_threshold:
        logger.info(
            "Routing to Pro (high complexity)",
            complexity=complexity,
            threshold=settings.complexity_threshold,
        )
        return "pro"

    # Certain intents always go to Pro
    pro_intents = {"task_planning", "architecture", "analysis"}
    if intent in pro_intents:
        logger.info("Routing to Pro (intent type)", intent=intent)
        return "pro"

    # Default to Flash
    logger.info("Routing to Flash", intent=intent, complexity=complexity)
    return "flash"


def should_escalate(state: AlexState) -> bool:
    """
    Check if current request should be escalated from Flash to Pro.

    Called after initial Flash processing if the response seems inadequate
    or the task turns out to be more complex than initially assessed.

    Args:
        state: Current agent state

    Returns:
        True if should escalate to Pro
    """
    # Already on Pro or Claude Code
    if state.get("current_cortex") in ("pro", "claude_code"):
        return False

    # Check if Flash indicated uncertainty
    last_response = get_last_assistant_message(state)
    if last_response:
        uncertainty_markers = [
            "I'm not sure",
            "I don't have enough information",
            "This is complex",
            "Let me think more carefully",
            "I may need to reconsider",
        ]
        for marker in uncertainty_markers:
            if marker.lower() in last_response.lower():
                logger.info("Escalating to Pro (uncertainty detected)")
                return True

    # Check retry count
    if state.get("retry_count", 0) > 0:
        logger.info("Escalating to Pro (retry needed)")
        return True

    return False
