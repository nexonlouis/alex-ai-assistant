"""
Main LangGraph definition for Alex AI Assistant.

Defines the agent graph structure with nodes and edges.
"""

from langgraph.graph import StateGraph, END
import structlog

from alex.agents.state import (
    AlexState,
    MemoryContext,
    InteractionMetadata,
    get_last_assistant_message,
)
from alex.agents.nodes.classify import classify_intent
from langchain_core.messages import HumanMessage, AIMessage
from alex.agents.nodes.memory import retrieve_memory, store_interaction
from alex.agents.nodes.chat import respond_flash, respond_pro
from alex.agents.nodes.engineer import respond_engineer
from alex.agents.nodes.self_modify import respond_self_modify
from alex.agents.nodes.trade import respond_trade
from alex.agents.edges import route_after_classify, route_after_memory, should_store

logger = structlog.get_logger()


def handle_error(state: AlexState) -> dict:
    """Handle errors in the graph."""
    error = state.get("error")
    logger.error("Error in agent graph", error=error)
    return {
        "messages": [
            AIMessage(content=f"I encountered an error: {error}. Please try again.")
        ],
        "processing_stage": "error",
    }


def create_alex_graph() -> StateGraph:
    """
    Create the Alex AI Assistant agent graph.

    Graph structure:
    ```
    START
      │
      ▼
    classify_intent
      │
      ├──[memory_query]──► retrieve_memory ──► respond_flash/pro ──► store ──► END
      │
      ├──[complex]──────► respond_pro ──────► store_interaction ──► END
      │
      ├──[engineering]──► respond_engineer (Claude) ──► store ──► END
      │
      ├──[self_modify]──► respond_self_modify ──► store ──► END
      │
      ├──[trade]────────► respond_trade ──► store ──► END
      │
      └──[simple]───────► respond_flash ───► store_interaction ──► END
    ```

    Cortex routing:
    - Flash (Gemini 3 Flash): Simple queries, routine tasks
    - Pro (Gemini 3 Pro): Complex analysis, architecture, planning
    - Claude Code (Claude Sonnet): Engineering tasks (code, refactor, debug, test)
    - Self-Modify (Gemini + Tools): Reading/modifying Alex's own codebase
    """
    # Create the graph builder
    builder = StateGraph(AlexState)

    # Add nodes
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("retrieve_memory", retrieve_memory)
    builder.add_node("respond_flash", respond_flash)
    builder.add_node("respond_pro", respond_pro)
    builder.add_node("respond_engineer", respond_engineer)
    builder.add_node("respond_self_modify", respond_self_modify)
    builder.add_node("respond_trade", respond_trade)
    builder.add_node("store_interaction", store_interaction)
    builder.add_node("handle_error", handle_error)

    # Set entry point
    builder.set_entry_point("classify_intent")

    # Add conditional edges from classify
    builder.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "retrieve_memory": "retrieve_memory",
            "respond_flash": "respond_flash",
            "respond_pro": "respond_pro",
            "engineer": "respond_engineer",  # Route to Claude Code
            "self_modify": "respond_self_modify",  # Route to self-modification
            "trade": "respond_trade",  # Route to TastyTrade trading
            "error": "handle_error",
        },
    )

    # Add conditional edges from memory retrieval
    builder.add_conditional_edges(
        "retrieve_memory",
        route_after_memory,
        {
            "respond_flash": "respond_flash",
            "respond_pro": "respond_pro",
            "error": "handle_error",
        },
    )

    # Add edges from response nodes to storage decision
    builder.add_conditional_edges(
        "respond_flash",
        should_store,
        {
            "store": "store_interaction",
            "complete": END,
        },
    )

    builder.add_conditional_edges(
        "respond_pro",
        should_store,
        {
            "store": "store_interaction",
            "complete": END,
        },
    )

    builder.add_conditional_edges(
        "respond_engineer",
        should_store,
        {
            "store": "store_interaction",
            "complete": END,
        },
    )

    builder.add_conditional_edges(
        "respond_self_modify",
        should_store,
        {
            "store": "store_interaction",
            "complete": END,
        },
    )

    builder.add_conditional_edges(
        "respond_trade",
        should_store,
        {
            "store": "store_interaction",
            "complete": END,
        },
    )

    # Storage and error handling go to END
    builder.add_edge("store_interaction", END)
    builder.add_edge("handle_error", END)

    return builder


# Compile the graph
_graph_builder = create_alex_graph()
alex_graph = _graph_builder.compile()


async def invoke_alex(
    user_message: str,
    user_id: str = "primary_user",
    session_id: str | None = None,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Invoke the Alex agent with a user message.

    Args:
        user_message: The user's message
        user_id: User identifier
        session_id: Optional session ID for conversation continuity
        conversation_history: Optional previous messages

    Returns:
        Agent response dictionary
    """
    from uuid import uuid4

    # Build initial messages list
    messages = []
    if conversation_history:
        for msg in conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_message))

    actual_session_id = session_id or str(uuid4())

    # Build initial state as dict (TypedDict)
    initial_state: AlexState = {
        "messages": messages,
        "user_id": user_id,
        "session_id": actual_session_id,
        "current_cortex": "flash",
        "processing_stage": "intake",
        "memory_context": MemoryContext(),
        "metadata": InteractionMetadata(),
        "tool_outputs": {},
        "error": None,
        "retry_count": 0,
        "max_retries": 3,
    }

    logger.info(
        "Invoking Alex agent",
        user_id=user_id,
        session_id=actual_session_id,
        message_length=len(user_message),
    )

    # Invoke the graph
    result = await alex_graph.ainvoke(initial_state)

    # Extract response from result (which is also a TypedDict)
    response_text = get_last_assistant_message(result)
    metadata = result.get("metadata")

    return {
        "response": response_text,
        "session_id": result.get("session_id"),
        "metadata": {
            "intent": metadata.intent if metadata else None,
            "complexity_score": metadata.complexity_score if metadata else 0.0,
            "model_used": metadata.model_used if metadata else None,
            "latency_ms": metadata.latency_ms if metadata else 0,
            "cortex": result.get("current_cortex"),
        },
    }
