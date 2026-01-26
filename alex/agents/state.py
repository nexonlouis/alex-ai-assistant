"""
State definitions for Alex AI Assistant agent.

The AlexState is the central data structure that flows through the LangGraph,
carrying conversation history, memory context, and processing metadata.
"""

from datetime import datetime
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field


class MemoryContext(BaseModel):
    """Context retrieved from the knowledge graph."""

    daily_summary: str | None = None
    weekly_summary: str | None = None
    relevant_interactions: list[dict[str, Any]] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    related_projects: list[str] = Field(default_factory=list)
    retrieval_method: str = "hybrid"
    retrieval_score: float = 0.0


class InteractionMetadata(BaseModel):
    """Metadata about the current interaction."""

    interaction_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    intent: str | None = None
    complexity_score: float = 0.0
    topics_extracted: list[str] = Field(default_factory=list)
    entities_extracted: list[str] = Field(default_factory=list)
    model_used: str | None = None
    token_count_input: int = 0
    token_count_output: int = 0
    latency_ms: int = 0


class AlexState(TypedDict, total=False):
    """
    Core state for the Alex AI Assistant agent.

    This state flows through the LangGraph and carries all necessary
    information for processing user requests.

    Using TypedDict for LangGraph compatibility with message reducers.
    """

    # Conversation - uses LangGraph's add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # User info
    user_id: str
    session_id: str

    # Processing state
    current_cortex: str  # "flash" | "pro" | "claude_code"
    processing_stage: str

    # Memory
    memory_context: MemoryContext

    # Metadata
    metadata: InteractionMetadata

    # Tool outputs
    tool_outputs: dict[str, Any]

    # Error handling
    error: str | None
    retry_count: int
    max_retries: int


def get_last_user_message(state: AlexState) -> str | None:
    """Get the most recent user message from state."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
        elif isinstance(msg, dict) and msg.get("role") == "user":
            return msg.get("content")
    return None


def get_last_assistant_message(state: AlexState) -> str | None:
    """Get the most recent assistant message from state."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg.content
        elif isinstance(msg, dict) and msg.get("role") == "assistant":
            return msg.get("content")
    return None


def should_escalate_to_pro(state: AlexState) -> bool:
    """Determine if the request should be escalated to Gemini Pro."""
    metadata = state.get("metadata")
    if metadata:
        return metadata.complexity_score >= 0.7
    return False


def is_engineering_task(state: AlexState) -> bool:
    """Check if the current task requires Claude Code."""
    metadata = state.get("metadata")
    if metadata:
        engineering_intents = {"code_change", "refactor", "debug", "test", "deploy"}
        return metadata.intent in engineering_intents
    return False


def create_initial_state(
    user_message: str,
    user_id: str = "primary_user",
    session_id: str | None = None,
) -> AlexState:
    """Create an initial state for a new conversation."""
    return AlexState(
        messages=[HumanMessage(content=user_message)],
        user_id=user_id,
        session_id=session_id or str(uuid4()),
        current_cortex="flash",
        processing_stage="intake",
        memory_context=MemoryContext(),
        metadata=InteractionMetadata(),
        tool_outputs={},
        error=None,
        retry_count=0,
        max_retries=3,
    )
