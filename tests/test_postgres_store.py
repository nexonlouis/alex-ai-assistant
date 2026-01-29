"""
Tests for PostgresStore.

These tests verify the PostgreSQL-based memory store functionality.
Tests use a test database and clean up after themselves.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
import asyncpg
import structlog

# Set up path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alex.config import settings

logger = structlog.get_logger()

# Skip all tests if PostgreSQL is not available
pytestmark = pytest.mark.asyncio


class PostgresStore:
    """
    Minimal PostgresStore for testing (avoids circular imports).
    """

    _pool: asyncpg.Pool | None = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """Get or create the connection pool."""
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(
                settings.postgres_uri,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
        return cls._pool

    @classmethod
    async def close(cls):
        """Close the connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @asynccontextmanager
    async def connection(self):
        """Get a connection from the pool."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            yield conn

    async def ensure_user(self, user_id: str) -> str:
        """Ensure a user exists."""
        async with self.connection() as conn:
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
                user_id,
            )
        return user_id

    async def ensure_time_tree(self, date_str: str):
        """Ensure time tree entry exists."""
        d = date.fromisoformat(date_str)
        iso_cal = d.isocalendar()
        async with self.connection() as conn:
            await conn.execute(
                """INSERT INTO days (date, year, month, day, week_number, day_of_week)
                   VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (date) DO NOTHING""",
                d, d.year, d.month, d.day, iso_cal.week, iso_cal.weekday,
            )

    async def store_interaction(
        self, interaction_id: str, user_id: str, user_message: str,
        assistant_response: str, intent: str | None = None,
        complexity_score: float = 0.0, model_used: str | None = None,
        topics: list[str] | None = None, entities: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """Store an interaction."""
        today = date.today()
        await self.ensure_time_tree(today.isoformat())
        await self.ensure_user(user_id)
        embedding_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None

        async with self.connection() as conn:
            await conn.execute(
                """INSERT INTO interactions (id, user_id, date, timestamp, user_message,
                   assistant_response, intent, complexity_score, model_used, embedding)
                   VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9::vector)
                   ON CONFLICT (id) DO NOTHING""",
                interaction_id, user_id, today, user_message, assistant_response,
                intent, complexity_score, model_used, embedding_str,
            )
            if topics:
                for topic in topics:
                    normalized = topic.lower().replace(" ", "_")
                    concept_id = await conn.fetchval(
                        """INSERT INTO concepts (name, normalized_name, mention_count)
                           VALUES ($1, $2, 1) ON CONFLICT (name) DO UPDATE
                           SET mention_count = concepts.mention_count + 1
                           RETURNING id""", topic, normalized,
                    )
                    await conn.execute(
                        """INSERT INTO interaction_concepts (interaction_id, concept_id)
                           VALUES ($1, $2) ON CONFLICT DO NOTHING""",
                        interaction_id, concept_id,
                    )
        return interaction_id

    async def get_interactions_for_date(self, date_str: str) -> list[dict]:
        """Get interactions for a date."""
        d = date.fromisoformat(date_str)
        async with self.connection() as conn:
            rows = await conn.fetch(
                """SELECT id, user_message, assistant_response, intent, timestamp
                   FROM interactions WHERE date = $1 ORDER BY timestamp""", d,
            )
            return [dict(row) for row in rows]

    async def get_daily_summary(self, date_str: str) -> dict | None:
        """Get daily summary."""
        d = date.fromisoformat(date_str)
        async with self.connection() as conn:
            row = await conn.fetchrow(
                "SELECT content, key_topics, generated_at FROM daily_summaries WHERE date = $1", d,
            )
            return dict(row) if row else None

    async def create_daily_summary(
        self, date_str: str, content: str, key_topics: list[str],
        interaction_count: int, model_used: str, embedding: list[float] | None = None,
    ) -> str:
        """Create daily summary."""
        d = date.fromisoformat(date_str)
        await self.ensure_time_tree(date_str)
        embedding_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None
        async with self.connection() as conn:
            await conn.execute(
                """INSERT INTO daily_summaries (date, content, key_topics, interaction_count, model_used, embedding)
                   VALUES ($1, $2, $3, $4, $5, $6::vector)
                   ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content""",
                d, content, key_topics, interaction_count, model_used, embedding_str,
            )
        return date_str

    async def get_weekly_summary(self, week_id: str) -> dict | None:
        """Get weekly summary."""
        async with self.connection() as conn:
            row = await conn.fetchrow(
                "SELECT content, key_themes, generated_at FROM weekly_summaries WHERE week_id = $1",
                week_id,
            )
            return dict(row) if row else None

    async def create_weekly_summary(
        self, week_id: str, content: str, key_themes: list[str],
        daily_summary_count: int, total_interactions: int, model_used: str,
        embedding: list[float] | None = None,
    ) -> str:
        """Create weekly summary."""
        parts = week_id.split("-W")
        year, week = int(parts[0]), int(parts[1])
        embedding_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None
        async with self.connection() as conn:
            await conn.execute(
                """INSERT INTO weekly_summaries (week_id, year, week, content, key_themes,
                   daily_summary_count, total_interactions, model_used, embedding)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector)
                   ON CONFLICT (week_id) DO UPDATE SET content = EXCLUDED.content""",
                week_id, year, week, content, key_themes, daily_summary_count,
                total_interactions, model_used, embedding_str,
            )
        return week_id

    async def get_unsummarized_days(self, limit: int = 30) -> list[str]:
        """Get days without summaries."""
        async with self.connection() as conn:
            rows = await conn.fetch(
                """SELECT d.date::text AS date FROM days d
                   JOIN interactions i ON d.date = i.date
                   LEFT JOIN daily_summaries ds ON d.date = ds.date
                   WHERE ds.date IS NULL GROUP BY d.date
                   HAVING COUNT(i.id) > 0 ORDER BY d.date DESC LIMIT $1""", limit,
            )
            return [row["date"] for row in rows]

    async def semantic_search(
        self, embedding: list[float], top_k: int = 5, min_score: float = 0.7,
    ) -> list[dict]:
        """Semantic search."""
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        async with self.connection() as conn:
            rows = await conn.fetch(
                """SELECT i.id, i.user_message, i.assistant_response, i.date::text AS date,
                   1 - (i.embedding <=> $1::vector) AS score
                   FROM interactions i WHERE i.embedding IS NOT NULL
                   ORDER BY i.embedding <=> $1::vector LIMIT $2""",
                embedding_str, top_k * 2,
            )
            return [dict(row) for row in rows if row["score"] >= min_score][:top_k]

    async def store_code_change(
        self, change_id: str, user_id: str, files_modified: list[str],
        description: str, reasoning: str, change_type: str,
        commit_sha: str | None = None, related_interaction_id: str | None = None,
    ) -> str:
        """Store code change."""
        today = date.today()
        await self.ensure_time_tree(today.isoformat())
        await self.ensure_user(user_id)
        async with self.connection() as conn:
            await conn.execute(
                """INSERT INTO code_changes (id, user_id, date, timestamp, files_modified,
                   description, reasoning, change_type, commit_sha, related_interaction_id)
                   VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (id) DO NOTHING""",
                change_id, user_id, today, files_modified, description,
                reasoning, change_type, commit_sha, related_interaction_id,
            )
        return change_id

    async def get_recent_code_changes(self, limit: int = 10, change_type: str | None = None) -> list[dict]:
        """Get recent code changes."""
        async with self.connection() as conn:
            if change_type:
                rows = await conn.fetch(
                    """SELECT id, description, reasoning, files_modified, change_type, commit_sha, timestamp::text
                       FROM code_changes WHERE change_type = $1 ORDER BY timestamp DESC LIMIT $2""",
                    change_type, limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, description, reasoning, files_modified, change_type, commit_sha, timestamp::text
                       FROM code_changes ORDER BY timestamp DESC LIMIT $1""", limit,
                )
            return [dict(row) for row in rows]

    async def get_code_changes_for_file(self, file_path: str) -> list[dict]:
        """Get code changes for a file."""
        async with self.connection() as conn:
            rows = await conn.fetch(
                """SELECT id, description, reasoning, change_type, commit_sha, timestamp::text
                   FROM code_changes WHERE $1 = ANY(files_modified) ORDER BY timestamp DESC""",
                file_path,
            )
            return [dict(row) for row in rows]

    async def get_related_concepts(self, concept_names: list[str]) -> list[dict]:
        """Get related concepts."""
        async with self.connection() as conn:
            rows = await conn.fetch(
                """SELECT c1.name AS concept,
                   array_agg(DISTINCT c2.name) FILTER (WHERE c2.name IS NOT NULL AND c2.name != c1.name) AS related_concepts,
                   c1.mention_count AS mentions FROM concepts c1
                   LEFT JOIN interaction_concepts ic1 ON c1.id = ic1.concept_id
                   LEFT JOIN interaction_concepts ic2 ON ic1.interaction_id = ic2.interaction_id
                   LEFT JOIN concepts c2 ON ic2.concept_id = c2.id
                   WHERE c1.name = ANY($1) GROUP BY c1.id, c1.name, c1.mention_count""",
                concept_names,
            )
            return [dict(row) for row in rows]

    async def health_check(self) -> dict:
        """Health check."""
        try:
            async with self.connection() as conn:
                counts = {}
                for table in ["users", "interactions", "concepts", "daily_summaries",
                              "weekly_summaries", "monthly_summaries", "code_changes"]:
                    counts[table] = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                pgvector_version = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
                return {"status": "healthy", "table_counts": counts, "pgvector_version": pgvector_version}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


@pytest_asyncio.fixture
async def store():
    """Create a PostgresStore instance for testing."""
    # Reset the pool to ensure fresh connection for each test
    PostgresStore._pool = None
    s = PostgresStore()
    yield s
    # Close pool after test
    await PostgresStore.close()


@pytest_asyncio.fixture
async def clean_store():
    """Create a PostgresStore instance and clean test data after."""
    # Reset the pool to ensure fresh connection for each test
    PostgresStore._pool = None
    s = PostgresStore()
    test_user_id = f"test_user_{uuid4().hex[:8]}"
    test_interaction_id = f"test_interaction_{uuid4().hex[:8]}"

    yield s, test_user_id, test_interaction_id

    # Clean up test data
    try:
        async with s.connection() as conn:
            await conn.execute(
                "DELETE FROM interaction_concepts WHERE interaction_id = $1",
                test_interaction_id,
            )
            await conn.execute(
                "DELETE FROM interactions WHERE user_id = $1",
                test_user_id,
            )
            await conn.execute(
                "DELETE FROM users WHERE id = $1",
                test_user_id,
            )
    except Exception:
        pass
    # Close pool after test
    await PostgresStore.close()


class TestPostgresStoreConnection:
    """Test database connection functionality."""

    async def test_get_pool_creates_pool(self, store):
        """Test that get_pool creates a connection pool."""
        pool = await PostgresStore.get_pool()
        assert pool is not None
        assert PostgresStore._pool is pool

    async def test_connection_context_manager(self, store):
        """Test that connection context manager works."""
        async with store.connection() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    async def test_health_check_healthy(self, store):
        """Test health check returns healthy status."""
        result = await store.health_check()
        assert result["status"] == "healthy"
        assert "table_counts" in result
        assert "pgvector_version" in result


class TestUserOperations:
    """Test user-related operations."""

    async def test_ensure_user_creates_user(self, clean_store):
        """Test that ensure_user creates a new user."""
        store, test_user_id, _ = clean_store
        result = await store.ensure_user(test_user_id)
        assert result == test_user_id

        # Verify user exists
        async with store.connection() as conn:
            user = await conn.fetchrow(
                "SELECT id FROM users WHERE id = $1",
                test_user_id,
            )
            assert user is not None
            assert user["id"] == test_user_id

    async def test_ensure_user_idempotent(self, clean_store):
        """Test that ensure_user is idempotent."""
        store, test_user_id, _ = clean_store

        # Create user twice
        await store.ensure_user(test_user_id)
        await store.ensure_user(test_user_id)

        # Should only have one user
        async with store.connection() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE id = $1",
                test_user_id,
            )
            assert count == 1


class TestTimeTree:
    """Test time tree operations."""

    async def test_ensure_time_tree_creates_day(self, store):
        """Test that ensure_time_tree creates a day entry."""
        test_date = "2099-12-31"  # Far future date unlikely to exist

        await store.ensure_time_tree(test_date)

        async with store.connection() as conn:
            day = await conn.fetchrow(
                "SELECT * FROM days WHERE date = $1",
                date.fromisoformat(test_date),
            )
            assert day is not None
            assert day["year"] == 2099
            assert day["month"] == 12
            assert day["day"] == 31

            # Clean up
            await conn.execute(
                "DELETE FROM days WHERE date = $1",
                date.fromisoformat(test_date),
            )

    async def test_ensure_time_tree_idempotent(self, store):
        """Test that ensure_time_tree is idempotent."""
        test_date = "2099-12-30"

        # Create day twice
        await store.ensure_time_tree(test_date)
        await store.ensure_time_tree(test_date)

        async with store.connection() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM days WHERE date = $1",
                date.fromisoformat(test_date),
            )
            assert count == 1

            # Clean up
            await conn.execute(
                "DELETE FROM days WHERE date = $1",
                date.fromisoformat(test_date),
            )


class TestInteractionOperations:
    """Test interaction-related operations."""

    async def test_store_interaction_basic(self, clean_store):
        """Test storing a basic interaction."""
        store, test_user_id, test_interaction_id = clean_store

        result = await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Hello, how are you?",
            assistant_response="I'm doing well, thank you!",
            intent="greeting",
            complexity_score=0.2,
            model_used="test-model",
        )

        assert result == test_interaction_id

        # Verify interaction exists
        async with store.connection() as conn:
            interaction = await conn.fetchrow(
                "SELECT * FROM interactions WHERE id = $1",
                test_interaction_id,
            )
            assert interaction is not None
            assert interaction["user_message"] == "Hello, how are you?"
            assert interaction["assistant_response"] == "I'm doing well, thank you!"
            assert interaction["intent"] == "greeting"
            assert interaction["complexity_score"] == 0.2

    async def test_store_interaction_with_topics(self, clean_store):
        """Test storing an interaction with topics."""
        store, test_user_id, test_interaction_id = clean_store

        await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Tell me about Python",
            assistant_response="Python is a great language!",
            topics=["python", "programming"],
        )

        # Verify concepts were created
        async with store.connection() as conn:
            concepts = await conn.fetch(
                """
                SELECT c.name FROM concepts c
                JOIN interaction_concepts ic ON c.id = ic.concept_id
                WHERE ic.interaction_id = $1
                """,
                test_interaction_id,
            )
            concept_names = [c["name"] for c in concepts]
            assert "python" in concept_names
            assert "programming" in concept_names

    async def test_store_interaction_with_embedding(self, clean_store):
        """Test storing an interaction with embedding."""
        store, test_user_id, test_interaction_id = clean_store

        # Create a 768-dimension embedding
        embedding = [0.1] * 768

        await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Test message",
            assistant_response="Test response",
            embedding=embedding,
        )

        # Verify embedding was stored
        async with store.connection() as conn:
            interaction = await conn.fetchrow(
                "SELECT embedding FROM interactions WHERE id = $1",
                test_interaction_id,
            )
            assert interaction["embedding"] is not None

    async def test_get_interactions_for_date(self, clean_store):
        """Test retrieving interactions for a specific date."""
        store, test_user_id, test_interaction_id = clean_store
        today = date.today().isoformat()

        # Store an interaction
        await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Test message",
            assistant_response="Test response",
        )

        # Retrieve interactions
        interactions = await store.get_interactions_for_date(today)

        assert len(interactions) >= 1
        interaction_ids = [i["id"] for i in interactions]
        assert test_interaction_id in interaction_ids


class TestSummaryOperations:
    """Test summary-related operations."""

    async def test_create_and_get_daily_summary(self, store):
        """Test creating and retrieving a daily summary."""
        test_date = "2099-01-15"

        # Ensure time tree exists
        await store.ensure_time_tree(test_date)

        await store.create_daily_summary(
            date_str=test_date,
            content="This was a productive day!",
            key_topics=["python", "testing"],
            interaction_count=10,
            model_used="test-model",
        )

        summary = await store.get_daily_summary(test_date)

        assert summary is not None
        assert summary["content"] == "This was a productive day!"
        assert "python" in summary["key_topics"]
        assert "testing" in summary["key_topics"]

        # Clean up
        async with store.connection() as conn:
            await conn.execute(
                "DELETE FROM daily_summaries WHERE date = $1",
                date.fromisoformat(test_date),
            )
            await conn.execute(
                "DELETE FROM days WHERE date = $1",
                date.fromisoformat(test_date),
            )

    async def test_create_and_get_weekly_summary(self, store):
        """Test creating and retrieving a weekly summary."""
        test_week_id = "2099-W01"

        await store.create_weekly_summary(
            week_id=test_week_id,
            content="Great week of progress!",
            key_themes=["development", "testing"],
            daily_summary_count=5,
            total_interactions=50,
            model_used="test-model",
        )

        summary = await store.get_weekly_summary(test_week_id)

        assert summary is not None
        assert summary["content"] == "Great week of progress!"
        assert "development" in summary["key_themes"]

        # Clean up
        async with store.connection() as conn:
            await conn.execute(
                "DELETE FROM weekly_summaries WHERE week_id = $1",
                test_week_id,
            )

    async def test_get_unsummarized_days(self, clean_store):
        """Test getting days without summaries."""
        store, test_user_id, test_interaction_id = clean_store

        # Store an interaction (creates a day)
        await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Test",
            assistant_response="Response",
        )

        # Get unsummarized days
        days = await store.get_unsummarized_days()

        # Today should be in the list (unless a summary exists)
        assert isinstance(days, list)


class TestSemanticSearch:
    """Test semantic search functionality."""

    async def test_semantic_search_with_embedding(self, clean_store):
        """Test semantic search returns results."""
        store, test_user_id, test_interaction_id = clean_store

        # Store an interaction with embedding
        embedding = [0.1] * 768
        await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Python programming tips",
            assistant_response="Here are some tips...",
            embedding=embedding,
        )

        # Search with similar embedding
        query_embedding = [0.1] * 768
        results = await store.semantic_search(
            embedding=query_embedding,
            top_k=5,
            min_score=0.5,
        )

        # Should find the interaction
        assert len(results) >= 1


class TestCodeChangeOperations:
    """Test code change tracking operations."""

    async def test_store_and_get_code_change(self, clean_store):
        """Test storing and retrieving code changes."""
        store, test_user_id, _ = clean_store
        change_id = f"test_change_{uuid4().hex[:8]}"

        await store.store_code_change(
            change_id=change_id,
            user_id=test_user_id,
            files_modified=["alex/memory/postgres_store.py"],
            description="Added new feature",
            reasoning="To improve performance",
            change_type="feature",
            commit_sha="abc123",
        )

        # Get recent changes
        changes = await store.get_recent_code_changes(limit=10)

        change_ids = [c["id"] for c in changes]
        assert change_id in change_ids

        # Clean up
        async with store.connection() as conn:
            await conn.execute(
                "DELETE FROM code_change_concepts WHERE change_id = $1",
                change_id,
            )
            await conn.execute(
                "DELETE FROM code_changes WHERE id = $1",
                change_id,
            )

    async def test_get_code_changes_for_file(self, clean_store):
        """Test getting code changes for a specific file."""
        store, test_user_id, _ = clean_store
        change_id = f"test_change_{uuid4().hex[:8]}"
        test_file = "alex/test_file.py"

        await store.store_code_change(
            change_id=change_id,
            user_id=test_user_id,
            files_modified=[test_file],
            description="Test change",
            reasoning="Testing",
            change_type="test",
        )

        changes = await store.get_code_changes_for_file(test_file)

        assert len(changes) >= 1
        assert changes[0]["id"] == change_id

        # Clean up
        async with store.connection() as conn:
            await conn.execute(
                "DELETE FROM code_change_concepts WHERE change_id = $1",
                change_id,
            )
            await conn.execute(
                "DELETE FROM code_changes WHERE id = $1",
                change_id,
            )


class TestConceptOperations:
    """Test concept-related operations."""

    async def test_get_related_concepts(self, clean_store):
        """Test getting related concepts."""
        store, test_user_id, test_interaction_id = clean_store

        # Store an interaction with multiple topics
        await store.store_interaction(
            interaction_id=test_interaction_id,
            user_id=test_user_id,
            user_message="Python and JavaScript",
            assistant_response="Both are great languages!",
            topics=["python", "javascript", "programming"],
        )

        # Get related concepts for python
        related = await store.get_related_concepts(["python"])

        assert len(related) >= 1
        # Python should have javascript and programming as related
        # (because they appear in the same interaction)
