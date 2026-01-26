"""Tests for agent state module."""

import pytest
from alex.agents.state import AlexState, MemoryContext, InteractionMetadata


def test_alex_state_defaults():
    """Test AlexState default values."""
    state = AlexState()

    assert state.user_id == "primary_user"
    assert state.current_cortex == "flash"
    assert state.processing_stage == "intake"
    assert state.error is None
    assert state.retry_count == 0


def test_alex_state_get_last_user_message():
    """Test getting last user message."""
    state = AlexState(
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"},
        ]
    )

    assert state.get_last_user_message() == "How are you?"


def test_alex_state_get_last_assistant_message():
    """Test getting last assistant message."""
    state = AlexState(
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"},
        ]
    )

    assert state.get_last_assistant_message() == "Hi there"


def test_alex_state_should_escalate():
    """Test escalation logic."""
    state = AlexState()
    state.metadata.complexity_score = 0.5
    assert state.should_escalate_to_pro() is False

    state.metadata.complexity_score = 0.8
    assert state.should_escalate_to_pro() is True


def test_alex_state_is_engineering_task():
    """Test engineering task detection."""
    state = AlexState()

    state.metadata.intent = "chat"
    assert state.is_engineering_task() is False

    state.metadata.intent = "code_change"
    assert state.is_engineering_task() is True

    state.metadata.intent = "refactor"
    assert state.is_engineering_task() is True


def test_memory_context_defaults():
    """Test MemoryContext default values."""
    ctx = MemoryContext()

    assert ctx.daily_summary is None
    assert ctx.relevant_interactions == []
    assert ctx.retrieval_method == "hybrid"


def test_interaction_metadata_defaults():
    """Test InteractionMetadata default values."""
    meta = InteractionMetadata()

    assert meta.interaction_id is not None
    assert meta.timestamp is not None
    assert meta.complexity_score == 0.0
    assert meta.topics_extracted == []
