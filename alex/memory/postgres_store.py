"""
PostgreSQL Store for Alex AI Assistant.

Handles all CRUD operations against PostgreSQL with pgvector.
Replaces Neo4j GraphStore with equivalent functionality.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

import structlog
import asyncpg

from alex.config import settings

logger = structlog.get_logger()


class PostgresStore:
    """
    PostgreSQL store for Alex's memory system.

    Provides methods for storing and retrieving:
    - Interactions
    - Summaries (daily, weekly, monthly)
    - Concepts and entities
    - Code changes
    - Time tree navigation

    Uses asyncpg for async database operations and pgvector for embeddings.
    """

    _pool: asyncpg.Pool | None = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """Get or create the connection pool."""
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(
                settings.postgres_uri,
                min_size=settings.postgres_pool_min,
                max_size=settings.postgres_pool_max,
                command_timeout=60,
            )
            logger.info("PostgreSQL pool created", uri=settings.postgres_uri.split("@")[-1])
        return cls._pool

    @classmethod
    async def close(cls):
        """Close the connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("PostgreSQL pool closed")

    @asynccontextmanager
    async def connection(self):
        """Get a connection from the pool."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            yield conn

    async def ensure_user(self, user_id: str) -> str:
        """Ensure a user exists in the database."""
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO users (id)
                VALUES ($1)
                ON CONFLICT (id) DO NOTHING
                """,
                user_id,
            )
        return user_id

    async def ensure_time_tree(self, date_str: str):
        """
        Ensure time tree entry exists for a given date.

        Args:
            date_str: Date in YYYY-MM-DD format
        """
        d = date.fromisoformat(date_str)
        iso_cal = d.isocalendar()

        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO days (date, year, month, day, week_number, day_of_week)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (date) DO NOTHING
                """,
                d,
                d.year,
                d.month,
                d.day,
                iso_cal.week,
                iso_cal.weekday,
            )

    async def store_interaction(
        self,
        interaction_id: str,
        user_id: str,
        user_message: str,
        assistant_response: str,
        intent: str | None = None,
        complexity_score: float = 0.0,
        model_used: str | None = None,
        topics: list[str] | None = None,
        entities: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """
        Store an interaction in the database.

        Args:
            interaction_id: Unique identifier for the interaction
            user_id: User identifier
            user_message: The user's message
            assistant_response: Alex's response
            intent: Classified intent
            complexity_score: Complexity score (0-1)
            model_used: Model used for response
            topics: Extracted topics
            entities: Extracted entities (unused, kept for API compatibility)
            embedding: Optional embedding vector (768 dimensions)

        Returns:
            The interaction ID
        """
        today = date.today()
        today_str = today.isoformat()

        # Ensure time tree and user exist
        await self.ensure_time_tree(today_str)
        await self.ensure_user(user_id)

        # Convert embedding to pgvector format if provided
        embedding_str = None
        if embedding:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        async with self.connection() as conn:
            # Insert interaction
            await conn.execute(
                """
                INSERT INTO interactions (
                    id, user_id, date, timestamp, user_message, assistant_response,
                    intent, complexity_score, model_used, embedding
                )
                VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9::vector)
                ON CONFLICT (id) DO UPDATE SET
                    assistant_response = EXCLUDED.assistant_response,
                    intent = EXCLUDED.intent,
                    complexity_score = EXCLUDED.complexity_score,
                    model_used = EXCLUDED.model_used,
                    embedding = EXCLUDED.embedding
                """,
                interaction_id,
                user_id,
                today,
                user_message,
                assistant_response,
                intent,
                complexity_score,
                model_used,
                embedding_str,
            )

            # Link to topics/concepts
            if topics:
                await self._link_to_concepts(conn, interaction_id, topics)

        logger.info(
            "Interaction stored",
            interaction_id=interaction_id,
            date=today_str,
        )

        return interaction_id

    async def _link_to_concepts(
        self,
        conn: asyncpg.Connection,
        interaction_id: str,
        topics: list[str],
    ):
        """Link an interaction to concept records."""
        for topic in topics:
            normalized = topic.lower().replace(" ", "_")

            # Upsert concept
            concept_id = await conn.fetchval(
                """
                INSERT INTO concepts (name, normalized_name, mention_count)
                VALUES ($1, $2, 1)
                ON CONFLICT (name) DO UPDATE SET
                    mention_count = concepts.mention_count + 1
                RETURNING id
                """,
                topic,
                normalized,
            )

            # Link interaction to concept
            await conn.execute(
                """
                INSERT INTO interaction_concepts (interaction_id, concept_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                interaction_id,
                concept_id,
            )

    async def get_interactions_for_date(self, date_str: str) -> list[dict[str, Any]]:
        """
        Get all interactions for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of interaction dictionaries
        """
        d = date.fromisoformat(date_str)

        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_message, assistant_response, intent, timestamp
                FROM interactions
                WHERE date = $1
                ORDER BY timestamp
                """,
                d,
            )

            return [dict(row) for row in rows]

    async def get_daily_summary(self, date_str: str) -> dict[str, Any] | None:
        """
        Get the daily summary for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Summary dictionary or None
        """
        d = date.fromisoformat(date_str)

        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT content, key_topics, generated_at
                FROM daily_summaries
                WHERE date = $1
                """,
                d,
            )

            return dict(row) if row else None

    async def create_daily_summary(
        self,
        date_str: str,
        content: str,
        key_topics: list[str],
        interaction_count: int,
        model_used: str,
        embedding: list[float] | None = None,
    ) -> str:
        """
        Create or update a daily summary.

        Args:
            date_str: Date in YYYY-MM-DD format
            content: Summary content
            key_topics: List of key topics
            interaction_count: Number of interactions summarized
            model_used: Model used for summarization
            embedding: Optional embedding vector

        Returns:
            The date string
        """
        d = date.fromisoformat(date_str)

        # Ensure time tree exists
        await self.ensure_time_tree(date_str)

        # Convert embedding to pgvector format if provided
        embedding_str = None
        if embedding:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO daily_summaries (
                    date, content, key_topics, interaction_count, model_used, embedding
                )
                VALUES ($1, $2, $3, $4, $5, $6::vector)
                ON CONFLICT (date) DO UPDATE SET
                    content = EXCLUDED.content,
                    key_topics = EXCLUDED.key_topics,
                    interaction_count = EXCLUDED.interaction_count,
                    model_used = EXCLUDED.model_used,
                    embedding = EXCLUDED.embedding,
                    generated_at = NOW()
                """,
                d,
                content,
                key_topics,
                interaction_count,
                model_used,
                embedding_str,
            )

        return date_str

    async def get_weekly_summary(self, week_id: str) -> dict[str, Any] | None:
        """
        Get the weekly summary for a specific week.

        Args:
            week_id: Week ID in YYYY-Wxx format

        Returns:
            Summary dictionary or None
        """
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT content, key_themes, generated_at
                FROM weekly_summaries
                WHERE week_id = $1
                """,
                week_id,
            )

            return dict(row) if row else None

    async def get_daily_summaries_for_week(self, week_id: str) -> list[dict[str, Any]]:
        """
        Get all daily summaries for a specific week.

        Args:
            week_id: Week ID in YYYY-Wxx format (e.g., "2026-W04")

        Returns:
            List of daily summary dictionaries
        """
        # Parse week_id
        parts = week_id.split("-W")
        year = int(parts[0])
        week = int(parts[1])

        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    ds.date::text AS date,
                    ds.content,
                    ds.key_topics,
                    ds.interaction_count
                FROM daily_summaries ds
                JOIN days d ON ds.date = d.date
                WHERE d.year = $1 AND d.week_number = $2
                ORDER BY ds.date
                """,
                year,
                week,
            )

            return [dict(row) for row in rows]

    async def create_weekly_summary(
        self,
        week_id: str,
        content: str,
        key_themes: list[str],
        daily_summary_count: int,
        total_interactions: int,
        model_used: str,
        embedding: list[float] | None = None,
    ) -> str:
        """
        Create or update a weekly summary.

        Args:
            week_id: Week ID in YYYY-Wxx format
            content: Summary content
            key_themes: List of key themes
            daily_summary_count: Number of daily summaries aggregated
            total_interactions: Total interactions across the week
            model_used: Model used for summarization
            embedding: Optional embedding vector

        Returns:
            The week ID
        """
        # Parse week_id
        parts = week_id.split("-W")
        year = int(parts[0])
        week = int(parts[1])

        # Convert embedding to pgvector format if provided
        embedding_str = None
        if embedding:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO weekly_summaries (
                    week_id, year, week, content, key_themes,
                    daily_summary_count, total_interactions, model_used, embedding
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector)
                ON CONFLICT (week_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    key_themes = EXCLUDED.key_themes,
                    daily_summary_count = EXCLUDED.daily_summary_count,
                    total_interactions = EXCLUDED.total_interactions,
                    model_used = EXCLUDED.model_used,
                    embedding = EXCLUDED.embedding,
                    generated_at = NOW()
                """,
                week_id,
                year,
                week,
                content,
                key_themes,
                daily_summary_count,
                total_interactions,
                model_used,
                embedding_str,
            )

        return week_id

    async def get_unsummarized_days(self, limit: int = 30) -> list[str]:
        """
        Get dates that have interactions but no daily summary.

        Args:
            limit: Maximum number of days to return

        Returns:
            List of date strings (YYYY-MM-DD format)
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT d.date::text AS date
                FROM days d
                JOIN interactions i ON d.date = i.date
                LEFT JOIN daily_summaries ds ON d.date = ds.date
                WHERE ds.date IS NULL
                GROUP BY d.date
                HAVING COUNT(i.id) > 0
                ORDER BY d.date DESC
                LIMIT $1
                """,
                limit,
            )

            return [row["date"] for row in rows]

    async def get_unsummarized_weeks(self, limit: int = 10) -> list[str]:
        """
        Get weeks that have daily summaries but no weekly summary.

        Args:
            limit: Maximum number of weeks to return

        Returns:
            List of week IDs (YYYY-Wxx format)
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    d.year || '-W' || LPAD(d.week_number::text, 2, '0') AS week_id,
                    COUNT(ds.date) AS summary_count
                FROM days d
                JOIN daily_summaries ds ON d.date = ds.date
                LEFT JOIN weekly_summaries ws ON
                    ws.year = d.year AND ws.week = d.week_number
                WHERE ws.week_id IS NULL
                GROUP BY d.year, d.week_number
                HAVING COUNT(ds.date) >= 1
                ORDER BY d.year DESC, d.week_number DESC
                LIMIT $1
                """,
                limit,
            )

            return [row["week_id"] for row in rows]

    async def get_weekly_summaries_for_month(self, month_id: str) -> list[dict[str, Any]]:
        """
        Get all weekly summaries for a specific month.

        Args:
            month_id: Month ID in YYYY-M format (e.g., "2026-1")

        Returns:
            List of weekly summary dictionaries
        """
        # Parse month_id
        parts = month_id.split("-")
        year = int(parts[0])
        month = int(parts[1])

        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (ws.week_id)
                    ws.week_id,
                    ws.content,
                    ws.key_themes,
                    ws.total_interactions
                FROM weekly_summaries ws
                JOIN days d ON ws.year = d.year AND ws.week = d.week_number
                WHERE d.year = $1 AND d.month = $2
                ORDER BY ws.week_id
                """,
                year,
                month,
            )

            return [dict(row) for row in rows]

    async def get_unsummarized_months(self, limit: int = 6) -> list[str]:
        """
        Get months that have weekly summaries but no monthly summary.

        Args:
            limit: Maximum number of months to return

        Returns:
            List of month IDs (YYYY-M format)
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    d.year || '-' || d.month AS month_id,
                    COUNT(DISTINCT ws.week_id) AS summary_count
                FROM days d
                JOIN weekly_summaries ws ON ws.year = d.year AND ws.week = d.week_number
                LEFT JOIN monthly_summaries ms ON
                    ms.year = d.year AND ms.month = d.month
                WHERE ms.month_id IS NULL
                GROUP BY d.year, d.month
                HAVING COUNT(DISTINCT ws.week_id) >= 1
                ORDER BY d.year DESC, d.month DESC
                LIMIT $1
                """,
                limit,
            )

            return [row["month_id"] for row in rows]

    async def create_monthly_summary(
        self,
        month_id: str,
        content: str,
        key_themes: list[str],
        weekly_summary_count: int,
        total_interactions: int,
        model_used: str,
        embedding: list[float] | None = None,
    ) -> str:
        """
        Create or update a monthly summary.

        Args:
            month_id: Month ID in YYYY-M format
            content: Summary content
            key_themes: List of key themes
            weekly_summary_count: Number of weekly summaries aggregated
            total_interactions: Total interactions across the month
            model_used: Model used for summarization
            embedding: Optional embedding vector

        Returns:
            The month ID
        """
        # Parse month_id
        parts = month_id.split("-")
        year = int(parts[0])
        month = int(parts[1])

        # Convert embedding to pgvector format if provided
        embedding_str = None
        if embedding:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO monthly_summaries (
                    month_id, year, month, content, key_themes,
                    weekly_summary_count, total_interactions, model_used, embedding
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector)
                ON CONFLICT (month_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    key_themes = EXCLUDED.key_themes,
                    weekly_summary_count = EXCLUDED.weekly_summary_count,
                    total_interactions = EXCLUDED.total_interactions,
                    model_used = EXCLUDED.model_used,
                    embedding = EXCLUDED.embedding,
                    generated_at = NOW()
                """,
                month_id,
                year,
                month,
                content,
                key_themes,
                weekly_summary_count,
                total_interactions,
                model_used,
                embedding_str,
            )

        return month_id

    async def get_related_concepts(self, concept_names: list[str]) -> list[dict[str, Any]]:
        """
        Get concepts related to the given concept names.

        Note: PostgreSQL doesn't have native graph traversal, so we find concepts
        that co-occur in the same interactions.

        Args:
            concept_names: List of concept names to find relations for

        Returns:
            List of related concept dictionaries
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    c1.name AS concept,
                    array_agg(DISTINCT c2.name) FILTER (WHERE c2.name IS NOT NULL AND c2.name != c1.name) AS related_concepts,
                    c1.mention_count AS mentions
                FROM concepts c1
                LEFT JOIN interaction_concepts ic1 ON c1.id = ic1.concept_id
                LEFT JOIN interaction_concepts ic2 ON ic1.interaction_id = ic2.interaction_id
                LEFT JOIN concepts c2 ON ic2.concept_id = c2.id
                WHERE c1.name = ANY($1)
                GROUP BY c1.id, c1.name, c1.mention_count
                """,
                concept_names,
            )

            return [dict(row) for row in rows]

    async def store_code_change(
        self,
        change_id: str,
        user_id: str,
        files_modified: list[str],
        description: str,
        reasoning: str,
        change_type: str,
        commit_sha: str | None = None,
        related_interaction_id: str | None = None,
    ) -> str:
        """
        Store a code change in the database.

        This tracks Alex's self-modifications for memory and recall.

        Args:
            change_id: Unique identifier for the change
            user_id: User who requested the change
            files_modified: List of file paths that were modified
            description: What was changed
            reasoning: Why the change was made
            change_type: Type of change (feature, bugfix, refactor, etc.)
            commit_sha: Git commit SHA if committed
            related_interaction_id: ID of the interaction that triggered this

        Returns:
            The change ID
        """
        today = date.today()
        today_str = today.isoformat()

        # Ensure time tree and user exist
        await self.ensure_time_tree(today_str)
        await self.ensure_user(user_id)

        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO code_changes (
                    id, user_id, date, timestamp, files_modified, description,
                    reasoning, change_type, commit_sha, related_interaction_id
                )
                VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9)
                ON CONFLICT (id) DO UPDATE SET
                    files_modified = EXCLUDED.files_modified,
                    description = EXCLUDED.description,
                    reasoning = EXCLUDED.reasoning,
                    change_type = EXCLUDED.change_type,
                    commit_sha = EXCLUDED.commit_sha
                """,
                change_id,
                user_id,
                today,
                files_modified,
                description,
                reasoning,
                change_type,
                commit_sha,
                related_interaction_id,
            )

            # Extract and link concepts from files modified
            concepts = self._extract_concepts_from_files(files_modified)
            if concepts:
                await self._link_change_to_concepts(conn, change_id, concepts)

        logger.info(
            "Code change stored",
            change_id=change_id,
            files=files_modified,
            change_type=change_type,
        )

        return change_id

    def _extract_concepts_from_files(self, files: list[str]) -> list[str]:
        """Extract concept names from file paths."""
        concepts = set()
        for f in files:
            # Extract module names
            parts = f.replace("/", ".").replace(".py", "").split(".")
            for part in parts:
                if part and part not in ("alex", "tests", "__init__"):
                    concepts.add(part)
        return list(concepts)

    async def _link_change_to_concepts(
        self,
        conn: asyncpg.Connection,
        change_id: str,
        concepts: list[str],
    ):
        """Link a code change to concept records."""
        for concept in concepts:
            normalized = concept.lower().replace(" ", "_")

            # Upsert concept
            concept_id = await conn.fetchval(
                """
                INSERT INTO concepts (name, normalized_name, mention_count)
                VALUES ($1, $2, 1)
                ON CONFLICT (name) DO UPDATE SET
                    mention_count = concepts.mention_count + 1
                RETURNING id
                """,
                concept,
                normalized,
            )

            # Link code change to concept
            await conn.execute(
                """
                INSERT INTO code_change_concepts (change_id, concept_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                change_id,
                concept_id,
            )

    async def get_recent_code_changes(
        self,
        limit: int = 10,
        change_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get recent code changes.

        Args:
            limit: Maximum number of changes to return
            change_type: Optional filter by change type

        Returns:
            List of code change dictionaries
        """
        async with self.connection() as conn:
            if change_type:
                rows = await conn.fetch(
                    """
                    SELECT id, description, reasoning, files_modified,
                           change_type, commit_sha, timestamp::text
                    FROM code_changes
                    WHERE change_type = $1
                    ORDER BY timestamp DESC
                    LIMIT $2
                    """,
                    change_type,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, description, reasoning, files_modified,
                           change_type, commit_sha, timestamp::text
                    FROM code_changes
                    ORDER BY timestamp DESC
                    LIMIT $1
                    """,
                    limit,
                )

            return [dict(row) for row in rows]

    async def get_code_changes_for_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        Get all code changes that modified a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of code change dictionaries
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, description, reasoning, change_type,
                       commit_sha, timestamp::text
                FROM code_changes
                WHERE $1 = ANY(files_modified)
                ORDER BY timestamp DESC
                """,
                file_path,
            )

            return [dict(row) for row in rows]

    async def semantic_search(
        self,
        embedding: list[float],
        top_k: int = 5,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Perform semantic search using vector similarity.

        Args:
            embedding: Query embedding vector (768 dimensions)
            top_k: Number of results to return
            min_score: Minimum similarity score threshold (0-1)

        Returns:
            List of matching interactions with scores
        """
        # Convert embedding to pgvector format
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    i.id,
                    i.user_message,
                    i.assistant_response,
                    i.date::text AS date,
                    1 - (i.embedding <=> $1::vector) AS score
                FROM interactions i
                WHERE i.embedding IS NOT NULL
                ORDER BY i.embedding <=> $1::vector
                LIMIT $2
                """,
                embedding_str,
                top_k * 2,  # Fetch more to filter by min_score
            )

            # Filter by min_score and limit to top_k
            results = []
            for row in rows:
                if row["score"] >= min_score:
                    results.append(dict(row))
                    if len(results) >= top_k:
                        break

            return results

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the PostgreSQL connection.

        Returns:
            Health status dictionary
        """
        try:
            async with self.connection() as conn:
                # Get table counts
                counts = {}
                for table in ["users", "interactions", "concepts", "daily_summaries",
                              "weekly_summaries", "monthly_summaries", "code_changes"]:
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    counts[table] = count

                # Check pgvector extension
                pgvector_version = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )

                return {
                    "status": "healthy",
                    "table_counts": counts,
                    "pgvector_version": pgvector_version,
                }

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
            }


# Backward compatibility alias
GraphStore = PostgresStore
