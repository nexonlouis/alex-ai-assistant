#!/usr/bin/env python3
"""
Migration script: Neo4j to PostgreSQL

This script migrates all data from Neo4j AuraDB to PostgreSQL with pgvector.

Usage:
    # Set environment variables
    export NEO4J_URI="neo4j+s://xxx.databases.neo4j.io"
    export NEO4J_USERNAME="neo4j"
    export NEO4J_PASSWORD="your-password"
    export POSTGRES_URI="postgresql://user:pass@host:5432/alex"

    # Run migration
    python scripts/migrate_neo4j_to_postgres.py

    # Dry run (show what would be migrated)
    python scripts/migrate_neo4j_to_postgres.py --dry-run

    # Migrate specific tables only
    python scripts/migrate_neo4j_to_postgres.py --only interactions,concepts
"""

import argparse
import asyncio
import sys
from datetime import date
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase
import asyncpg

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


class Neo4jToPostgresMigrator:
    """Migrates data from Neo4j to PostgreSQL."""

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        postgres_uri: str,
        neo4j_database: str = "neo4j",
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.neo4j_database = neo4j_database
        self.postgres_uri = postgres_uri
        self.neo4j_driver = None
        self.pg_pool = None
        self.dry_run = False

        # Migration stats
        self.stats = {
            "users": 0,
            "days": 0,
            "interactions": 0,
            "concepts": 0,
            "interaction_concepts": 0,
            "daily_summaries": 0,
            "weekly_summaries": 0,
            "monthly_summaries": 0,
            "code_changes": 0,
            "code_change_concepts": 0,
        }

    async def connect(self):
        """Connect to both databases."""
        logger.info("Connecting to Neo4j", uri=self.neo4j_uri)
        self.neo4j_driver = AsyncGraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password),
        )
        await self.neo4j_driver.verify_connectivity()
        logger.info("Neo4j connected")

        logger.info("Connecting to PostgreSQL")
        self.pg_pool = await asyncpg.create_pool(
            self.postgres_uri,
            min_size=2,
            max_size=10,
        )
        logger.info("PostgreSQL connected")

    async def close(self):
        """Close both database connections."""
        if self.neo4j_driver:
            await self.neo4j_driver.close()
        if self.pg_pool:
            await self.pg_pool.close()
        logger.info("Connections closed")

    async def neo4j_query(self, query: str, **params) -> list[dict]:
        """Execute a Neo4j query and return results."""
        async with self.neo4j_driver.session(database=self.neo4j_database) as session:
            result = await session.run(query, **params)
            return await result.data()

    async def migrate_users(self):
        """Migrate User nodes."""
        logger.info("Migrating users...")

        users = await self.neo4j_query("""
            MATCH (u:User)
            RETURN u.id AS id, u.created_at AS created_at
        """)

        if self.dry_run:
            logger.info("Would migrate users", count=len(users))
            self.stats["users"] = len(users)
            return

        async with self.pg_pool.acquire() as conn:
            for user in users:
                await conn.execute(
                    """
                    INSERT INTO users (id, created_at)
                    VALUES ($1, COALESCE($2, NOW()))
                    ON CONFLICT (id) DO NOTHING
                    """,
                    user["id"],
                    user.get("created_at"),
                )
                self.stats["users"] += 1

        logger.info("Users migrated", count=self.stats["users"])

    async def migrate_days(self):
        """Migrate Day nodes to days table."""
        logger.info("Migrating days...")

        days = await self.neo4j_query("""
            MATCH (d:Day)
            RETURN d.date AS date, d.year AS year, d.month AS month,
                   d.day AS day, d.week_number AS week_number,
                   d.day_of_week AS day_of_week
        """)

        if self.dry_run:
            logger.info("Would migrate days", count=len(days))
            self.stats["days"] = len(days)
            return

        async with self.pg_pool.acquire() as conn:
            for d in days:
                try:
                    # Parse date
                    date_val = date.fromisoformat(d["date"])
                    iso_cal = date_val.isocalendar()

                    await conn.execute(
                        """
                        INSERT INTO days (date, year, month, day, week_number, day_of_week)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (date) DO NOTHING
                        """,
                        date_val,
                        d.get("year") or date_val.year,
                        d.get("month") or date_val.month,
                        d.get("day") or date_val.day,
                        d.get("week_number") or iso_cal.week,
                        d.get("day_of_week") or iso_cal.weekday,
                    )
                    self.stats["days"] += 1
                except Exception as e:
                    logger.error("Failed to migrate day", date=d.get("date"), error=str(e))

        logger.info("Days migrated", count=self.stats["days"])

    async def migrate_interactions(self):
        """Migrate Interaction nodes."""
        logger.info("Migrating interactions...")

        interactions = await self.neo4j_query("""
            MATCH (i:Interaction)
            OPTIONAL MATCH (i)-[:OCCURRED_ON]->(d:Day)
            OPTIONAL MATCH (u:User)-[:HAD_INTERACTION]->(i)
            RETURN i.id AS id,
                   u.id AS user_id,
                   d.date AS date,
                   i.timestamp AS timestamp,
                   i.user_message AS user_message,
                   i.assistant_response AS assistant_response,
                   i.intent AS intent,
                   i.complexity_score AS complexity_score,
                   i.model_used AS model_used,
                   i.embedding AS embedding
        """)

        if self.dry_run:
            logger.info("Would migrate interactions", count=len(interactions))
            self.stats["interactions"] = len(interactions)
            return

        async with self.pg_pool.acquire() as conn:
            for i in interactions:
                try:
                    # Parse date
                    date_val = None
                    if i.get("date"):
                        date_val = date.fromisoformat(i["date"])

                    # Convert embedding to pgvector format
                    embedding_str = None
                    if i.get("embedding"):
                        embedding_str = f"[{','.join(str(x) for x in i['embedding'])}]"

                    await conn.execute(
                        """
                        INSERT INTO interactions (
                            id, user_id, date, timestamp, user_message,
                            assistant_response, intent, complexity_score,
                            model_used, embedding
                        )
                        VALUES ($1, $2, $3, COALESCE($4, NOW()), $5, $6, $7, $8, $9, $10::vector)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        i["id"],
                        i.get("user_id"),
                        date_val,
                        i.get("timestamp"),
                        i.get("user_message", ""),
                        i.get("assistant_response", ""),
                        i.get("intent"),
                        i.get("complexity_score", 0.0),
                        i.get("model_used"),
                        embedding_str,
                    )
                    self.stats["interactions"] += 1
                except Exception as e:
                    logger.error("Failed to migrate interaction", id=i.get("id"), error=str(e))

        logger.info("Interactions migrated", count=self.stats["interactions"])

    async def migrate_concepts(self):
        """Migrate Concept nodes."""
        logger.info("Migrating concepts...")

        concepts = await self.neo4j_query("""
            MATCH (c:Concept)
            RETURN c.name AS name,
                   c.normalized_name AS normalized_name,
                   c.first_mentioned AS first_mentioned,
                   c.mention_count AS mention_count
        """)

        if self.dry_run:
            logger.info("Would migrate concepts", count=len(concepts))
            self.stats["concepts"] = len(concepts)
            return

        async with self.pg_pool.acquire() as conn:
            for c in concepts:
                try:
                    await conn.execute(
                        """
                        INSERT INTO concepts (name, normalized_name, first_mentioned, mention_count)
                        VALUES ($1, $2, COALESCE($3, NOW()), $4)
                        ON CONFLICT (name) DO UPDATE SET
                            mention_count = GREATEST(concepts.mention_count, EXCLUDED.mention_count)
                        """,
                        c["name"],
                        c.get("normalized_name") or c["name"].lower().replace(" ", "_"),
                        c.get("first_mentioned"),
                        c.get("mention_count", 0),
                    )
                    self.stats["concepts"] += 1
                except Exception as e:
                    logger.error("Failed to migrate concept", name=c.get("name"), error=str(e))

        logger.info("Concepts migrated", count=self.stats["concepts"])

    async def migrate_interaction_concepts(self):
        """Migrate MENTIONS_CONCEPT relationships."""
        logger.info("Migrating interaction-concept relationships...")

        rels = await self.neo4j_query("""
            MATCH (i:Interaction)-[:MENTIONS_CONCEPT]->(c:Concept)
            RETURN i.id AS interaction_id, c.name AS concept_name
        """)

        if self.dry_run:
            logger.info("Would migrate interaction-concept relationships", count=len(rels))
            self.stats["interaction_concepts"] = len(rels)
            return

        async with self.pg_pool.acquire() as conn:
            for rel in rels:
                try:
                    # Get concept ID
                    concept_id = await conn.fetchval(
                        "SELECT id FROM concepts WHERE name = $1",
                        rel["concept_name"],
                    )
                    if concept_id:
                        await conn.execute(
                            """
                            INSERT INTO interaction_concepts (interaction_id, concept_id)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            rel["interaction_id"],
                            concept_id,
                        )
                        self.stats["interaction_concepts"] += 1
                except Exception as e:
                    logger.error(
                        "Failed to migrate interaction-concept",
                        interaction=rel.get("interaction_id"),
                        error=str(e),
                    )

        logger.info("Interaction-concept relationships migrated", count=self.stats["interaction_concepts"])

    async def migrate_daily_summaries(self):
        """Migrate DailySummary nodes."""
        logger.info("Migrating daily summaries...")

        summaries = await self.neo4j_query("""
            MATCH (ds:DailySummary)
            RETURN ds.date AS date,
                   ds.content AS content,
                   ds.key_topics AS key_topics,
                   ds.interaction_count AS interaction_count,
                   ds.model_used AS model_used,
                   ds.embedding AS embedding,
                   ds.generated_at AS generated_at
        """)

        if self.dry_run:
            logger.info("Would migrate daily summaries", count=len(summaries))
            self.stats["daily_summaries"] = len(summaries)
            return

        async with self.pg_pool.acquire() as conn:
            for ds in summaries:
                try:
                    date_val = date.fromisoformat(ds["date"])

                    # Ensure day exists
                    iso_cal = date_val.isocalendar()
                    await conn.execute(
                        """
                        INSERT INTO days (date, year, month, day, week_number, day_of_week)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (date) DO NOTHING
                        """,
                        date_val,
                        date_val.year,
                        date_val.month,
                        date_val.day,
                        iso_cal.week,
                        iso_cal.weekday,
                    )

                    # Convert embedding
                    embedding_str = None
                    if ds.get("embedding"):
                        embedding_str = f"[{','.join(str(x) for x in ds['embedding'])}]"

                    await conn.execute(
                        """
                        INSERT INTO daily_summaries (
                            date, content, key_topics, interaction_count,
                            model_used, embedding, generated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::vector, COALESCE($7, NOW()))
                        ON CONFLICT (date) DO UPDATE SET
                            content = EXCLUDED.content,
                            key_topics = EXCLUDED.key_topics
                        """,
                        date_val,
                        ds.get("content", ""),
                        ds.get("key_topics", []),
                        ds.get("interaction_count", 0),
                        ds.get("model_used"),
                        embedding_str,
                        ds.get("generated_at"),
                    )
                    self.stats["daily_summaries"] += 1
                except Exception as e:
                    logger.error("Failed to migrate daily summary", date=ds.get("date"), error=str(e))

        logger.info("Daily summaries migrated", count=self.stats["daily_summaries"])

    async def migrate_weekly_summaries(self):
        """Migrate WeeklySummary nodes."""
        logger.info("Migrating weekly summaries...")

        summaries = await self.neo4j_query("""
            MATCH (ws:WeeklySummary)
            RETURN ws.week_id AS week_id,
                   ws.content AS content,
                   ws.key_themes AS key_themes,
                   ws.daily_summary_count AS daily_summary_count,
                   ws.total_interactions AS total_interactions,
                   ws.model_used AS model_used,
                   ws.embedding AS embedding,
                   ws.generated_at AS generated_at
        """)

        if self.dry_run:
            logger.info("Would migrate weekly summaries", count=len(summaries))
            self.stats["weekly_summaries"] = len(summaries)
            return

        async with self.pg_pool.acquire() as conn:
            for ws in summaries:
                try:
                    # Parse week_id (YYYY-Wxx)
                    parts = ws["week_id"].split("-W")
                    year = int(parts[0])
                    week = int(parts[1])

                    # Convert embedding
                    embedding_str = None
                    if ws.get("embedding"):
                        embedding_str = f"[{','.join(str(x) for x in ws['embedding'])}]"

                    await conn.execute(
                        """
                        INSERT INTO weekly_summaries (
                            week_id, year, week, content, key_themes,
                            daily_summary_count, total_interactions,
                            model_used, embedding, generated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, COALESCE($10, NOW()))
                        ON CONFLICT (week_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            key_themes = EXCLUDED.key_themes
                        """,
                        ws["week_id"],
                        year,
                        week,
                        ws.get("content", ""),
                        ws.get("key_themes", []),
                        ws.get("daily_summary_count", 0),
                        ws.get("total_interactions", 0),
                        ws.get("model_used"),
                        embedding_str,
                        ws.get("generated_at"),
                    )
                    self.stats["weekly_summaries"] += 1
                except Exception as e:
                    logger.error("Failed to migrate weekly summary", week_id=ws.get("week_id"), error=str(e))

        logger.info("Weekly summaries migrated", count=self.stats["weekly_summaries"])

    async def migrate_monthly_summaries(self):
        """Migrate MonthlySummary nodes."""
        logger.info("Migrating monthly summaries...")

        summaries = await self.neo4j_query("""
            MATCH (ms:MonthlySummary)
            RETURN ms.month_id AS month_id,
                   ms.content AS content,
                   ms.key_themes AS key_themes,
                   ms.weekly_summary_count AS weekly_summary_count,
                   ms.total_interactions AS total_interactions,
                   ms.model_used AS model_used,
                   ms.embedding AS embedding,
                   ms.generated_at AS generated_at
        """)

        if self.dry_run:
            logger.info("Would migrate monthly summaries", count=len(summaries))
            self.stats["monthly_summaries"] = len(summaries)
            return

        async with self.pg_pool.acquire() as conn:
            for ms in summaries:
                try:
                    # Parse month_id (YYYY-M)
                    parts = ms["month_id"].split("-")
                    year = int(parts[0])
                    month = int(parts[1])

                    # Convert embedding
                    embedding_str = None
                    if ms.get("embedding"):
                        embedding_str = f"[{','.join(str(x) for x in ms['embedding'])}]"

                    await conn.execute(
                        """
                        INSERT INTO monthly_summaries (
                            month_id, year, month, content, key_themes,
                            weekly_summary_count, total_interactions,
                            model_used, embedding, generated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, COALESCE($10, NOW()))
                        ON CONFLICT (month_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            key_themes = EXCLUDED.key_themes
                        """,
                        ms["month_id"],
                        year,
                        month,
                        ms.get("content", ""),
                        ms.get("key_themes", []),
                        ms.get("weekly_summary_count", 0),
                        ms.get("total_interactions", 0),
                        ms.get("model_used"),
                        embedding_str,
                        ms.get("generated_at"),
                    )
                    self.stats["monthly_summaries"] += 1
                except Exception as e:
                    logger.error("Failed to migrate monthly summary", month_id=ms.get("month_id"), error=str(e))

        logger.info("Monthly summaries migrated", count=self.stats["monthly_summaries"])

    async def migrate_code_changes(self):
        """Migrate CodeChange nodes."""
        logger.info("Migrating code changes...")

        changes = await self.neo4j_query("""
            MATCH (cc:CodeChange)
            OPTIONAL MATCH (cc)-[:OCCURRED_ON]->(d:Day)
            OPTIONAL MATCH (u:User)-[:MADE_CHANGE]->(cc)
            OPTIONAL MATCH (cc)-[:TRIGGERED_BY]->(i:Interaction)
            RETURN cc.id AS id,
                   u.id AS user_id,
                   d.date AS date,
                   cc.timestamp AS timestamp,
                   cc.files_modified AS files_modified,
                   cc.description AS description,
                   cc.reasoning AS reasoning,
                   cc.change_type AS change_type,
                   cc.commit_sha AS commit_sha,
                   i.id AS related_interaction_id
        """)

        if self.dry_run:
            logger.info("Would migrate code changes", count=len(changes))
            self.stats["code_changes"] = len(changes)
            return

        async with self.pg_pool.acquire() as conn:
            for cc in changes:
                try:
                    # Parse date
                    date_val = None
                    if cc.get("date"):
                        date_val = date.fromisoformat(cc["date"])

                    await conn.execute(
                        """
                        INSERT INTO code_changes (
                            id, user_id, date, timestamp, files_modified,
                            description, reasoning, change_type, commit_sha,
                            related_interaction_id
                        )
                        VALUES ($1, $2, $3, COALESCE($4, NOW()), $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        cc["id"],
                        cc.get("user_id"),
                        date_val,
                        cc.get("timestamp"),
                        cc.get("files_modified", []),
                        cc.get("description", ""),
                        cc.get("reasoning"),
                        cc.get("change_type"),
                        cc.get("commit_sha"),
                        cc.get("related_interaction_id"),
                    )
                    self.stats["code_changes"] += 1
                except Exception as e:
                    logger.error("Failed to migrate code change", id=cc.get("id"), error=str(e))

        logger.info("Code changes migrated", count=self.stats["code_changes"])

    async def migrate_code_change_concepts(self):
        """Migrate MODIFIES_CONCEPT relationships."""
        logger.info("Migrating code change-concept relationships...")

        rels = await self.neo4j_query("""
            MATCH (cc:CodeChange)-[:MODIFIES_CONCEPT]->(c:Concept)
            RETURN cc.id AS change_id, c.name AS concept_name
        """)

        if self.dry_run:
            logger.info("Would migrate code change-concept relationships", count=len(rels))
            self.stats["code_change_concepts"] = len(rels)
            return

        async with self.pg_pool.acquire() as conn:
            for rel in rels:
                try:
                    # Get concept ID
                    concept_id = await conn.fetchval(
                        "SELECT id FROM concepts WHERE name = $1",
                        rel["concept_name"],
                    )
                    if concept_id:
                        await conn.execute(
                            """
                            INSERT INTO code_change_concepts (change_id, concept_id)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            rel["change_id"],
                            concept_id,
                        )
                        self.stats["code_change_concepts"] += 1
                except Exception as e:
                    logger.error(
                        "Failed to migrate code change-concept",
                        change=rel.get("change_id"),
                        error=str(e),
                    )

        logger.info("Code change-concept relationships migrated", count=self.stats["code_change_concepts"])

    async def verify_migration(self):
        """Verify the migration by comparing counts."""
        logger.info("Verifying migration...")

        # Get Neo4j counts
        neo4j_counts = {}
        for label in ["User", "Day", "Interaction", "Concept", "DailySummary", "WeeklySummary", "MonthlySummary", "CodeChange"]:
            result = await self.neo4j_query(f"MATCH (n:{label}) RETURN count(n) AS count")
            neo4j_counts[label] = result[0]["count"] if result else 0

        # Get PostgreSQL counts
        pg_counts = {}
        async with self.pg_pool.acquire() as conn:
            for table in ["users", "days", "interactions", "concepts", "daily_summaries", "weekly_summaries", "monthly_summaries", "code_changes"]:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                pg_counts[table] = count

        # Compare
        mapping = {
            "User": "users",
            "Day": "days",
            "Interaction": "interactions",
            "Concept": "concepts",
            "DailySummary": "daily_summaries",
            "WeeklySummary": "weekly_summaries",
            "MonthlySummary": "monthly_summaries",
            "CodeChange": "code_changes",
        }

        all_match = True
        for neo4j_label, pg_table in mapping.items():
            neo4j_count = neo4j_counts.get(neo4j_label, 0)
            pg_count = pg_counts.get(pg_table, 0)
            match = "✓" if neo4j_count == pg_count else "✗"
            if neo4j_count != pg_count:
                all_match = False
            logger.info(
                f"{match} {neo4j_label}/{pg_table}",
                neo4j=neo4j_count,
                postgres=pg_count,
            )

        return all_match

    async def run(self, only: list[str] | None = None):
        """Run the full migration."""
        try:
            await self.connect()

            # Define migration order
            migrations = [
                ("users", self.migrate_users),
                ("days", self.migrate_days),
                ("interactions", self.migrate_interactions),
                ("concepts", self.migrate_concepts),
                ("interaction_concepts", self.migrate_interaction_concepts),
                ("daily_summaries", self.migrate_daily_summaries),
                ("weekly_summaries", self.migrate_weekly_summaries),
                ("monthly_summaries", self.migrate_monthly_summaries),
                ("code_changes", self.migrate_code_changes),
                ("code_change_concepts", self.migrate_code_change_concepts),
            ]

            # Filter if only specific tables requested
            if only:
                migrations = [(name, func) for name, func in migrations if name in only]

            # Run migrations
            for name, migrate_func in migrations:
                await migrate_func()

            # Print summary
            logger.info("=" * 50)
            logger.info("Migration Summary")
            logger.info("=" * 50)
            for key, value in self.stats.items():
                logger.info(f"  {key}: {value}")

            # Verify
            if not self.dry_run:
                logger.info("=" * 50)
                all_match = await self.verify_migration()
                if all_match:
                    logger.info("Migration verification: SUCCESS")
                else:
                    logger.warning("Migration verification: MISMATCH (some counts differ)")

        finally:
            await self.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate Neo4j to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    parser.add_argument("--only", type=str, help="Only migrate specific tables (comma-separated)")
    parser.add_argument("--neo4j-uri", type=str, help="Neo4j URI")
    parser.add_argument("--neo4j-user", type=str, default="neo4j", help="Neo4j username")
    parser.add_argument("--neo4j-password", type=str, help="Neo4j password")
    parser.add_argument("--neo4j-database", type=str, default="neo4j", help="Neo4j database")
    parser.add_argument("--postgres-uri", type=str, help="PostgreSQL URI")
    args = parser.parse_args()

    # Get credentials from args or environment
    import os
    neo4j_uri = args.neo4j_uri or os.environ.get("NEO4J_URI")
    neo4j_user = args.neo4j_user or os.environ.get("NEO4J_USERNAME", "neo4j")
    neo4j_password = args.neo4j_password or os.environ.get("NEO4J_PASSWORD")
    neo4j_database = args.neo4j_database or os.environ.get("NEO4J_DATABASE", "neo4j")
    postgres_uri = args.postgres_uri or os.environ.get("POSTGRES_URI")

    # Validate
    if not neo4j_uri or not neo4j_password:
        logger.error("Missing Neo4j credentials. Set NEO4J_URI and NEO4J_PASSWORD environment variables.")
        sys.exit(1)
    if not postgres_uri:
        logger.error("Missing PostgreSQL URI. Set POSTGRES_URI environment variable.")
        sys.exit(1)

    # Parse --only
    only = None
    if args.only:
        only = [x.strip() for x in args.only.split(",")]

    # Run migration
    migrator = Neo4jToPostgresMigrator(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        neo4j_database=neo4j_database,
        postgres_uri=postgres_uri,
    )
    migrator.dry_run = args.dry_run

    if args.dry_run:
        logger.info("DRY RUN - No changes will be made")

    await migrator.run(only=only)


if __name__ == "__main__":
    asyncio.run(main())
