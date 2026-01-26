#!/usr/bin/env python3
"""
Update Neo4j vector indexes to 768 dimensions for Gemini embeddings.
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from alex.memory.graph_store import GraphStore


async def update_vector_indexes():
    """Update vector indexes to 768 dimensions."""
    graph_store = GraphStore()

    print("Updating Neo4j vector indexes to 768 dimensions...")

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
        print("\nDropping existing vector indexes...")
        for idx_name, _, _ in indexes:
            try:
                await session.run(f"DROP INDEX {idx_name} IF EXISTS")
                print(f"  Dropped: {idx_name}")
            except Exception as e:
                print(f"  Skip {idx_name}: {e}")

        # Create new indexes with 768 dimensions
        print("\nCreating vector indexes with 768 dimensions...")
        for idx_name, label, prop in indexes:
            query = f"""
            CREATE VECTOR INDEX {idx_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{prop})
            OPTIONS {{indexConfig: {{`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}}}
            """
            try:
                await session.run(query)
                print(f"  Created: {idx_name}")
            except Exception as e:
                print(f"  Error creating {idx_name}: {e}")

        # Verify indexes
        print("\nVerifying indexes...")
        result = await session.run("""
            SHOW INDEXES
            WHERE type = 'VECTOR'
            RETURN name, labelsOrTypes, properties, options
        """)
        records = await result.data()

        for record in records:
            dims = record.get('options', {}).get('indexConfig', {}).get('vector.dimensions', 'unknown')
            print(f"  {record['name']}: {dims} dimensions")

    await GraphStore.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(update_vector_indexes())
