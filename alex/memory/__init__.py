"""
Memory module for Alex AI Assistant.

Implements the memory system using PostgreSQL with pgvector.
Provides semantic search, temporal summaries, and concept tracking.
"""

from alex.memory.postgres_store import PostgresStore
from alex.memory.retriever import HybridRetriever
from alex.memory.summarizer import (
    summarize_day,
    summarize_week,
    summarize_month,
    run_daily_summarization,
    run_weekly_summarization,
    run_monthly_summarization,
    run_full_summarization_pipeline,
)

# Backward compatibility alias
GraphStore = PostgresStore

__all__ = [
    "PostgresStore",
    "GraphStore",  # Alias for backward compatibility
    "HybridRetriever",
    "summarize_day",
    "summarize_week",
    "summarize_month",
    "run_daily_summarization",
    "run_weekly_summarization",
    "run_monthly_summarization",
    "run_full_summarization_pipeline",
]
