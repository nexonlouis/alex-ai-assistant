"""
Neo4j Graph Store for Alex AI Assistant.

Handles all CRUD operations against the Temporal Knowledge Graph.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any
from uuid import uuid4

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver

from alex.config import settings

logger = structlog.get_logger()


class GraphStore:
    """
    Neo4j graph store for Alex's memory system.

    Provides methods for storing and retrieving:
    - Interactions
    - Summaries
    - Concepts and entities
    - Time tree navigation
    """

    _driver: AsyncDriver | None = None

    @classmethod
    async def get_driver(cls) -> AsyncDriver:
        """Get or create the Neo4j driver."""
        if cls._driver is None:
            cls._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
            )
            # Verify connectivity
            await cls._driver.verify_connectivity()
            logger.info("Neo4j driver connected", uri=settings.neo4j_uri)
        return cls._driver

    @classmethod
    async def close(cls):
        """Close the Neo4j driver."""
        if cls._driver:
            await cls._driver.close()
            cls._driver = None
            logger.info("Neo4j driver closed")

    @asynccontextmanager
    async def session(self):
        """Get a Neo4j session context manager."""
        driver = await self.get_driver()
        async with driver.session(database=settings.neo4j_database) as session:
            yield session

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
        Store an interaction in the knowledge graph.

        Args:
            interaction_id: Unique identifier for the interaction
            user_id: User identifier
            user_message: The user's message
            assistant_response: Alex's response
            intent: Classified intent
            complexity_score: Complexity score (0-1)
            model_used: Model used for response
            topics: Extracted topics
            entities: Extracted entities
            embedding: Optional embedding vector

        Returns:
            The interaction ID
        """
        today = date.today().isoformat()

        query = """
        // Ensure time tree exists for today
        MERGE (d:Day {date: $date})
        ON CREATE SET d.year = date($date).year,
                      d.month = date($date).month,
                      d.day = date($date).day,
                      d.timestamp = datetime($date)

        // Create interaction
        CREATE (i:Interaction {
            id: $interaction_id,
            user_id: $user_id,
            timestamp: datetime(),
            user_message: $user_message,
            assistant_response: $assistant_response,
            intent: $intent,
            complexity_score: $complexity_score,
            model_used: $model_used,
            embedding: $embedding
        })

        // Link to day
        MERGE (i)-[:OCCURRED_ON]->(d)

        // Link to user
        MERGE (u:User {id: $user_id})
        MERGE (u)-[:HAD_INTERACTION]->(i)

        RETURN i.id AS interaction_id
        """

        async with self.session() as session:
            result = await session.run(
                query,
                interaction_id=interaction_id,
                user_id=user_id,
                date=today,
                user_message=user_message,
                assistant_response=assistant_response,
                intent=intent,
                complexity_score=complexity_score,
                model_used=model_used,
                embedding=embedding,
            )
            record = await result.single()

            # Link to topics
            if topics:
                await self._link_to_concepts(session, interaction_id, topics)

            logger.info(
                "Interaction stored",
                interaction_id=interaction_id,
                date=today,
            )

            return record["interaction_id"] if record else interaction_id

    async def _link_to_concepts(
        self,
        session,
        interaction_id: str,
        topics: list[str],
    ):
        """Link an interaction to concept nodes."""
        query = """
        MATCH (i:Interaction {id: $interaction_id})
        UNWIND $topics AS topic_name
        MERGE (c:Concept {name: topic_name})
        ON CREATE SET c.normalized_name = toLower(replace(topic_name, ' ', '_')),
                      c.first_mentioned = datetime(),
                      c.mention_count = 0
        SET c.mention_count = c.mention_count + 1
        MERGE (i)-[:MENTIONS_CONCEPT]->(c)
        """
        await session.run(query, interaction_id=interaction_id, topics=topics)

    async def get_interactions_for_date(self, date_str: str) -> list[dict[str, Any]]:
        """
        Get all interactions for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of interaction dictionaries
        """
        query = """
        MATCH (d:Day {date: $date})<-[:OCCURRED_ON]-(i:Interaction)
        RETURN i.id AS id,
               i.user_message AS user_message,
               i.assistant_response AS assistant_response,
               i.intent AS intent,
               i.timestamp AS timestamp
        ORDER BY i.timestamp
        """

        async with self.session() as session:
            result = await session.run(query, date=date_str)
            records = await result.data()
            return records

    async def get_daily_summary(self, date_str: str) -> dict[str, Any] | None:
        """
        Get the daily summary for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Summary dictionary or None
        """
        query = """
        MATCH (d:Day {date: $date})<-[:SUMMARIZES]-(ds:DailySummary)
        RETURN ds.content AS content,
               ds.key_topics AS key_topics,
               ds.generated_at AS generated_at
        """

        async with self.session() as session:
            result = await session.run(query, date=date_str)
            record = await result.single()
            return dict(record) if record else None

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
        query = """
        MATCH (d:Day {date: $date})
        MERGE (ds:DailySummary {date: $date})
        ON CREATE SET ds.generated_at = datetime(),
                      ds.status = 'completed'
        SET ds.content = $content,
            ds.key_topics = $key_topics,
            ds.interaction_count = $interaction_count,
            ds.model_used = $model_used
        MERGE (ds)-[:SUMMARIZES]->(d)
        RETURN ds.date AS date
        """

        async with self.session() as session:
            result = await session.run(
                query,
                date=date_str,
                content=content,
                key_topics=key_topics,
                interaction_count=interaction_count,
                model_used=model_used,
            )
            record = await result.single()
            return record["date"] if record else date_str

    async def get_weekly_summary(self, week_id: str) -> dict[str, Any] | None:
        """
        Get the weekly summary for a specific week.

        Args:
            week_id: Week ID in YYYY-Wxx format

        Returns:
            Summary dictionary or None
        """
        query = """
        MATCH (w:Week {id: $week_id})<-[:SUMMARIZES]-(ws:WeeklySummary)
        RETURN ws.content AS content,
               ws.key_themes AS key_themes,
               ws.generated_at AS generated_at
        """

        async with self.session() as session:
            result = await session.run(query, week_id=week_id)
            record = await result.single()
            return dict(record) if record else None

    async def get_related_concepts(self, concept_names: list[str]) -> list[dict[str, Any]]:
        """
        Get concepts related to the given concept names.

        Args:
            concept_names: List of concept names to find relations for

        Returns:
            List of related concept dictionaries
        """
        query = """
        UNWIND $concepts AS concept_name
        MATCH (c:Concept {name: concept_name})
        OPTIONAL MATCH (c)-[:RELATED_TO]-(related:Concept)
        RETURN c.name AS concept,
               collect(DISTINCT related.name) AS related_concepts,
               c.mention_count AS mentions
        """

        async with self.session() as session:
            result = await session.run(query, concepts=concept_names)
            records = await result.data()
            return records

    async def ensure_time_tree(self, date_str: str):
        """
        Ensure time tree nodes exist for a given date.

        Args:
            date_str: Date in YYYY-MM-DD format
        """
        query = """
        WITH date($date) AS d
        MERGE (y:Year {year: d.year})
        MERGE (m:Month {id: toString(d.year) + '-' + toString(d.month)})
        ON CREATE SET m.month = d.month, m.year = d.year
        MERGE (y)-[:HAS_MONTH]->(m)
        MERGE (w:Week {id: toString(d.year) + '-W' +
          CASE WHEN d.week < 10 THEN '0' + toString(d.week) ELSE toString(d.week) END})
        ON CREATE SET w.week = d.week, w.year = d.year
        MERGE (y)-[:HAS_WEEK]->(w)
        MERGE (day:Day {date: $date})
        ON CREATE SET day.year = d.year, day.month = d.month, day.day = d.day,
                      day.day_of_week = d.dayOfWeek, day.week_number = d.week
        MERGE (m)-[:HAS_DAY]->(day)
        MERGE (w)-[:CONTAINS_DAY]->(day)
        """

        async with self.session() as session:
            await session.run(query, date=date_str)

    async def get_unsummarized_days(self, limit: int = 30) -> list[str]:
        """
        Get dates that have interactions but no daily summary.

        Args:
            limit: Maximum number of days to return

        Returns:
            List of date strings (YYYY-MM-DD format)
        """
        query = """
        MATCH (d:Day)<-[:OCCURRED_ON]-(i:Interaction)
        WHERE NOT EXISTS {
            MATCH (ds:DailySummary)-[:SUMMARIZES]->(d)
        }
        WITH d.date AS date, count(i) AS interaction_count
        WHERE interaction_count > 0
        RETURN date
        ORDER BY date DESC
        LIMIT $limit
        """

        async with self.session() as session:
            result = await session.run(query, limit=limit)
            records = await result.data()
            return [r["date"] for r in records]

    async def get_daily_summaries_for_week(self, week_id: str) -> list[dict[str, Any]]:
        """
        Get all daily summaries for a specific week.

        Args:
            week_id: Week ID in YYYY-Wxx format

        Returns:
            List of daily summary dictionaries
        """
        query = """
        MATCH (w:Week {id: $week_id})-[:CONTAINS_DAY]->(d:Day)<-[:SUMMARIZES]-(ds:DailySummary)
        RETURN ds.date AS date,
               ds.content AS content,
               ds.key_topics AS key_topics,
               ds.interaction_count AS interaction_count
        ORDER BY ds.date
        """

        async with self.session() as session:
            result = await session.run(query, week_id=week_id)
            records = await result.data()
            return records

    async def get_unsummarized_weeks(self, limit: int = 10) -> list[str]:
        """
        Get weeks that have daily summaries but no weekly summary.

        Args:
            limit: Maximum number of weeks to return

        Returns:
            List of week IDs (YYYY-Wxx format)
        """
        query = """
        MATCH (w:Week)-[:CONTAINS_DAY]->(d:Day)<-[:SUMMARIZES]-(ds:DailySummary)
        WHERE NOT EXISTS {
            MATCH (ws:WeeklySummary)-[:SUMMARIZES]->(w)
        }
        WITH w.id AS week_id, count(ds) AS summary_count
        WHERE summary_count >= 1
        RETURN week_id
        ORDER BY week_id DESC
        LIMIT $limit
        """

        async with self.session() as session:
            result = await session.run(query, limit=limit)
            records = await result.data()
            return [r["week_id"] for r in records]

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
        query = """
        MATCH (w:Week {id: $week_id})
        MERGE (ws:WeeklySummary {week_id: $week_id})
        ON CREATE SET ws.generated_at = datetime(),
                      ws.status = 'completed'
        SET ws.content = $content,
            ws.key_themes = $key_themes,
            ws.daily_summary_count = $daily_summary_count,
            ws.total_interactions = $total_interactions,
            ws.model_used = $model_used,
            ws.embedding = $embedding
        MERGE (ws)-[:SUMMARIZES]->(w)
        RETURN ws.week_id AS week_id
        """

        async with self.session() as session:
            result = await session.run(
                query,
                week_id=week_id,
                content=content,
                key_themes=key_themes,
                daily_summary_count=daily_summary_count,
                total_interactions=total_interactions,
                model_used=model_used,
                embedding=embedding,
            )
            record = await result.single()

            # Link to daily summaries
            await session.run("""
                MATCH (ws:WeeklySummary {week_id: $week_id})
                MATCH (w:Week {id: $week_id})-[:CONTAINS_DAY]->(d:Day)<-[:SUMMARIZES]-(ds:DailySummary)
                MERGE (ws)-[:AGGREGATES]->(ds)
            """, week_id=week_id)

            return record["week_id"] if record else week_id

    async def get_weekly_summaries_for_month(self, month_id: str) -> list[dict[str, Any]]:
        """
        Get all weekly summaries for a specific month.

        Args:
            month_id: Month ID in YYYY-M format (e.g., "2026-1")

        Returns:
            List of weekly summary dictionaries
        """
        # Parse month_id to get year and month
        parts = month_id.split("-")
        year = int(parts[0])
        month = int(parts[1])

        query = """
        MATCH (m:Month {id: $month_id})-[:HAS_DAY]->(d:Day)<-[:CONTAINS_DAY]-(w:Week)
        WITH DISTINCT w
        MATCH (ws:WeeklySummary)-[:SUMMARIZES]->(w)
        RETURN ws.week_id AS week_id,
               ws.content AS content,
               ws.key_themes AS key_themes,
               ws.total_interactions AS total_interactions
        ORDER BY ws.week_id
        """

        async with self.session() as session:
            result = await session.run(query, month_id=month_id)
            records = await result.data()
            return records

    async def get_unsummarized_months(self, limit: int = 6) -> list[str]:
        """
        Get months that have weekly summaries but no monthly summary.

        Args:
            limit: Maximum number of months to return

        Returns:
            List of month IDs (YYYY-M format)
        """
        query = """
        MATCH (m:Month)-[:HAS_DAY]->(d:Day)<-[:CONTAINS_DAY]-(w:Week)<-[:SUMMARIZES]-(ws:WeeklySummary)
        WHERE NOT EXISTS {
            MATCH (ms:MonthlySummary)-[:SUMMARIZES]->(m)
        }
        WITH m.id AS month_id, count(DISTINCT ws) AS summary_count
        WHERE summary_count >= 1
        RETURN month_id
        ORDER BY month_id DESC
        LIMIT $limit
        """

        async with self.session() as session:
            result = await session.run(query, limit=limit)
            records = await result.data()
            return [r["month_id"] for r in records]

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
        query = """
        MATCH (m:Month {id: $month_id})
        MERGE (ms:MonthlySummary {month_id: $month_id})
        ON CREATE SET ms.generated_at = datetime(),
                      ms.status = 'completed'
        SET ms.content = $content,
            ms.key_themes = $key_themes,
            ms.weekly_summary_count = $weekly_summary_count,
            ms.total_interactions = $total_interactions,
            ms.model_used = $model_used,
            ms.embedding = $embedding
        MERGE (ms)-[:SUMMARIZES]->(m)
        RETURN ms.month_id AS month_id
        """

        async with self.session() as session:
            result = await session.run(
                query,
                month_id=month_id,
                content=content,
                key_themes=key_themes,
                weekly_summary_count=weekly_summary_count,
                total_interactions=total_interactions,
                model_used=model_used,
                embedding=embedding,
            )
            record = await result.single()

            # Link to weekly summaries
            await session.run("""
                MATCH (ms:MonthlySummary {month_id: $month_id})
                MATCH (m:Month {id: $month_id})-[:HAS_DAY]->(d:Day)<-[:CONTAINS_DAY]-(w:Week)<-[:SUMMARIZES]-(ws:WeeklySummary)
                MERGE (ms)-[:AGGREGATES]->(ws)
            """, month_id=month_id)

            return record["month_id"] if record else month_id

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
        Store a code change in the knowledge graph.

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
        today = date.today().isoformat()

        query = """
        // Ensure time tree exists
        MERGE (d:Day {date: $date})

        // Create code change node
        CREATE (cc:CodeChange {
            id: $change_id,
            timestamp: datetime(),
            files_modified: $files_modified,
            description: $description,
            reasoning: $reasoning,
            change_type: $change_type,
            commit_sha: $commit_sha,
            file_count: size($files_modified)
        })

        // Link to day
        MERGE (cc)-[:OCCURRED_ON]->(d)

        // Link to user
        MERGE (u:User {id: $user_id})
        MERGE (u)-[:MADE_CHANGE]->(cc)

        RETURN cc.id AS change_id
        """

        async with self.session() as session:
            result = await session.run(
                query,
                change_id=change_id,
                date=today,
                files_modified=files_modified,
                description=description,
                reasoning=reasoning,
                change_type=change_type,
                commit_sha=commit_sha,
            )
            record = await result.single()

            # Link to triggering interaction if provided
            if related_interaction_id:
                await session.run("""
                    MATCH (cc:CodeChange {id: $change_id})
                    MATCH (i:Interaction {id: $interaction_id})
                    MERGE (cc)-[:TRIGGERED_BY]->(i)
                """, change_id=change_id, interaction_id=related_interaction_id)

            # Extract and link concepts from files modified
            concepts = self._extract_concepts_from_files(files_modified)
            if concepts:
                await self._link_change_to_concepts(session, change_id, concepts)

            logger.info(
                "Code change stored",
                change_id=change_id,
                files=files_modified,
                change_type=change_type,
            )

            return record["change_id"] if record else change_id

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
        session,
        change_id: str,
        concepts: list[str],
    ):
        """Link a code change to concept nodes."""
        query = """
        MATCH (cc:CodeChange {id: $change_id})
        UNWIND $concepts AS concept_name
        MERGE (c:Concept {name: concept_name})
        ON CREATE SET c.normalized_name = toLower(replace(concept_name, ' ', '_')),
                      c.first_mentioned = datetime(),
                      c.mention_count = 0
        SET c.mention_count = c.mention_count + 1
        MERGE (cc)-[:MODIFIES_CONCEPT]->(c)
        """
        await session.run(query, change_id=change_id, concepts=concepts)

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
        query = """
        MATCH (cc:CodeChange)
        """ + ("WHERE cc.change_type = $change_type" if change_type else "") + """
        RETURN cc.id AS id,
               cc.description AS description,
               cc.reasoning AS reasoning,
               cc.files_modified AS files_modified,
               cc.change_type AS change_type,
               cc.commit_sha AS commit_sha,
               toString(cc.timestamp) AS timestamp
        ORDER BY cc.timestamp DESC
        LIMIT $limit
        """

        async with self.session() as session:
            result = await session.run(
                query,
                limit=limit,
                change_type=change_type,
            )
            records = await result.data()
            return records

    async def get_code_changes_for_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        Get all code changes that modified a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of code change dictionaries
        """
        query = """
        MATCH (cc:CodeChange)
        WHERE $file_path IN cc.files_modified
        RETURN cc.id AS id,
               cc.description AS description,
               cc.reasoning AS reasoning,
               cc.change_type AS change_type,
               cc.commit_sha AS commit_sha,
               toString(cc.timestamp) AS timestamp
        ORDER BY cc.timestamp DESC
        """

        async with self.session() as session:
            result = await session.run(query, file_path=file_path)
            records = await result.data()
            return records

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the Neo4j connection.

        Returns:
            Health status dictionary
        """
        query = """
        MATCH (n)
        WITH labels(n) AS nodeLabels, count(*) AS cnt
        UNWIND nodeLabels AS label
        RETURN label, sum(cnt) AS count
        ORDER BY count DESC
        LIMIT 10
        """

        try:
            async with self.session() as session:
                result = await session.run(query)
                records = await result.data()
                return {
                    "status": "healthy",
                    "node_counts": {r["label"]: r["count"] for r in records},
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
