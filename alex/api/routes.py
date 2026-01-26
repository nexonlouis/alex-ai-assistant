"""
API routes for Alex AI Assistant.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alex.agents.graph import invoke_alex
from alex.memory.graph_store import GraphStore

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, max_length=10000)
    user_id: str = Field(default="primary_user")
    session_id: str | None = Field(default=None)
    conversation_history: list[dict[str, str]] | None = Field(default=None)


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str
    session_id: str
    metadata: dict[str, Any]


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    version: str
    neo4j: dict[str, Any]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat with Alex AI Assistant.

    Sends a message to Alex and receives a response. The conversation
    can be continued by providing the session_id from a previous response.
    """
    try:
        result = await invoke_alex(
            user_message=request.message,
            user_id=request.user_id,
            session_id=request.session_id,
            conversation_history=request.conversation_history,
        )

        return ChatResponse(
            response=result["response"] or "I'm sorry, I couldn't generate a response.",
            session_id=result["session_id"],
            metadata=result["metadata"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns the status of Alex and its dependencies.
    """
    from alex import __version__

    graph_store = GraphStore()
    neo4j_health = await graph_store.health_check()

    return HealthResponse(
        status="healthy" if neo4j_health["status"] == "healthy" else "degraded",
        version=__version__,
        neo4j=neo4j_health,
    )


@router.get("/memory/today")
async def get_today_context() -> dict[str, Any]:
    """
    Get today's memory context.

    Returns the daily summary and recent interactions.
    """
    from datetime import date
    from alex.memory.retriever import HybridRetriever

    retriever = HybridRetriever()
    context = await retriever.get_daily_context(date.today().isoformat())

    # Convert Neo4j DateTime objects to strings for JSON serialization
    if context.get("recent_interactions"):
        for interaction in context["recent_interactions"]:
            if interaction.get("timestamp"):
                interaction["timestamp"] = str(interaction["timestamp"])

    return context


@router.post("/tasks/summarize_daily")
async def trigger_daily_summary() -> dict[str, Any]:
    """
    Trigger daily summarization task.

    Called by Cloud Scheduler to generate daily summaries.
    Summarizes all days that have interactions but no summary yet.
    """
    from alex.memory.summarizer import run_daily_summarization

    try:
        results = await run_daily_summarization(max_days=7)
        return {
            "status": "completed",
            "processed": results["processed"],
            "completed": results["completed"],
            "skipped": results["skipped"],
            "errors": results["errors"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/summarize_weekly")
async def trigger_weekly_summary() -> dict[str, Any]:
    """
    Trigger weekly summarization task.

    Called by Cloud Scheduler to generate weekly summaries.
    Aggregates daily summaries into weekly themes.
    """
    from alex.memory.summarizer import run_weekly_summarization

    try:
        results = await run_weekly_summarization(max_weeks=4)
        return {
            "status": "completed",
            "processed": results["processed"],
            "completed": results["completed"],
            "skipped": results["skipped"],
            "errors": results["errors"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/summarize_monthly")
async def trigger_monthly_summary() -> dict[str, Any]:
    """
    Trigger monthly summarization task.

    Called by Cloud Scheduler to generate monthly summaries.
    Aggregates weekly summaries into monthly insights.
    """
    from alex.memory.summarizer import run_monthly_summarization

    try:
        results = await run_monthly_summarization(max_months=2)
        return {
            "status": "completed",
            "processed": results["processed"],
            "completed": results["completed"],
            "skipped": results["skipped"],
            "errors": results["errors"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/summarize_all")
async def trigger_full_summarization() -> dict[str, Any]:
    """
    Trigger full summarization pipeline.

    Runs daily → weekly → monthly summarization in sequence.
    This is the main endpoint for comprehensive memory consolidation.
    """
    from alex.memory.summarizer import run_full_summarization_pipeline

    try:
        results = await run_full_summarization_pipeline()
        return {
            "status": "completed",
            "daily": results["daily"],
            "weekly": results["weekly"],
            "monthly": results["monthly"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/interactions")
async def get_interactions(date: str | None = None, limit: int = 10) -> dict[str, Any]:
    """
    Debug endpoint to query stored interactions.

    Args:
        date: Optional date filter (YYYY-MM-DD format). Defaults to today.
        limit: Maximum number of interactions to return.
    """
    from datetime import date as date_type

    graph_store = GraphStore()
    target_date = date or date_type.today().isoformat()

    # Get interactions for the date
    interactions = await graph_store.get_interactions_for_date(target_date)

    # Convert Neo4j DateTime to string for serialization
    for interaction in interactions:
        if interaction.get("timestamp"):
            interaction["timestamp"] = str(interaction["timestamp"])

    # Also get total count and all interactions summary
    async with graph_store.session() as session:
        result = await session.run("MATCH (i:Interaction) RETURN count(i) as total")
        record = await result.single()
        total_count = record["total"] if record else 0

        # Get all interactions if date filter returns none
        all_result = await session.run("""
            MATCH (i:Interaction)
            RETURN i.id AS id,
                   i.user_message AS user_message,
                   i.intent AS intent,
                   toString(i.timestamp) AS timestamp
            ORDER BY i.timestamp DESC
            LIMIT $limit
        """, limit=limit)
        all_interactions = await all_result.data()

        # Check Day node linking
        day_result = await session.run("""
            MATCH (i:Interaction)-[:OCCURRED_ON]->(d:Day)
            RETURN d.date AS day, count(i) AS interaction_count
            ORDER BY d.date DESC
            LIMIT 5
        """)
        day_links = await day_result.data()

        # Check User linking
        user_result = await session.run("""
            MATCH (u:User)-[:HAD_INTERACTION]->(i:Interaction)
            RETURN u.id AS user_id, count(i) AS interaction_count
        """)
        user_links = await user_result.data()

        # Check Concept linking
        concept_result = await session.run("""
            MATCH (i:Interaction)-[:MENTIONS_CONCEPT]->(c:Concept)
            RETURN c.name AS concept, c.mention_count AS mentions, count(i) AS linked_interactions
            ORDER BY c.mention_count DESC
            LIMIT 10
        """)
        concept_links = await concept_result.data()

    return {
        "date": target_date,
        "interactions_for_date": interactions[:limit],
        "count_for_date": len(interactions),
        "total_interactions": total_count,
        "recent_interactions": all_interactions,
        "day_node_links": day_links,
        "user_links": user_links,
        "concept_links": concept_links,
    }


@router.get("/debug/semantic-search")
async def test_semantic_search(query: str, top_k: int = 5) -> dict[str, Any]:
    """
    Debug endpoint to test semantic search.
    """
    from alex.memory.retriever import HybridRetriever

    retriever = HybridRetriever()
    results = await retriever.semantic_search(query=query, top_k=top_k, min_score=0.5)

    return {
        "query": query,
        "results_count": len(results),
        "results": results,
    }


@router.get("/debug/summaries")
async def get_summaries() -> dict[str, Any]:
    """
    Debug endpoint to view all generated summaries.
    """
    graph_store = GraphStore()

    async with graph_store.session() as session:
        # Get daily summaries
        daily_result = await session.run("""
            MATCH (ds:DailySummary)
            RETURN ds.date AS date,
                   ds.content AS content,
                   ds.key_topics AS key_topics,
                   ds.interaction_count AS interaction_count,
                   toString(ds.generated_at) AS generated_at
            ORDER BY ds.date DESC
            LIMIT 10
        """)
        daily_summaries = await daily_result.data()

        # Get weekly summaries
        weekly_result = await session.run("""
            MATCH (ws:WeeklySummary)
            RETURN ws.week_id AS week_id,
                   ws.content AS content,
                   ws.key_themes AS key_themes,
                   ws.daily_summary_count AS daily_count,
                   ws.total_interactions AS total_interactions,
                   toString(ws.generated_at) AS generated_at
            ORDER BY ws.week_id DESC
            LIMIT 5
        """)
        weekly_summaries = await weekly_result.data()

        # Get monthly summaries
        monthly_result = await session.run("""
            MATCH (ms:MonthlySummary)
            RETURN ms.month_id AS month_id,
                   ms.content AS content,
                   ms.key_themes AS key_themes,
                   ms.weekly_summary_count AS weekly_count,
                   ms.total_interactions AS total_interactions,
                   toString(ms.generated_at) AS generated_at
            ORDER BY ms.month_id DESC
            LIMIT 3
        """)
        monthly_summaries = await monthly_result.data()

    return {
        "daily_summaries": daily_summaries,
        "weekly_summaries": weekly_summaries,
        "monthly_summaries": monthly_summaries,
        "counts": {
            "daily": len(daily_summaries),
            "weekly": len(weekly_summaries),
            "monthly": len(monthly_summaries),
        },
    }


@router.get("/debug/unsummarized")
async def get_unsummarized() -> dict[str, Any]:
    """
    Debug endpoint to see what needs to be summarized.
    """
    graph_store = GraphStore()

    unsummarized_days = await graph_store.get_unsummarized_days(limit=30)
    unsummarized_weeks = await graph_store.get_unsummarized_weeks(limit=10)
    unsummarized_months = await graph_store.get_unsummarized_months(limit=6)

    return {
        "unsummarized_days": unsummarized_days,
        "unsummarized_weeks": unsummarized_weeks,
        "unsummarized_months": unsummarized_months,
        "counts": {
            "days": len(unsummarized_days),
            "weeks": len(unsummarized_weeks),
            "months": len(unsummarized_months),
        },
    }


@router.post("/admin/backfill-embeddings")
async def backfill_embeddings() -> dict[str, Any]:
    """
    Admin endpoint to backfill embeddings for existing interactions.
    """
    from alex.cortex.flash import generate_embedding

    graph_store = GraphStore()
    results = {"processed": 0, "success": 0, "errors": []}

    async with graph_store.session() as session:
        # Get interactions without embeddings
        result = await session.run("""
            MATCH (i:Interaction)
            WHERE i.embedding IS NULL
            RETURN i.id AS id, i.user_message AS user_message, i.assistant_response AS response
            LIMIT 100
        """)
        interactions = await result.data()

        for interaction in interactions:
            results["processed"] += 1
            try:
                # Generate embedding
                text = f"{interaction['user_message']}\n{interaction['response']}"
                embedding = await generate_embedding(text)

                # Update the node
                await session.run("""
                    MATCH (i:Interaction {id: $id})
                    SET i.embedding = $embedding
                """, id=interaction["id"], embedding=embedding)

                results["success"] += 1
            except Exception as e:
                results["errors"].append(f"{interaction['id']}: {str(e)}")

    return results


@router.post("/admin/update-vector-indexes")
async def update_vector_indexes() -> dict[str, Any]:
    """
    Admin endpoint to update vector indexes to 768 dimensions.
    """
    graph_store = GraphStore()

    results = {"dropped": [], "created": [], "errors": []}

    # Vector indexes to recreate
    indexes = [
        ("vector_index_interaction", "Interaction", "embedding"),
        ("vector_index_concept", "Concept", "embedding"),
        ("vector_index_project", "Project", "embedding"),
        ("vector_index_daily_summary", "DailySummary", "embedding"),
        ("vector_index_weekly_summary", "WeeklySummary", "embedding"),
    ]

    async with graph_store.session() as session:
        # Drop existing indexes
        for idx_name, _, _ in indexes:
            try:
                await session.run(f"DROP INDEX {idx_name} IF EXISTS")
                results["dropped"].append(idx_name)
            except Exception as e:
                results["errors"].append(f"Drop {idx_name}: {e}")

        # Create new indexes with 768 dimensions
        for idx_name, label, prop in indexes:
            query = f"""
            CREATE VECTOR INDEX {idx_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{prop})
            OPTIONS {{indexConfig: {{`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}}}
            """
            try:
                await session.run(query)
                results["created"].append(idx_name)
            except Exception as e:
                results["errors"].append(f"Create {idx_name}: {e}")

    return results
