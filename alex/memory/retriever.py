"""
Hybrid Retriever for Alex AI Assistant.

Implements combined vector + graph retrieval for optimal context gathering.
"""

from datetime import date, timedelta
from typing import Any

import structlog

from alex.config import settings
from alex.memory.graph_store import GraphStore
from alex.cortex.flash import generate_embedding

logger = structlog.get_logger()


class HybridRetriever:
    """
    Hybrid retrieval combining semantic search and graph traversal.

    Retrieval strategies:
    1. Temporal: Get context based on time (today, this week, etc.)
    2. Semantic: Vector similarity search on embeddings
    3. Graph: Traverse relationships to find connected context
    4. Hybrid: Combine all strategies for best results
    """

    def __init__(self):
        self.graph_store = GraphStore()

    async def get_daily_context(self, date_str: str) -> dict[str, Any]:
        """
        Get context for a specific day.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Dictionary with daily context
        """
        # Get daily summary
        daily_summary = await self.graph_store.get_daily_summary(date_str)

        # Get recent interactions if no summary exists
        interactions = []
        if not daily_summary:
            interactions = await self.graph_store.get_interactions_for_date(date_str)

        # Get this week's summary
        d = date.fromisoformat(date_str)
        week_id = f"{d.year}-W{d.isocalendar()[1]:02d}"
        weekly_summary = await self.graph_store.get_weekly_summary(week_id)

        return {
            "daily_summary": daily_summary.get("content") if daily_summary else None,
            "weekly_summary": weekly_summary.get("content") if weekly_summary else None,
            "recent_interactions": interactions[:5],  # Last 5 interactions
            "date": date_str,
            "week_id": week_id,
        }

    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Perform semantic search using vector similarity.

        Args:
            query: Search query
            top_k: Number of results to return
            min_score: Minimum similarity score threshold

        Returns:
            List of matching interactions
        """
        try:
            # Generate embedding for query
            query_embedding = await generate_embedding(query)

            # Search in Neo4j vector index
            search_query = """
            CALL db.index.vector.queryNodes('vector_index_interaction', $top_k, $embedding)
            YIELD node AS interaction, score
            WHERE score >= $min_score
            MATCH (interaction)-[:OCCURRED_ON]->(d:Day)
            RETURN interaction.id AS id,
                   interaction.user_message AS user_message,
                   interaction.assistant_response AS assistant_response,
                   d.date AS date,
                   score
            ORDER BY score DESC
            """

            async with self.graph_store.session() as session:
                result = await session.run(
                    search_query,
                    embedding=query_embedding,
                    top_k=top_k,
                    min_score=min_score,
                )
                records = await result.data()

                logger.info(
                    "Semantic search completed",
                    query_length=len(query),
                    results_count=len(records),
                )

                return records

        except Exception as e:
            logger.error("Semantic search failed", error=str(e))
            return []

    async def get_related_concepts(self, topics: list[str]) -> list[str]:
        """
        Get concepts related to the given topics.

        Args:
            topics: List of topic names

        Returns:
            List of related concept names
        """
        try:
            results = await self.graph_store.get_related_concepts(topics)
            related = set()
            for r in results:
                related.update(r.get("related_concepts", []))
            return list(related)[:10]  # Limit to 10

        except Exception as e:
            logger.error("Related concepts lookup failed", error=str(e))
            return []

    async def get_related_projects(self, entities: list[str]) -> list[str]:
        """
        Get projects related to the given entities.

        Args:
            entities: List of entity names

        Returns:
            List of related project names
        """
        try:
            query = """
            UNWIND $entities AS entity_name
            MATCH (p:Project)
            WHERE p.name CONTAINS entity_name OR p.description CONTAINS entity_name
            RETURN DISTINCT p.name AS name
            LIMIT 5
            """

            async with self.graph_store.session() as session:
                result = await session.run(query, entities=entities)
                records = await result.data()
                return [r["name"] for r in records]

        except Exception as e:
            logger.error("Related projects lookup failed", error=str(e))
            return []

    async def adaptive_retrieve(
        self,
        query: str,
        query_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Adaptively retrieve context based on query characteristics.

        Automatically selects the appropriate summary level based on
        how far back the query date is from today.

        Args:
            query: The user query
            query_date: Optional date the query is about

        Returns:
            Retrieved context dictionary
        """
        today = date.today()
        target_date = date.fromisoformat(query_date) if query_date else today
        days_ago = (today - target_date).days

        # Determine appropriate level
        if days_ago <= 1:
            level = "interactions"
            content = await self.graph_store.get_interactions_for_date(
                target_date.isoformat()
            )
        elif days_ago <= 7:
            level = "daily"
            content = await self.graph_store.get_daily_summary(
                target_date.isoformat()
            )
        elif days_ago <= 30:
            level = "weekly"
            week_id = f"{target_date.year}-W{target_date.isocalendar()[1]:02d}"
            content = await self.graph_store.get_weekly_summary(week_id)
        else:
            level = "monthly"
            # TODO: Implement monthly summary retrieval
            content = None

        return {
            "level": level,
            "days_ago": days_ago,
            "content": content,
            "target_date": target_date.isoformat(),
        }

    async def hybrid_search(
        self,
        query: str,
        include_temporal: bool = True,
        include_semantic: bool = True,
        include_graph: bool = True,
    ) -> dict[str, Any]:
        """
        Perform a full hybrid search combining all strategies.

        Args:
            query: Search query
            include_temporal: Include temporal context
            include_semantic: Include semantic search results
            include_graph: Include graph traversal results

        Returns:
            Combined context dictionary
        """
        context = {
            "temporal": None,
            "semantic": [],
            "concepts": [],
            "projects": [],
        }

        # Temporal context (today)
        if include_temporal:
            context["temporal"] = await self.get_daily_context(
                date.today().isoformat()
            )

        # Semantic search
        if include_semantic and len(query) > 10:
            context["semantic"] = await self.semantic_search(query)

        # Extract topics from semantic results for graph expansion
        if include_graph and context["semantic"]:
            # Get topics from query (simple extraction)
            words = query.lower().split()
            topics = [w for w in words if len(w) > 4][:5]

            if topics:
                context["concepts"] = await self.get_related_concepts(topics)
                context["projects"] = await self.get_related_projects(topics)

        return context
