#!/usr/bin/env python3
"""
Direct Neo4j Schema Deployment for Alex AI Assistant
Deploys schema in logical sections with proper error handling.
"""

import os
import sys
from pathlib import Path

try:
    from neo4j import GraphDatabase
    from dotenv import load_dotenv
except ImportError:
    print("Installing required packages...")
    os.system("pip install neo4j python-dotenv --quiet")
    from neo4j import GraphDatabase
    from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

print(f"Connecting to: {URI}")
print(f"Database: {DATABASE}")

# Schema sections as individual statements
CONSTRAINTS = [
    # Time Tree
    "CREATE CONSTRAINT constraint_year_unique IF NOT EXISTS FOR (y:Year) REQUIRE y.year IS UNIQUE",
    "CREATE CONSTRAINT constraint_month_unique IF NOT EXISTS FOR (m:Month) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_week_unique IF NOT EXISTS FOR (w:Week) REQUIRE w.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_day_unique IF NOT EXISTS FOR (d:Day) REQUIRE d.date IS UNIQUE",
    # User & Interaction
    "CREATE CONSTRAINT constraint_user_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_interaction_unique IF NOT EXISTS FOR (i:Interaction) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_conversation_unique IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
    # Summaries
    "CREATE CONSTRAINT constraint_daily_summary_unique IF NOT EXISTS FOR (ds:DailySummary) REQUIRE ds.date IS UNIQUE",
    "CREATE CONSTRAINT constraint_weekly_summary_unique IF NOT EXISTS FOR (ws:WeeklySummary) REQUIRE ws.week_id IS UNIQUE",
    "CREATE CONSTRAINT constraint_monthly_summary_unique IF NOT EXISTS FOR (ms:MonthlySummary) REQUIRE ms.month_id IS UNIQUE",
    "CREATE CONSTRAINT constraint_annual_summary_unique IF NOT EXISTS FOR (ans:AnnualSummary) REQUIRE ans.year IS UNIQUE",
    # Self-Knowledge
    "CREATE CONSTRAINT constraint_module_unique IF NOT EXISTS FOR (mod:Module) REQUIRE mod.path IS UNIQUE",
    "CREATE CONSTRAINT constraint_class_unique IF NOT EXISTS FOR (cls:Class) REQUIRE cls.fqn IS UNIQUE",
    "CREATE CONSTRAINT constraint_method_unique IF NOT EXISTS FOR (m:Method) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_function_unique IF NOT EXISTS FOR (f:Function) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_file_unique IF NOT EXISTS FOR (file:File) REQUIRE file.path IS UNIQUE",
    "CREATE CONSTRAINT constraint_commit_unique IF NOT EXISTS FOR (commit:Commit) REQUIRE commit.hash IS UNIQUE",
    # Concepts
    "CREATE CONSTRAINT constraint_concept_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT constraint_topic_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT constraint_project_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_person_unique IF NOT EXISTS FOR (person:Person) REQUIRE person.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_entity_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_tag_unique IF NOT EXISTS FOR (tag:Tag) REQUIRE tag.name IS UNIQUE",
]

INDEXES = [
    # Time Tree
    "CREATE INDEX index_year_value IF NOT EXISTS FOR (y:Year) ON (y.year)",
    "CREATE INDEX index_month_number IF NOT EXISTS FOR (m:Month) ON (m.month)",
    "CREATE INDEX index_month_year IF NOT EXISTS FOR (m:Month) ON (m.year)",
    "CREATE INDEX index_week_number IF NOT EXISTS FOR (w:Week) ON (w.week)",
    "CREATE INDEX index_week_year IF NOT EXISTS FOR (w:Week) ON (w.year)",
    "CREATE INDEX index_day_dow IF NOT EXISTS FOR (d:Day) ON (d.day_of_week)",
    "CREATE INDEX index_day_timestamp IF NOT EXISTS FOR (d:Day) ON (d.timestamp)",
    # Interaction
    "CREATE INDEX index_interaction_timestamp IF NOT EXISTS FOR (i:Interaction) ON (i.timestamp)",
    "CREATE INDEX index_interaction_type IF NOT EXISTS FOR (i:Interaction) ON (i.type)",
    "CREATE INDEX index_interaction_intent IF NOT EXISTS FOR (i:Interaction) ON (i.intent)",
    "CREATE INDEX index_interaction_user IF NOT EXISTS FOR (i:Interaction) ON (i.user_id)",
    "CREATE INDEX index_conversation_timestamp IF NOT EXISTS FOR (c:Conversation) ON (c.started_at)",
    "CREATE INDEX index_conversation_status IF NOT EXISTS FOR (c:Conversation) ON (c.status)",
    # Summary
    "CREATE INDEX index_daily_summary_status IF NOT EXISTS FOR (ds:DailySummary) ON (ds.status)",
    "CREATE INDEX index_daily_summary_generated IF NOT EXISTS FOR (ds:DailySummary) ON (ds.generated_at)",
    "CREATE INDEX index_weekly_summary_status IF NOT EXISTS FOR (ws:WeeklySummary) ON (ws.status)",
    "CREATE INDEX index_monthly_summary_status IF NOT EXISTS FOR (ms:MonthlySummary) ON (ms.status)",
    # Self-Knowledge
    "CREATE INDEX index_module_name IF NOT EXISTS FOR (mod:Module) ON (mod.name)",
    "CREATE INDEX index_class_name IF NOT EXISTS FOR (cls:Class) ON (cls.name)",
    "CREATE INDEX index_method_name IF NOT EXISTS FOR (m:Method) ON (m.name)",
    "CREATE INDEX index_function_name IF NOT EXISTS FOR (f:Function) ON (f.name)",
    "CREATE INDEX index_file_extension IF NOT EXISTS FOR (file:File) ON (file.extension)",
    "CREATE INDEX index_commit_timestamp IF NOT EXISTS FOR (commit:Commit) ON (commit.timestamp)",
    # Concepts
    "CREATE INDEX index_concept_category IF NOT EXISTS FOR (c:Concept) ON (c.category)",
    "CREATE INDEX index_concept_mention_count IF NOT EXISTS FOR (c:Concept) ON (c.mention_count)",
    "CREATE INDEX index_topic_relevance IF NOT EXISTS FOR (t:Topic) ON (t.relevance_score)",
    "CREATE INDEX index_project_status IF NOT EXISTS FOR (p:Project) ON (p.status)",
    "CREATE INDEX index_person_type IF NOT EXISTS FOR (person:Person) ON (person.type)",
    "CREATE INDEX index_entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
    "CREATE INDEX index_tag_usage IF NOT EXISTS FOR (tag:Tag) ON (tag.usage_count)",
]

VECTOR_INDEXES = [
    "CREATE VECTOR INDEX vector_index_interaction IF NOT EXISTS FOR (i:Interaction) ON (i.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_daily_summary IF NOT EXISTS FOR (ds:DailySummary) ON (ds.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_weekly_summary IF NOT EXISTS FOR (ws:WeeklySummary) ON (ws.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_monthly_summary IF NOT EXISTS FOR (ms:MonthlySummary) ON (ms.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_annual_summary IF NOT EXISTS FOR (ans:AnnualSummary) ON (ans.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_concept IF NOT EXISTS FOR (c:Concept) ON (c.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_topic IF NOT EXISTS FOR (t:Topic) ON (t.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_project IF NOT EXISTS FOR (p:Project) ON (p.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_module IF NOT EXISTS FOR (mod:Module) ON (mod.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_class IF NOT EXISTS FOR (cls:Class) ON (cls.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX vector_index_method IF NOT EXISTS FOR (m:Method) ON (m.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
]

FULLTEXT_INDEXES = [
    "CREATE FULLTEXT INDEX fulltext_interaction_content IF NOT EXISTS FOR (i:Interaction) ON EACH [i.user_message, i.assistant_response]",
    "CREATE FULLTEXT INDEX fulltext_daily_summary IF NOT EXISTS FOR (ds:DailySummary) ON EACH [ds.content]",
    "CREATE FULLTEXT INDEX fulltext_weekly_summary IF NOT EXISTS FOR (ws:WeeklySummary) ON EACH [ws.content]",
    "CREATE FULLTEXT INDEX fulltext_module_docs IF NOT EXISTS FOR (mod:Module) ON EACH [mod.docstring, mod.name]",
    "CREATE FULLTEXT INDEX fulltext_class_docs IF NOT EXISTS FOR (cls:Class) ON EACH [cls.docstring, cls.name]",
    "CREATE FULLTEXT INDEX fulltext_method_docs IF NOT EXISTS FOR (m:Method) ON EACH [m.docstring, m.name]",
    "CREATE FULLTEXT INDEX fulltext_concepts IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.description]",
    "CREATE FULLTEXT INDEX fulltext_topics IF NOT EXISTS FOR (t:Topic) ON EACH [t.name, t.description]",
    "CREATE FULLTEXT INDEX fulltext_projects IF NOT EXISTS FOR (p:Project) ON EACH [p.name, p.description]",
]

TIME_TREE_SETUP = [
    # Years
    "MERGE (y:Year {year: 2025}) SET y.created_at = datetime(), y.label = '2025'",
    "MERGE (y:Year {year: 2026}) SET y.created_at = datetime(), y.label = '2026'",
]

# Generate months
for year in [2025, 2026]:
    for month in range(1, 13):
        month_names = ["", "January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        TIME_TREE_SETUP.append(
            f"MERGE (m:Month {{id: '{year}-{month}'}}) "
            f"SET m.month = {month}, m.year = {year}, m.name = '{month_names[month]}', m.created_at = datetime() "
            f"WITH m MATCH (y:Year {{year: {year}}}) MERGE (y)-[:HAS_MONTH]->(m)"
        )

# Generate weeks
for year in [2025, 2026]:
    for week in range(1, 53):
        week_str = f"{week:02d}"
        TIME_TREE_SETUP.append(
            f"MERGE (w:Week {{id: '{year}-W{week_str}'}}) "
            f"SET w.week = {week}, w.year = {year}, w.created_at = datetime() "
            f"WITH w MATCH (y:Year {{year: {year}}}) MERGE (y)-[:HAS_WEEK]->(w)"
        )

# Days generation query (single query per year for efficiency)
DAYS_2025 = """
WITH date('2025-01-01') AS startDate, date('2025-12-31') AS endDate
WITH startDate, duration.inDays(startDate, endDate).days AS totalDays
UNWIND range(0, totalDays) AS dayOffset
WITH startDate + duration({days: dayOffset}) AS currentDate
MERGE (d:Day {date: toString(currentDate)})
SET d.year = currentDate.year,
    d.month = currentDate.month,
    d.day = currentDate.day,
    d.day_of_week = currentDate.dayOfWeek,
    d.day_name = CASE currentDate.dayOfWeek
      WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday' WHEN 3 THEN 'Wednesday'
      WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday' WHEN 6 THEN 'Saturday' WHEN 7 THEN 'Sunday'
    END,
    d.timestamp = datetime({year: currentDate.year, month: currentDate.month, day: currentDate.day}),
    d.week_number = currentDate.week,
    d.created_at = datetime()
WITH d, currentDate
MATCH (m:Month {id: toString(currentDate.year) + '-' + toString(currentDate.month)})
MERGE (m)-[:HAS_DAY]->(d)
WITH d, currentDate
MATCH (w:Week {id: toString(currentDate.year) + '-W' +
  CASE WHEN currentDate.week < 10 THEN '0' + toString(currentDate.week) ELSE toString(currentDate.week) END})
MERGE (w)-[:CONTAINS_DAY]->(d)
"""

DAYS_2026 = """
WITH date('2026-01-01') AS startDate, date('2026-12-31') AS endDate
WITH startDate, duration.inDays(startDate, endDate).days AS totalDays
UNWIND range(0, totalDays) AS dayOffset
WITH startDate + duration({days: dayOffset}) AS currentDate
MERGE (d:Day {date: toString(currentDate)})
SET d.year = currentDate.year,
    d.month = currentDate.month,
    d.day = currentDate.day,
    d.day_of_week = currentDate.dayOfWeek,
    d.day_name = CASE currentDate.dayOfWeek
      WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday' WHEN 3 THEN 'Wednesday'
      WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday' WHEN 6 THEN 'Saturday' WHEN 7 THEN 'Sunday'
    END,
    d.timestamp = datetime({year: currentDate.year, month: currentDate.month, day: currentDate.day}),
    d.week_number = currentDate.week,
    d.created_at = datetime()
WITH d, currentDate
MATCH (m:Month {id: toString(currentDate.year) + '-' + toString(currentDate.month)})
MERGE (m)-[:HAS_DAY]->(d)
WITH d, currentDate
MATCH (w:Week {id: toString(currentDate.year) + '-W' +
  CASE WHEN currentDate.week < 10 THEN '0' + toString(currentDate.week) ELSE toString(currentDate.week) END})
MERGE (w)-[:CONTAINS_DAY]->(d)
"""

NEXT_DAY_LINKS = """
MATCH (d1:Day)
WHERE d1.year IN [2025, 2026]
WITH d1
ORDER BY d1.date
WITH collect(d1) AS days
UNWIND range(0, size(days)-2) AS i
WITH days[i] AS day1, days[i+1] AS day2
MERGE (day1)-[:NEXT_DAY]->(day2)
"""

SEED_DATA = [
    # Primary User
    """MERGE (u:User {id: 'primary_user'})
    SET u.name = 'Primary User',
        u.created_at = datetime(),
        u.timezone = 'UTC',
        u.updated_at = datetime()""",

    # Core Concepts
    """MERGE (c:Concept {name: 'knowledge_graph'}) SET c.normalized_name = 'knowledge_graph', c.category = 'technology', c.description = 'Graph-based data structure for representing knowledge', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'neo4j'}) SET c.normalized_name = 'neo4j', c.category = 'technology', c.description = 'Native graph database platform', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'temporal_reasoning'}) SET c.normalized_name = 'temporal_reasoning', c.category = 'capability', c.description = 'Ability to reason about time-based events', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'recursive_summarization'}) SET c.normalized_name = 'recursive_summarization', c.category = 'algorithm', c.description = 'Hierarchical aggregation of information over time', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'hybrid_retrieval'}) SET c.normalized_name = 'hybrid_retrieval', c.category = 'algorithm', c.description = 'Combining vector similarity with graph traversal', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'langgraph'}) SET c.normalized_name = 'langgraph', c.category = 'technology', c.description = 'Framework for building stateful AI agents', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'gemini'}) SET c.normalized_name = 'gemini', c.category = 'technology', c.description = 'Google multimodal AI model family', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'claude_code'}) SET c.normalized_name = 'claude_code', c.category = 'technology', c.description = 'Anthropic CLI tool for autonomous software engineering', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'mcp_toolbox'}) SET c.normalized_name = 'mcp_toolbox', c.category = 'technology', c.description = 'Model Context Protocol server for database access', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",
    """MERGE (c:Concept {name: 'dual_cortex'}) SET c.normalized_name = 'dual_cortex', c.category = 'architecture', c.description = 'Two-tier AI model architecture for cost-efficiency', c.first_mentioned = datetime(), c.mention_count = 0, c.relevance_score = 0.8""",

    # Alex Project
    """MERGE (p:Project {id: 'proj_alex_core'})
    SET p.name = 'Alex AI Assistant',
        p.description = 'Autonomous, self-reflective AI assistant with temporal knowledge graph memory',
        p.status = 'in_progress',
        p.priority = 'high',
        p.started_at = datetime(),
        p.current_milestone = 'Neo4j Schema Deployment'
    WITH p
    MATCH (d:Day {date: '2026-01-25'})
    MERGE (p)-[:STARTED_ON]->(d)""",
]


def run_section(driver, name: str, statements: list, continue_on_error: bool = False):
    """Execute a section of statements."""
    print(f"\n{'='*60}")
    print(f"SECTION: {name}")
    print(f"{'='*60}")

    success = 0
    errors = []

    with driver.session(database=DATABASE) as session:
        for i, stmt in enumerate(statements, 1):
            try:
                session.run(stmt)
                success += 1
                print(f"  [{i}/{len(statements)}] OK")
            except Exception as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower() or "equivalent" in error_msg.lower():
                    print(f"  [{i}/{len(statements)}] SKIPPED (already exists)")
                    success += 1
                else:
                    errors.append(f"Statement {i}: {error_msg[:100]}")
                    print(f"  [{i}/{len(statements)}] ERROR: {error_msg[:80]}")
                    if not continue_on_error:
                        break

    print(f"\nCompleted: {success}/{len(statements)}")
    if errors:
        print(f"Errors: {len(errors)}")
    return success, errors


def main():
    print("=" * 60)
    print("ALEX AI ASSISTANT - NEO4J SCHEMA DEPLOYMENT")
    print("=" * 60)

    # Connect
    print(f"\nConnecting to {URI}...")
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

    try:
        driver.verify_connectivity()
        print("Connected!")

        all_errors = []

        # 1. Constraints
        s, e = run_section(driver, "CONSTRAINTS", CONSTRAINTS, continue_on_error=True)
        all_errors.extend(e)

        # 2. Indexes
        s, e = run_section(driver, "INDEXES", INDEXES, continue_on_error=True)
        all_errors.extend(e)

        # 3. Vector Indexes
        s, e = run_section(driver, "VECTOR INDEXES", VECTOR_INDEXES, continue_on_error=True)
        all_errors.extend(e)

        # 4. Fulltext Indexes
        s, e = run_section(driver, "FULLTEXT INDEXES", FULLTEXT_INDEXES, continue_on_error=True)
        all_errors.extend(e)

        # 5. Time Tree Setup (Years, Months, Weeks)
        s, e = run_section(driver, "TIME TREE (Years/Months/Weeks)", TIME_TREE_SETUP, continue_on_error=True)
        all_errors.extend(e)

        # 6. Days 2025
        print(f"\n{'='*60}")
        print("SECTION: DAYS 2025 (365 nodes)")
        print(f"{'='*60}")
        with driver.session(database=DATABASE) as session:
            try:
                session.run(DAYS_2025)
                print("  OK - Created 365 Day nodes for 2025")
            except Exception as e:
                print(f"  ERROR: {e}")
                all_errors.append(f"Days 2025: {e}")

        # 7. Days 2026
        print(f"\n{'='*60}")
        print("SECTION: DAYS 2026 (365 nodes)")
        print(f"{'='*60}")
        with driver.session(database=DATABASE) as session:
            try:
                session.run(DAYS_2026)
                print("  OK - Created 365 Day nodes for 2026")
            except Exception as e:
                print(f"  ERROR: {e}")
                all_errors.append(f"Days 2026: {e}")

        # 8. Next Day Links
        print(f"\n{'='*60}")
        print("SECTION: NEXT_DAY RELATIONSHIPS")
        print(f"{'='*60}")
        with driver.session(database=DATABASE) as session:
            try:
                session.run(NEXT_DAY_LINKS)
                print("  OK - Created NEXT_DAY relationships")
            except Exception as e:
                print(f"  ERROR: {e}")
                all_errors.append(f"Next Day Links: {e}")

        # 9. Seed Data
        s, e = run_section(driver, "SEED DATA", SEED_DATA, continue_on_error=True)
        all_errors.extend(e)

        # Verification
        print(f"\n{'='*60}")
        print("VERIFICATION")
        print(f"{'='*60}")
        with driver.session(database=DATABASE) as session:
            checks = [
                ("Years", "MATCH (y:Year) RETURN count(y) AS c"),
                ("Months", "MATCH (m:Month) RETURN count(m) AS c"),
                ("Weeks", "MATCH (w:Week) RETURN count(w) AS c"),
                ("Days", "MATCH (d:Day) RETURN count(d) AS c"),
                ("Users", "MATCH (u:User) RETURN count(u) AS c"),
                ("Concepts", "MATCH (c:Concept) RETURN count(c) AS c"),
                ("Projects", "MATCH (p:Project) RETURN count(p) AS c"),
            ]
            for name, query in checks:
                result = session.run(query).single()
                count = result["c"] if result else 0
                print(f"  {name}: {count}")

        # Summary
        print(f"\n{'='*60}")
        print("DEPLOYMENT COMPLETE")
        print(f"{'='*60}")
        if all_errors:
            print(f"Completed with {len(all_errors)} errors (some may be 'already exists')")
        else:
            print("All sections deployed successfully!")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
