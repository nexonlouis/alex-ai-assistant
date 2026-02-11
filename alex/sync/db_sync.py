"""
Database synchronization from local PostgreSQL to remote Neon.

Performs incremental sync based on timestamps, tracking the last sync
time to avoid re-syncing old data.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import structlog
from dotenv import load_dotenv

# Load .env file from project root
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")

logger = structlog.get_logger()

# Sync state file location
SYNC_STATE_DIR = Path.home() / ".alex"
SYNC_STATE_FILE = SYNC_STATE_DIR / "sync_state.json"


def _load_sync_state() -> dict[str, Any]:
    """Load sync state from file."""
    if not SYNC_STATE_FILE.exists():
        return {"last_sync": None, "sync_count": 0}

    try:
        with open(SYNC_STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"last_sync": None, "sync_count": 0}


def _save_sync_state(state: dict[str, Any]):
    """Save sync state to file."""
    SYNC_STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYNC_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.chmod(SYNC_STATE_FILE, 0o600)


def get_sync_status() -> dict[str, Any]:
    """Get current sync status."""
    state = _load_sync_state()
    return {
        "last_sync": state.get("last_sync"),
        "sync_count": state.get("sync_count", 0),
        "state_file": str(SYNC_STATE_FILE),
    }


def reset_sync_state():
    """Reset sync state to force full sync on next run."""
    _save_sync_state({"last_sync": None, "sync_count": 0})
    logger.info("Sync state reset")


async def _sync_table(
    local_conn: asyncpg.Connection,
    remote_conn: asyncpg.Connection,
    table: str,
    id_column: str,
    timestamp_column: str | None,
    last_sync: datetime | None,
    columns: list[str],
    conflict_columns: list[str] | None = None,
) -> int:
    """
    Sync a single table from local to remote.

    Args:
        local_conn: Local database connection
        remote_conn: Remote database connection
        table: Table name
        id_column: Primary key column name
        timestamp_column: Column to filter by for incremental sync (or None for full)
        last_sync: Last sync timestamp
        columns: List of columns to sync
        conflict_columns: Columns for ON CONFLICT clause (defaults to id_column)

    Returns:
        Number of rows synced
    """
    # Build query
    if timestamp_column and last_sync:
        query = f"SELECT {', '.join(columns)} FROM {table} WHERE {timestamp_column} > $1"
        rows = await local_conn.fetch(query, last_sync)
    else:
        query = f"SELECT {', '.join(columns)} FROM {table}"
        rows = await local_conn.fetch(query)

    if not rows:
        return 0

    # Build upsert statement
    conflict_cols = conflict_columns or [id_column]
    placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
    update_cols = [c for c in columns if c not in conflict_cols]

    if update_cols:
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        upsert = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT ({', '.join(conflict_cols)}) DO UPDATE SET {update_clause}
        """
    else:
        upsert = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT ({', '.join(conflict_cols)}) DO NOTHING
        """

    # Execute upserts
    synced = 0
    for row in rows:
        try:
            await remote_conn.execute(upsert, *[row[c] for c in columns])
            synced += 1
        except Exception as e:
            logger.warning(f"Failed to sync row in {table}", error=str(e), id=row.get(id_column))

    return synced


async def sync_to_remote(
    local_uri: str | None = None,
    remote_uri: str | None = None,
    force_full: bool = False,
) -> dict[str, Any]:
    """
    Sync local database to remote Neon database.

    Args:
        local_uri: Local PostgreSQL URI (defaults to localhost)
        remote_uri: Remote Neon URI (from environment or settings)
        force_full: If True, sync all data regardless of last sync time

    Returns:
        Sync results with counts per table
    """
    # Get URIs
    if not local_uri:
        local_uri = os.environ.get("LOCAL_POSTGRES_URI", "postgresql://localhost:5432/alex")

    if not remote_uri:
        remote_uri = os.environ.get("REMOTE_POSTGRES_URI")
        if not remote_uri:
            # Try to load from .env
            from alex.config import settings
            remote_uri = os.environ.get("NEON_POSTGRES_URI") or settings.postgres_uri

    if not remote_uri or "localhost" in remote_uri:
        raise ValueError(
            "Remote database URI not configured. "
            "Set REMOTE_POSTGRES_URI or NEON_POSTGRES_URI environment variable."
        )

    # Load sync state
    state = _load_sync_state()
    last_sync = None
    if not force_full and state.get("last_sync"):
        last_sync = datetime.fromisoformat(state["last_sync"])

    sync_start = datetime.now(timezone.utc)
    results = {"tables": {}, "total_synced": 0, "errors": []}

    logger.info(
        "Starting database sync",
        last_sync=last_sync,
        force_full=force_full,
    )

    try:
        # Connect to both databases
        local_conn = await asyncpg.connect(local_uri)
        remote_conn = await asyncpg.connect(remote_uri)

        try:
            # Sync tables in dependency order

            # 1. Users (no timestamp, sync all)
            count = await _sync_table(
                local_conn, remote_conn,
                table="users",
                id_column="id",
                timestamp_column="created_at",
                last_sync=last_sync,
                columns=["id", "created_at", "updated_at"],
            )
            results["tables"]["users"] = count
            results["total_synced"] += count

            # 2. Days (no timestamp dependency, sync all new)
            count = await _sync_table(
                local_conn, remote_conn,
                table="days",
                id_column="date",
                timestamp_column="created_at",
                last_sync=last_sync,
                columns=["date", "year", "month", "day", "week_number", "day_of_week", "created_at"],
            )
            results["tables"]["days"] = count
            results["total_synced"] += count

            # 3. Concepts
            count = await _sync_table(
                local_conn, remote_conn,
                table="concepts",
                id_column="id",
                timestamp_column="first_mentioned",
                last_sync=last_sync,
                columns=["id", "name", "normalized_name", "first_mentioned", "mention_count"],
            )
            results["tables"]["concepts"] = count
            results["total_synced"] += count

            # 4. Projects
            count = await _sync_table(
                local_conn, remote_conn,
                table="projects",
                id_column="id",
                timestamp_column="created_at",
                last_sync=last_sync,
                columns=["id", "name", "description", "created_at"],
            )
            results["tables"]["projects"] = count
            results["total_synced"] += count

            # 5. Interactions (main data)
            count = await _sync_table(
                local_conn, remote_conn,
                table="interactions",
                id_column="id",
                timestamp_column="created_at",
                last_sync=last_sync,
                columns=[
                    "id", "user_id", "date", "timestamp", "user_message",
                    "assistant_response", "intent", "complexity_score",
                    "model_used", "embedding", "created_at"
                ],
            )
            results["tables"]["interactions"] = count
            results["total_synced"] += count

            # 6. Interaction-Concepts junction
            # For junction tables, we need to sync based on interaction timestamps
            if last_sync:
                query = """
                    SELECT ic.interaction_id, ic.concept_id
                    FROM interaction_concepts ic
                    JOIN interactions i ON ic.interaction_id = i.id
                    WHERE i.created_at > $1
                """
                rows = await local_conn.fetch(query, last_sync)
            else:
                rows = await local_conn.fetch("SELECT interaction_id, concept_id FROM interaction_concepts")

            junction_count = 0
            for row in rows:
                try:
                    await remote_conn.execute(
                        """
                        INSERT INTO interaction_concepts (interaction_id, concept_id)
                        VALUES ($1, $2)
                        ON CONFLICT (interaction_id, concept_id) DO NOTHING
                        """,
                        row["interaction_id"], row["concept_id"]
                    )
                    junction_count += 1
                except Exception as e:
                    logger.warning("Failed to sync interaction_concept", error=str(e))
            results["tables"]["interaction_concepts"] = junction_count
            results["total_synced"] += junction_count

            # 7. Daily Summaries
            count = await _sync_table(
                local_conn, remote_conn,
                table="daily_summaries",
                id_column="date",
                timestamp_column="generated_at",
                last_sync=last_sync,
                columns=[
                    "date", "content", "key_topics", "interaction_count",
                    "model_used", "embedding", "generated_at"
                ],
            )
            results["tables"]["daily_summaries"] = count
            results["total_synced"] += count

            # 8. Weekly Summaries
            count = await _sync_table(
                local_conn, remote_conn,
                table="weekly_summaries",
                id_column="week_id",
                timestamp_column="generated_at",
                last_sync=last_sync,
                columns=[
                    "week_id", "year", "week", "content", "key_themes",
                    "daily_summary_count", "total_interactions",
                    "model_used", "embedding", "generated_at"
                ],
            )
            results["tables"]["weekly_summaries"] = count
            results["total_synced"] += count

            # 9. Monthly Summaries
            count = await _sync_table(
                local_conn, remote_conn,
                table="monthly_summaries",
                id_column="month_id",
                timestamp_column="generated_at",
                last_sync=last_sync,
                columns=[
                    "month_id", "year", "month", "content", "key_themes",
                    "weekly_summary_count", "total_interactions",
                    "model_used", "embedding", "generated_at"
                ],
            )
            results["tables"]["monthly_summaries"] = count
            results["total_synced"] += count

            # 10. Code Changes
            count = await _sync_table(
                local_conn, remote_conn,
                table="code_changes",
                id_column="id",
                timestamp_column="timestamp",
                last_sync=last_sync,
                columns=[
                    "id", "user_id", "date", "timestamp", "files_modified",
                    "description", "reasoning", "change_type", "commit_sha",
                    "related_interaction_id"
                ],
            )
            results["tables"]["code_changes"] = count
            results["total_synced"] += count

            # 11. Code Change Concepts junction
            if last_sync:
                query = """
                    SELECT cc.change_id, cc.concept_id
                    FROM code_change_concepts cc
                    JOIN code_changes c ON cc.change_id = c.id
                    WHERE c.timestamp > $1
                """
                rows = await local_conn.fetch(query, last_sync)
            else:
                rows = await local_conn.fetch("SELECT change_id, concept_id FROM code_change_concepts")

            junction_count = 0
            for row in rows:
                try:
                    await remote_conn.execute(
                        """
                        INSERT INTO code_change_concepts (change_id, concept_id)
                        VALUES ($1, $2)
                        ON CONFLICT (change_id, concept_id) DO NOTHING
                        """,
                        row["change_id"], row["concept_id"]
                    )
                    junction_count += 1
                except Exception as e:
                    logger.warning("Failed to sync code_change_concept", error=str(e))
            results["tables"]["code_change_concepts"] = junction_count
            results["total_synced"] += junction_count

            # 12. Trades
            count = await _sync_table(
                local_conn, remote_conn,
                table="trades",
                id_column="id",
                timestamp_column="created_at",
                last_sync=last_sync,
                columns=[
                    "id", "user_id", "date", "timestamp", "symbol", "action",
                    "quantity", "order_id", "status", "order_type", "price",
                    "instrument_type", "option_symbol", "account_number",
                    "mode", "related_interaction_id", "created_at"
                ],
            )
            results["tables"]["trades"] = count
            results["total_synced"] += count

        finally:
            await local_conn.close()
            await remote_conn.close()

        # Update sync state
        new_state = {
            "last_sync": sync_start.isoformat(),
            "sync_count": state.get("sync_count", 0) + 1,
            "last_result": results,
        }
        _save_sync_state(new_state)

        logger.info(
            "Database sync complete",
            total_synced=results["total_synced"],
            tables=results["tables"],
        )

        results["success"] = True
        results["sync_time"] = sync_start.isoformat()

    except Exception as e:
        logger.error("Database sync failed", error=str(e))
        results["success"] = False
        results["error"] = str(e)

    return results


async def main():
    """CLI entry point for sync."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync local Alex database to remote Neon")
    parser.add_argument("--force-full", action="store_true", help="Force full sync (ignore last sync time)")
    parser.add_argument("--status", action="store_true", help="Show sync status")
    parser.add_argument("--reset", action="store_true", help="Reset sync state")
    parser.add_argument("--local-uri", help="Local PostgreSQL URI")
    parser.add_argument("--remote-uri", help="Remote Neon URI")

    args = parser.parse_args()

    if args.status:
        status = get_sync_status()
        print(f"Last sync: {status['last_sync'] or 'Never'}")
        print(f"Sync count: {status['sync_count']}")
        print(f"State file: {status['state_file']}")
        return

    if args.reset:
        reset_sync_state()
        print("Sync state reset. Next sync will be a full sync.")
        return

    # Run sync
    results = await sync_to_remote(
        local_uri=args.local_uri,
        remote_uri=args.remote_uri,
        force_full=args.force_full,
    )

    if results.get("success"):
        print(f"✓ Sync complete: {results['total_synced']} records synced")
        for table, count in results.get("tables", {}).items():
            if count > 0:
                print(f"  - {table}: {count}")
    else:
        print(f"✗ Sync failed: {results.get('error')}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
