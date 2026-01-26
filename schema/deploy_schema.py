#!/usr/bin/env python3
"""
Neo4j Schema Deployment Script for Alex AI Assistant

This script deploys the Temporal Knowledge Graph schema to Neo4j AuraDB.
It reads the schema from neo4j_schema.cypher and executes it in sections.

Usage:
    python deploy_schema.py

Environment Variables Required:
    NEO4J_URI - Neo4j connection URI (e.g., neo4j+s://xxx.databases.neo4j.io)
    NEO4J_USERNAME - Database username
    NEO4J_PASSWORD - Database password
    NEO4J_DATABASE - Database name (default: neo4j)
"""

import os
import sys
import re
from pathlib import Path

try:
    from neo4j import GraphDatabase
    from dotenv import load_dotenv
except ImportError:
    print("Required packages not installed. Run:")
    print("  pip install neo4j python-dotenv")
    sys.exit(1)


def load_config():
    """Load configuration from environment variables."""
    load_dotenv()

    config = {
        "uri": os.getenv("NEO4J_URI"),
        "username": os.getenv("NEO4J_USERNAME", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD"),
        "database": os.getenv("NEO4J_DATABASE", "neo4j"),
    }

    if not config["uri"] or not config["password"]:
        print("Error: NEO4J_URI and NEO4J_PASSWORD environment variables are required.")
        print("Create a .env file with these values or export them.")
        sys.exit(1)

    return config


def parse_schema_file(filepath: Path) -> list[dict]:
    """
    Parse the schema file into executable sections.

    Returns a list of dicts with 'name' and 'statements' keys.
    """
    content = filepath.read_text()

    # Split by section headers
    section_pattern = r'// =+\n// SECTION (\d+): ([^\n]+)\n// =+'

    sections = []
    matches = list(re.finditer(section_pattern, content))

    for i, match in enumerate(matches):
        section_num = match.group(1)
        section_name = match.group(2).strip()

        # Get content between this section and the next (or end of file)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_content = content[start:end]

        # Extract individual statements (split by semicolons, but handle multiline)
        # Skip comments and empty lines
        statements = []
        current_statement = []

        for line in section_content.split('\n'):
            stripped = line.strip()

            # Skip pure comment lines and empty lines when not in a statement
            if not current_statement and (stripped.startswith('//') or stripped.startswith('/*') or not stripped):
                continue

            current_statement.append(line)

            # Check if statement is complete (ends with semicolon, not in string/comment)
            if stripped.endswith(';') and not stripped.startswith('//'):
                stmt = '\n'.join(current_statement).strip()
                if stmt and not stmt.startswith('//') and not stmt.startswith('/*'):
                    # Remove trailing comments on the statement
                    statements.append(stmt)
                current_statement = []

        if statements:
            sections.append({
                "number": section_num,
                "name": section_name,
                "statements": statements
            })

    return sections


def execute_statement(tx, statement: str):
    """Execute a single Cypher statement."""
    # Skip if it's just a comment block
    if statement.strip().startswith('/*'):
        return None

    # Clean up the statement
    statement = statement.strip()
    if not statement or statement == ';':
        return None

    try:
        result = tx.run(statement)
        return result.consume()
    except Exception as e:
        raise Exception(f"Failed to execute statement: {str(e)}\nStatement: {statement[:200]}...")


def deploy_schema(driver, database: str, sections: list[dict], dry_run: bool = False):
    """Deploy schema sections to Neo4j."""

    total_statements = sum(len(s["statements"]) for s in sections)
    executed = 0
    errors = []

    print(f"\nDeploying {total_statements} statements across {len(sections)} sections...\n")

    for section in sections:
        print(f"Section {section['number']}: {section['name']}")
        print(f"  Statements: {len(section['statements'])}")

        if dry_run:
            print("  [DRY RUN - Skipping execution]")
            continue

        with driver.session(database=database) as session:
            for i, statement in enumerate(section['statements'], 1):
                try:
                    # Skip comment blocks
                    if statement.strip().startswith('/*'):
                        continue

                    session.execute_write(execute_statement, statement)
                    executed += 1
                    print(f"    [{i}/{len(section['statements'])}] OK")

                except Exception as e:
                    error_msg = f"Section {section['number']}, Statement {i}: {str(e)}"
                    errors.append(error_msg)
                    print(f"    [{i}/{len(section['statements'])}] ERROR: {str(e)[:100]}")

        print()

    return executed, errors


def verify_deployment(driver, database: str):
    """Run verification queries to confirm schema deployment."""

    print("Running verification checks...\n")

    checks = [
        ("Constraints", "SHOW CONSTRAINTS YIELD name RETURN count(*) AS count"),
        ("Indexes", "SHOW INDEXES YIELD name WHERE name STARTS WITH 'index_' OR name STARTS WITH 'vector_' OR name STARTS WITH 'fulltext_' RETURN count(*) AS count"),
        ("Years", "MATCH (y:Year) RETURN count(y) AS count"),
        ("Months", "MATCH (m:Month) RETURN count(m) AS count"),
        ("Weeks", "MATCH (w:Week) RETURN count(w) AS count"),
        ("Days", "MATCH (d:Day) RETURN count(d) AS count"),
        ("Users", "MATCH (u:User) RETURN count(u) AS count"),
        ("Concepts", "MATCH (c:Concept) RETURN count(c) AS count"),
        ("Projects", "MATCH (p:Project) RETURN count(p) AS count"),
    ]

    results = {}

    with driver.session(database=database) as session:
        for name, query in checks:
            try:
                result = session.run(query)
                record = result.single()
                count = record["count"] if record else 0
                results[name] = count
                status = "OK" if count > 0 else "EMPTY"
                print(f"  {name}: {count} ({status})")
            except Exception as e:
                results[name] = f"ERROR: {e}"
                print(f"  {name}: ERROR - {e}")

    return results


def main():
    """Main deployment function."""

    print("=" * 60)
    print("Alex AI Assistant - Neo4j Schema Deployment")
    print("=" * 60)

    # Load configuration
    config = load_config()
    print(f"\nTarget: {config['uri']}")
    print(f"Database: {config['database']}")

    # Find schema file
    schema_path = Path(__file__).parent / "neo4j_schema.cypher"
    if not schema_path.exists():
        print(f"\nError: Schema file not found at {schema_path}")
        sys.exit(1)

    print(f"Schema file: {schema_path}")

    # Parse schema
    print("\nParsing schema file...")
    sections = parse_schema_file(schema_path)
    print(f"Found {len(sections)} sections")

    # Check for dry run flag
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***")

    # Confirm deployment
    if not dry_run:
        print("\nThis will deploy the schema to your Neo4j database.")
        response = input("Continue? (yes/no): ").strip().lower()
        if response != "yes":
            print("Deployment cancelled.")
            sys.exit(0)

    # Connect to Neo4j
    print("\nConnecting to Neo4j...")
    driver = GraphDatabase.driver(
        config["uri"],
        auth=(config["username"], config["password"])
    )

    try:
        # Verify connection
        driver.verify_connectivity()
        print("Connected successfully!")

        # Deploy schema
        executed, errors = deploy_schema(
            driver,
            config["database"],
            sections,
            dry_run=dry_run
        )

        # Summary
        print("=" * 60)
        print("DEPLOYMENT SUMMARY")
        print("=" * 60)
        print(f"Statements executed: {executed}")
        print(f"Errors: {len(errors)}")

        if errors:
            print("\nErrors encountered:")
            for error in errors[:10]:  # Show first 10 errors
                print(f"  - {error[:200]}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more")

        # Verify deployment
        if not dry_run:
            print("\n" + "=" * 60)
            verify_deployment(driver, config["database"])

        print("\n" + "=" * 60)
        print("Deployment complete!")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
