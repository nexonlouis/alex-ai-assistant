# CLAUDE.md - Alex AI Assistant Constitution

This file defines the rules, patterns, and constraints for AI-assisted development on this codebase.

## Project Overview

Alex is an autonomous, self-reflective AI assistant with:
- **Dual-Cortex Architecture**: Gemini 3 Flash (routine) + Gemini 3 Pro (complex reasoning)
- **Temporal Knowledge Graph**: Neo4j-based memory with recursive summarization
- **Self-Modification**: Claude Code integration for autonomous engineering
- **MCP Integration**: Google's MCP Toolbox for database access

## Architecture Rules

### Critical Constraints
1. **NEVER** modify `cloudbuild.yaml` or deployment configs without explicit human approval
2. **NEVER** delete historical interaction data from Neo4j
3. **NEVER** modify the schema constraints without migration scripts
4. **ALWAYS** include tests for new functionality
5. **ALWAYS** preserve backward compatibility for API endpoints

### Model Routing
- **Flash** (default): Chat, classification, summarization, simple questions
- **Pro** (escalated): Complex reasoning, planning, ambiguous requests, architecture
- **Claude Code**: File modifications, refactoring, test execution

### Complexity Threshold
- Requests with `complexity_score >= 0.7` are routed to Pro
- Engineering tasks (`intent in {code_change, refactor, debug, test}`) go to Claude Code

## Code Style

### Python
- Python 3.11+ required
- Follow PEP 8 with max line length 100
- Use type hints for all function signatures
- Docstrings required for public methods (Google style)
- Use `async/await` for all I/O operations

### Imports
```python
# Standard library
from datetime import datetime
from typing import Any

# Third-party
import structlog
from fastapi import APIRouter
from pydantic import BaseModel

# Local
from alex.config import settings
from alex.memory import GraphStore
```

### Naming Conventions
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

## Folder Structure

```
alex/
├── cortex/          # LLM integration (Flash, Pro models)
│   ├── flash.py     # Basal Cortex - routine operations
│   ├── pro.py       # Executive Cortex - complex reasoning
│   ├── claude.py    # Claude Code integration
│   └── router.py    # Request routing logic
│
├── memory/          # Neo4j knowledge graph
│   ├── graph_store.py   # CRUD operations
│   ├── retriever.py     # Hybrid retrieval
│   └── summarizer.py    # Recursive summarization
│
├── agents/          # LangGraph orchestration
│   ├── state.py     # AlexState definition
│   ├── graph.py     # Main agent graph
│   ├── edges.py     # Conditional routing
│   └── nodes/       # Individual node implementations
│
├── engineering/     # Claude Code integration
│   └── wrapper.py   # Headless CLI wrapper
│
├── api/            # REST API
│   └── routes.py   # FastAPI endpoints
│
└── main.py         # Application entry point

web/
└── index.html      # Simple chat UI for local development
```

## Protected Files

These files require **explicit human approval** before modification:
- `cloudbuild.yaml` - Deployment pipeline
- `schema/neo4j_schema.cypher` - Database schema
- `alex/config.py` - Configuration (sensitive defaults)
- `CLAUDE.md` - This constitution file

## Neo4j Patterns

### Time Tree Queries
```cypher
// Always use parameterized queries
MATCH (d:Day {date: $date})<-[:OCCURRED_ON]-(i:Interaction)
RETURN i
ORDER BY i.timestamp
```

### Summary Levels
1. **Raw**: Individual interactions (< 1 day old)
2. **Daily**: DailySummary nodes (1-7 days old)
3. **Weekly**: WeeklySummary nodes (1-4 weeks old)
4. **Monthly**: MonthlySummary nodes (1-12 months old)
5. **Annual**: AnnualSummary nodes (> 1 year old)

### Vector Search
- Embedding model: text-embedding-004
- Embedding dimension: 768
- Similarity function: cosine
- Minimum score threshold: 0.7

## Security Rules

1. **NEVER** log API keys, passwords, or tokens
2. **NEVER** include credentials in code (use environment variables)
3. **ALWAYS** use parameterized queries for Neo4j
4. **ALWAYS** validate user inputs before processing
5. **ALWAYS** use HTTPS for external connections

## Testing Requirements

- Unit test coverage: > 80%
- Integration tests for all API endpoints
- Mock external services in tests
- Use `pytest` with `pytest-asyncio`

```bash
# Run tests
pytest tests/ -v --cov=alex --cov-report=term-missing
```

## Error Handling

```python
# Use structured logging
import structlog
logger = structlog.get_logger()

try:
    result = await some_operation()
except SpecificError as e:
    logger.error("Operation failed", error=str(e), context={"key": "value"})
    # Handle gracefully, don't crash
```

## Git Workflow

1. Create feature branches from `main`
2. Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`
3. Require PR review before merge
4. Squash commits on merge

## Environment Variables

Required:
- `NEO4J_URI` - Neo4j connection string
- `NEO4J_PASSWORD` - Neo4j password
- `GOOGLE_API_KEY` - Gemini API key

Optional:
- `ANTHROPIC_API_KEY` - For Claude Code integration
- `APP_ENV` - Environment (development/production)
- `LOG_LEVEL` - Logging level (INFO/DEBUG/WARNING)

## Common Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run API server locally
python -m alex.main

# Run Web UI (in separate terminal)
cd web && python -m http.server 3000
# Open http://localhost:3000 in browser

# Run tests
pytest tests/ -v

# Type checking
mypy alex/

# Linting
ruff check alex/
```

---

*Last updated: 2026-01-26*
*Version: 1.1.0*
