"""
Edge definitions for Alex AI Assistant LangGraph.

Defines conditional routing between nodes based on state.
"""

from typing import Literal

import structlog

from alex.agents.state import AlexState, get_last_user_message, get_last_assistant_message
from alex.cortex.router import route_to_cortex

logger = structlog.get_logger()


def route_after_classify(
    state: AlexState,
) -> Literal["retrieve_memory", "respond_flash", "respond_pro", "engineer", "self_modify", "trade", "error"]:
    """
    Route after intent classification.

    Determines the next node based on:
    - Whether memory retrieval is needed
    - The complexity of the request
    - The type of task (chat vs engineering vs self-modification)
    """
    # Check for errors
    if state.get("error") or state.get("processing_stage") == "error":
        return "error"

    # Check for self-modification intent first
    metadata = state.get("metadata")
    if metadata and metadata.intent == "self_modify":
        logger.info("Routing to self-modification node")
        return "self_modify"

    # Check for trading intent
    if metadata and metadata.intent == "trade":
        logger.info("Routing to trade node")
        return "trade"

    # Determine target cortex
    cortex = route_to_cortex(state)

    # Engineering tasks need special handling
    if cortex == "claude_code":
        logger.info("Routing to engineering node")
        return "engineer"

    # Memory-intensive queries should retrieve context first
    memory_intents = {"memory_query", "question", "task_planning"}
    if metadata and metadata.intent in memory_intents:
        logger.info("Routing to memory retrieval")
        return "retrieve_memory"

    # Route to appropriate cortex
    if cortex == "pro":
        logger.info("Routing to Pro")
        return "respond_pro"

    logger.info("Routing to Flash")
    return "respond_flash"


def route_after_memory(
    state: AlexState,
) -> Literal["respond_flash", "respond_pro", "error"]:
    """
    Route after memory retrieval.

    Chooses between Flash and Pro based on complexity.
    """
    if state.get("error") or state.get("processing_stage") == "error":
        return "error"

    # Use Pro for high complexity or memory-heavy tasks
    metadata = state.get("metadata")
    if metadata and metadata.complexity_score >= 0.7:
        return "respond_pro"

    # Check if memory context suggests complexity
    memory_context = state.get("memory_context")
    if memory_context and memory_context.relevant_interactions and len(
        memory_context.relevant_interactions
    ) > 3:
        return "respond_pro"

    return "respond_flash"


def should_store(state: AlexState) -> Literal["store", "complete"]:
    """
    Determine if the interaction should be stored.

    Store interactions unless:
    - There was an error
    - The conversation is too short
    """
    if state.get("error"):
        return "complete"

    user_msg = get_last_user_message(state)
    assistant_msg = get_last_assistant_message(state)

    # Don't store very short interactions
    if not user_msg or not assistant_msg:
        return "complete"

    if len(user_msg) < 5 or len(assistant_msg) < 10:
        return "complete"

    return "store"
