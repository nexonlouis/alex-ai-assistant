"""
Memory nodes for Alex AI Assistant.

Handles retrieval from and storage to the PostgreSQL database with pgvector.
"""

from datetime import date
from typing import Any
from uuid import uuid4

import structlog

from alex.agents.state import AlexState, MemoryContext, get_last_user_message, get_last_assistant_message
from alex.memory.postgres_store import PostgresStore
from alex.memory.retriever import HybridRetriever
from alex.cortex.flash import generate_embedding

logger = structlog.get_logger()


async def retrieve_memory(state: AlexState) -> dict[str, Any]:
    """
    Retrieve relevant context from the knowledge graph.

    Uses hybrid retrieval (semantic + temporal + graph traversal) to find:
    - Recent interactions from today/this week
    - Semantically similar past conversations
    - Related concepts and projects
    """
    metadata = state.get("metadata")
    logger.info(
        "Retrieving memory context",
        session_id=state.get("session_id"),
        intent=metadata.intent if metadata else None,
    )

    try:
        retriever = HybridRetriever()

        user_message = get_last_user_message(state)
        topics = metadata.topics_extracted if metadata else []
        entities = metadata.entities_extracted if metadata else []

        # Get temporal context (today's summary, recent interactions)
        today = date.today().isoformat()
        daily_context = await retriever.get_daily_context(today)

        # Get semantic matches if we have a meaningful query
        relevant_interactions = []
        if user_message and len(user_message) > 10:
            relevant_interactions = await retriever.semantic_search(
                query=user_message,
                top_k=5,
                min_score=0.7,
            )

        # Get related concepts
        related_concepts = []
        if topics:
            related_concepts = await retriever.get_related_concepts(topics)

        # Get related projects
        related_projects = []
        if entities:
            related_projects = await retriever.get_related_projects(entities)

        memory_context = MemoryContext(
            daily_summary=daily_context.get("daily_summary"),
            weekly_summary=daily_context.get("weekly_summary"),
            relevant_interactions=relevant_interactions,
            related_concepts=related_concepts,
            related_projects=related_projects,
            retrieval_method="hybrid",
            retrieval_score=0.8 if relevant_interactions else 0.5,
        )

        logger.info(
            "Memory retrieved",
            has_daily_summary=bool(memory_context.daily_summary),
            relevant_count=len(relevant_interactions),
            concepts_count=len(related_concepts),
        )

        return {
            "memory_context": memory_context,
            "processing_stage": "retrieve_memory",
        }

    except Exception as e:
        logger.error("Memory retrieval failed", error=str(e))
        # Continue with empty context rather than failing
        return {
            "memory_context": MemoryContext(),
            "processing_stage": "retrieve_memory",
        }


async def store_interaction(state: AlexState) -> dict[str, Any]:
    """
    Store the completed interaction in the PostgreSQL database.

    Creates:
    - Interaction record with user message and assistant response
    - Links to the current day in the time tree
    - Links to extracted concepts and topics
    """
    metadata = state.get("metadata")
    logger.info(
        "Storing interaction",
        session_id=state.get("session_id"),
        interaction_id=metadata.interaction_id if metadata else None,
    )

    try:
        store = PostgresStore()

        user_message = get_last_user_message(state)
        assistant_message = get_last_assistant_message(state)

        if not user_message or not assistant_message:
            logger.warning("Missing message content, skipping storage")
            return {"processing_stage": "complete"}

        # Generate embedding for the interaction
        embedding_text = f"{user_message}\n{assistant_message}"
        try:
            embedding = await generate_embedding(embedding_text)
            logger.info("Generated embedding", dimensions=len(embedding))
        except Exception as e:
            logger.warning("Failed to generate embedding", error=str(e))
            embedding = None

        # Store the interaction
        interaction_id = await store.store_interaction(
            interaction_id=metadata.interaction_id if metadata else None,
            user_id=state.get("user_id"),
            user_message=user_message,
            assistant_response=assistant_message,
            intent=metadata.intent if metadata else None,
            complexity_score=metadata.complexity_score if metadata else 0.0,
            model_used=metadata.model_used if metadata else None,
            topics=metadata.topics_extracted if metadata else [],
            entities=metadata.entities_extracted if metadata else [],
            embedding=embedding,
        )

        logger.info("Interaction stored", interaction_id=interaction_id)

        return {"processing_stage": "complete"}

    except Exception as e:
        logger.error("Failed to store interaction", error=str(e))
        # Don't fail the whole interaction if storage fails
        return {"processing_stage": "complete"}
