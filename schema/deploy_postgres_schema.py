#!/usr/bin/env python3
"""
Deploy PostgreSQL schema for Alex AI Assistant.

This script creates all required tables, indexes, and extensions
for the PostgreSQL-based memory system.

Usage:
    # Set environment variable
    export POSTGRES_URI="postgresql://user:pass@host:5432/alex"

    # Deploy schema
    python schema/deploy_postgres_schema.py

    # Deploy with verbose output
    python schema/deploy_postgres_schema.py --verbose
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


async def deploy_schema(postgres_uri: str, verbose: bool = False):
    """Deploy the PostgreSQL schema."""
    logger.info("Connecting to PostgreSQL...")

    conn = await asyncpg.connect(postgres_uri)

    try:
        # Read schema file
        schema_path = Path(__file__).parent / "postgres_schema.sql"
        if not schema_path.exists():
            logger.error("Schema file not found", path=str(schema_path))
            sys.exit(1)

        schema_sql = schema_path.read_text()

        logger.info("Deploying schema...")

        # Split into individual statements and execute
        # (asyncpg doesn't support multiple statements in one execute)
        statements = []
        current_statement = []
        in_function = False

        for line in schema_sql.split("\n"):
            stripped = line.strip()

            # Skip empty lines and comments at statement boundaries
            if not stripped or stripped.startswith("--"):
                if current_statement:
                    current_statement.append(line)
                continue

            current_statement.append(line)

            # Track function/trigger definitions (they can contain semicolons)
            if "CREATE OR REPLACE FUNCTION" in line.upper() or "CREATE FUNCTION" in line.upper():
                in_function = True
            if in_function and "$$" in line and current_statement.count("$$") >= 2:
                in_function = False

            # Statement ends with semicolon (not inside function)
            if stripped.endswith(";") and not in_function:
                statement = "\n".join(current_statement).strip()
                if statement and not statement.startswith("--"):
                    statements.append(statement)
                current_statement = []

        # Execute each statement
        success_count = 0
        error_count = 0

        for i, statement in enumerate(statements, 1):
            try:
                # Skip empty statements
                if not statement.strip() or statement.strip() == ";":
                    continue

                # Extract first line for logging
                first_line = statement.split("\n")[0][:60]
                if verbose:
                    logger.info(f"Executing [{i}/{len(statements)}]", statement=first_line)

                await conn.execute(statement)
                success_count += 1

            except Exception as e:
                error_msg = str(e)
                # Some errors are expected (e.g., extension already exists)
                if "already exists" in error_msg.lower():
                    if verbose:
                        logger.info("Skipped (already exists)", statement=first_line[:40])
                    success_count += 1
                else:
                    logger.error("Failed to execute", statement=first_line[:40], error=error_msg)
                    error_count += 1

        logger.info(
            "Schema deployment complete",
            success=success_count,
            errors=error_count,
            total=len(statements),
        )

        # Verify tables exist
        logger.info("Verifying tables...")
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        expected_tables = [
            "code_change_concepts",
            "code_changes",
            "concepts",
            "daily_summaries",
            "days",
            "interaction_concepts",
            "interactions",
            "monthly_summaries",
            "projects",
            "users",
            "weekly_summaries",
        ]

        existing_tables = [t["table_name"] for t in tables]
        missing_tables = [t for t in expected_tables if t not in existing_tables]

        if missing_tables:
            logger.warning("Missing tables", tables=missing_tables)
        else:
            logger.info("All expected tables exist", count=len(expected_tables))

        # Verify pgvector extension
        pgvector = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        if pgvector:
            logger.info("pgvector extension installed", version=pgvector)
        else:
            logger.warning("pgvector extension not found!")

        # Verify indexes
        indexes = await conn.fetch("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            ORDER BY indexname
        """)
        logger.info("Custom indexes created", count=len(indexes))

        if error_count > 0:
            logger.warning("Schema deployed with errors", error_count=error_count)
            return False

        logger.info("Schema deployment successful!")
        return True

    finally:
        await conn.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Deploy PostgreSQL schema")
    parser.add_argument("--postgres-uri", type=str, help="PostgreSQL URI")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    postgres_uri = args.postgres_uri or os.environ.get("POSTGRES_URI")

    if not postgres_uri:
        logger.error("Missing PostgreSQL URI. Set POSTGRES_URI environment variable.")
        sys.exit(1)

    success = await deploy_schema(postgres_uri, verbose=args.verbose)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
