# Alex AI Assistant - Implementation Plan

## Overview

This plan outlines the implementation of "Alex," an autonomous, self-reflective AI assistant with a Neo4j-based Temporal Knowledge Graph, dual-cortex Gemini 3 architecture, and Claude Code engineering capabilities.

**Current State:**
- GCP project created
- Neo4j AuraDB provisioned at `neo4j+s://d1f2297e.databases.neo4j.io`
- MCP Toolbox binary downloaded
- Basic source configuration in `tools.yaml`

---

## Phase 1: MCP Server & Neo4j Foundation

### Task 1.1: Secure MCP Toolbox Configuration
**Delegated to:** `everything-claude-code:security-reviewer`

**Objective:** Move hardcoded credentials to environment variables and configure secure MCP server access.

**Deliverables:**
- [ ] Update `tools.yaml` to use environment variable references
- [ ] Create `.env.example` template
- [ ] Configure MCP server authentication
- [ ] Document security best practices

**Configuration Update:**
```yaml
sources:
  alex-neo4j:
    kind: "neo4j"
    uri: ${NEO4J_URI}
    user: ${NEO4J_USERNAME}
    password: ${NEO4J_PASSWORD}
    database: ${NEO4J_DATABASE}

tools:
  - name: query-memory
    kind: neo4j-execute-cypher
    source: alex-neo4j
    description: "Execute Cypher queries against Alex's memory graph"

  - name: get-schema
    kind: neo4j-schema
    source: alex-neo4j
    description: "Retrieve the Neo4j database schema"
```

---

### Task 1.2: Initialize Neo4j Schema
**Delegated to:** `everything-claude-code:architect`

**Objective:** Deploy the Temporal Knowledge Graph schema to Neo4j AuraDB.

**Deliverables:**
- [ ] Create `schema/neo4j_schema.cypher` with full schema
- [ ] Create `schema/seed_data.cypher` for initial time tree
- [ ] Script to apply schema via MCP Toolbox or direct connection
- [ ] Verification queries to confirm schema deployment

**Schema Components:**
1. Time Tree (Year → Month → Week → Day)
2. User & Interaction nodes
3. Summary hierarchy (Daily → Weekly → Monthly → Annual)
4. Self-Knowledge nodes (Module, Class, Method, File, Commit)
5. Concept/Entity nodes (Topic, Project, Person, Tag)
6. Vector indexes for hybrid retrieval (1536 dimensions)

---

### Task 1.3: Define MCP Tools for Alex Operations
**Delegated to:** `everything-claude-code:backend-patterns`

**Objective:** Create parameterized MCP tools for common memory operations.

**Tools to Define:**
```yaml
tools:
  # Memory Storage
  - name: store-interaction
    kind: neo4j-execute-cypher
    source: alex-neo4j
    statement: |
      CREATE (i:Interaction {id: $id, timestamp: datetime(), ...})
      WITH i MATCH (d:Day {date: $date}) MERGE (i)-[:OCCURRED_ON]->(d)
    parameters:
      - name: id
        type: string
      - name: date
        type: string
      - name: user_message
        type: string
      - name: assistant_response
        type: string

  # Memory Retrieval
  - name: get-daily-context
    kind: neo4j-execute-cypher
    source: alex-neo4j
    statement: |
      MATCH (d:Day {date: $date})<-[:OCCURRED_ON]-(i:Interaction)
      OPTIONAL MATCH (ds:DailySummary)-[:SUMMARIZES]->(d)
      RETURN d, collect(i) AS interactions, ds
    parameters:
      - name: date
        type: string

  # Summarization Support
  - name: get-interactions-for-summary
    kind: neo4j-execute-cypher
    source: alex-neo4j
    statement: |
      MATCH (d:Day {date: $date})<-[:OCCURRED_ON]-(i:Interaction)
      RETURN i.user_message, i.assistant_response, i.timestamp
      ORDER BY i.timestamp
    parameters:
      - name: date
        type: string

  # Vector Search
  - name: semantic-search
    kind: neo4j-execute-cypher
    source: alex-neo4j
    statement: |
      CALL db.index.vector.queryNodes('vector_index_interaction', $k, $embedding)
      YIELD node, score
      WHERE score >= $threshold
      RETURN node, score ORDER BY score DESC
    parameters:
      - name: embedding
        type: array
      - name: k
        type: integer
      - name: threshold
        type: number

  # Self-Knowledge
  - name: query-codebase
    kind: neo4j-execute-cypher
    source: alex-neo4j
    statement: |
      MATCH (mod:Module)-[:CONTAINS_CLASS]->(cls:Class)-[:HAS_METHOD]->(m:Method)
      WHERE mod.name CONTAINS $query OR cls.name CONTAINS $query OR m.name CONTAINS $query
      RETURN mod.path, cls.name, m.name, m.docstring
    parameters:
      - name: query
        type: string
```

---

## Phase 2: Python Project Structure

### Task 2.1: Project Scaffolding
**Delegated to:** `everything-claude-code:planner`

**Directory Structure:**
```
alex-ai-assistant/
├── alex/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Configuration management
│   │
│   ├── cortex/                    # Dual-Cortex Intelligence
│   │   ├── __init__.py
│   │   ├── flash.py               # Gemini 3 Flash (Basal Cortex)
│   │   ├── pro.py                 # Gemini 3 Pro (Executive Cortex)
│   │   ├── router.py              # Intent classification & routing
│   │   └── models.py              # Pydantic schemas
│   │
│   ├── memory/                    # GraphRAG Memory System
│   │   ├── __init__.py
│   │   ├── graph_store.py         # Neo4j connection & operations
│   │   ├── time_tree.py           # Time tree management
│   │   ├── summarizer.py          # Recursive summarization
│   │   ├── retriever.py           # Hybrid retrieval (vector + graph)
│   │   └── embeddings.py          # Embedding generation
│   │
│   ├── engineering/               # Claude Code Integration
│   │   ├── __init__.py
│   │   ├── wrapper.py             # Headless Claude Code wrapper
│   │   ├── repo_mapper.py         # AST analysis for self-knowledge
│   │   └── tools.py               # LangGraph tool definitions
│   │
│   ├── agents/                    # LangGraph Agents
│   │   ├── __init__.py
│   │   ├── state.py               # AlexState definition
│   │   ├── graph.py               # Main agent graph
│   │   ├── nodes/
│   │   │   ├── chat.py            # Chat response node
│   │   │   ├── memory.py          # Memory retrieval node
│   │   │   ├── engineer.py        # Claude Code node
│   │   │   └── summarize.py       # Background summarization
│   │   └── edges.py               # Conditional routing
│   │
│   └── api/                       # REST API
│       ├── __init__.py
│       ├── routes.py              # API endpoints
│       └── middleware.py          # Auth, logging, etc.
│
├── schema/                        # Neo4j Schema
│   ├── neo4j_schema.cypher
│   ├── seed_data.cypher
│   └── migrations/
│
├── tests/
│   ├── __init__.py
│   ├── test_memory.py
│   ├── test_cortex.py
│   └── test_engineering.py
│
├── infrastructure/                # GCP Deployment
│   ├── Dockerfile
│   ├── cloudbuild.yaml
│   └── terraform/                 # Optional IaC
│
├── tools.yaml                     # MCP Toolbox configuration
├── CLAUDE.md                      # AI Constitution
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

### Task 2.2: Core Dependencies
**Delegated to:** `everything-claude-code:backend-patterns`

**pyproject.toml:**
```toml
[project]
name = "alex-ai-assistant"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Core Framework
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",

    # LLM & Orchestration
    "langgraph>=0.1.0",
    "langchain>=0.1.0",
    "langchain-google-genai>=1.0.0",
    "google-generativeai>=0.4.0",

    # Neo4j
    "neo4j>=5.15.0",
    "langchain-neo4j>=0.1.0",

    # MCP Integration
    "mcp-toolbox-sdk>=0.1.0",  # Google MCP Toolbox SDK

    # Utilities
    "python-dotenv>=1.0.0",
    "httpx>=0.26.0",
    "tenacity>=8.2.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.2.0",
    "mypy>=1.8.0",
]
```

---

### Task 2.3: LangGraph Agent Architecture
**Delegated to:** `everything-claude-code:architect`

**State Definition (`alex/agents/state.py`):**
```python
from typing import TypedDict, List, Annotated, Optional
from langgraph.graph.message import add_messages
from pydantic import BaseModel

class AlexState(TypedDict):
    """Core state for Alex agent."""
    messages: Annotated[List[dict], add_messages]
    user_id: str
    intent: Optional[str]
    complexity_score: float
    memory_context: dict
    tool_outputs: dict
    current_cortex: str  # "flash" | "pro" | "claude_code"
    session_id: str
    error: Optional[str]
```

**Graph Definition (`alex/agents/graph.py`):**
```python
from langgraph.graph import StateGraph, END
from alex.agents.state import AlexState
from alex.agents.nodes import chat, memory, engineer, summarize
from alex.agents.edges import route_request

# Build the graph
builder = StateGraph(AlexState)

# Add nodes
builder.add_node("classify_intent", classify_intent)
builder.add_node("retrieve_memory", memory.retrieve)
builder.add_node("chat_flash", chat.respond_flash)
builder.add_node("chat_pro", chat.respond_pro)
builder.add_node("engineer_node", engineer.invoke_claude_code)
builder.add_node("store_interaction", memory.store)

# Set entry point
builder.set_entry_point("classify_intent")

# Add edges
builder.add_conditional_edges(
    "classify_intent",
    route_request,
    {
        "memory": "retrieve_memory",
        "chat": "chat_flash",
        "complex": "chat_pro",
        "engineering": "engineer_node",
    }
)

builder.add_edge("retrieve_memory", "chat_flash")
builder.add_edge("chat_flash", "store_interaction")
builder.add_edge("chat_pro", "store_interaction")
builder.add_edge("engineer_node", "chat_pro")  # Pro reviews Claude Code output
builder.add_edge("store_interaction", END)

# Compile
alex_graph = builder.compile()
```

---

## Phase 3: Memory System Implementation

### Task 3.1: Graph Store Implementation
**Delegated to:** `everything-claude-code:backend-patterns`

**Objective:** Implement Neo4j connection management and core CRUD operations.

**Key Methods:**
- `store_interaction()` - Save user-assistant exchange
- `get_daily_context()` - Retrieve day's interactions
- `get_weekly_summary()` - Retrieve or generate weekly summary
- `update_time_tree()` - Ensure time tree nodes exist
- `link_to_concepts()` - Extract and link concepts/topics

---

### Task 3.2: Recursive Summarization Pipeline
**Delegated to:** `everything-claude-code:backend-patterns`

**Objective:** Implement the 4-level summarization hierarchy.

**Summarization Worker:**
```python
class SummarizationWorker:
    """Background worker for recursive summarization."""

    async def summarize_daily(self, date: str) -> DailySummary:
        """Level 1: Aggregate raw interactions into daily summary."""
        interactions = await self.graph_store.get_interactions_for_date(date)
        if not interactions:
            return None

        summary_text = await self.flash_model.invoke(
            f"Summarize these interactions:\n{interactions}"
        )

        embedding = await self.embed(summary_text)

        return await self.graph_store.create_daily_summary(
            date=date,
            content=summary_text,
            embedding=embedding
        )

    async def summarize_weekly(self, week_id: str) -> WeeklySummary:
        """Level 2: Aggregate daily summaries into weekly summary."""
        daily_summaries = await self.graph_store.get_daily_summaries_for_week(week_id)
        # ... aggregate and create weekly summary

    async def summarize_monthly(self, month_id: str) -> MonthlySummary:
        """Level 3: Aggregate weekly summaries into monthly summary."""
        # ...

    async def summarize_annual(self, year: int) -> AnnualSummary:
        """Level 4: Aggregate monthly summaries into annual summary."""
        # ...
```

---

### Task 3.3: Hybrid Retriever
**Delegated to:** `everything-claude-code:backend-patterns`

**Objective:** Implement vector + graph traversal retrieval.

**Retrieval Strategy:**
1. **Semantic Entry:** Use vector index to find relevant nodes
2. **Graph Traversal:** Expand context via relationships
3. **Temporal Filtering:** Apply time-based constraints
4. **Adaptive Level Selection:** Choose appropriate summary level based on time distance

---

## Phase 4: Claude Code Integration

### Task 4.1: Headless Wrapper
**Delegated to:** `everything-claude-code:backend-patterns`

**Implementation (`alex/engineering/wrapper.py`):**
```python
import subprocess
import asyncio
from typing import Optional

class ClaudeCodeWrapper:
    """Headless wrapper for Claude Code CLI."""

    def __init__(self, working_dir: str, timeout: int = 600):
        self.working_dir = working_dir
        self.timeout = timeout

    async def invoke(
        self,
        prompt: str,
        context_files: Optional[list[str]] = None
    ) -> dict:
        """Execute Claude Code in non-interactive mode."""

        cmd = ["claude", "--print", prompt]

        if context_files:
            cmd.extend(["--context", ",".join(context_files)])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )

            return {
                "status": "success" if process.returncode == 0 else "error",
                "output": stdout.decode(),
                "error": stderr.decode() if stderr else None,
                "return_code": process.returncode
            }

        except asyncio.TimeoutError:
            process.kill()
            return {"status": "error", "error": "Operation timed out"}
```

---

### Task 4.2: Repository Mapper (Self-Knowledge)
**Delegated to:** `everything-claude-code:backend-patterns`

**Objective:** Parse Python codebase and ingest structure into Neo4j.

**Implementation:**
```python
import ast
from pathlib import Path

class RepositoryMapper:
    """Parse Python codebase and create self-knowledge graph."""

    def analyze_file(self, file_path: Path) -> dict:
        """Parse a Python file and extract structure."""
        with open(file_path) as f:
            tree = ast.parse(f.read())

        classes = []
        functions = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(self._extract_class(node))
            elif isinstance(node, ast.FunctionDef):
                functions.append(self._extract_function(node))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(self._extract_import(node))

        return {
            "path": str(file_path),
            "classes": classes,
            "functions": functions,
            "imports": imports
        }

    async def ingest_to_graph(self, analysis: dict):
        """Store analysis results in Neo4j."""
        # Create Module, Class, Method, Function nodes
        # Create relationships (CONTAINS_CLASS, HAS_METHOD, IMPORTS, CALLS)
```

---

## Phase 5: GCP Infrastructure

### Task 5.1: Dockerfile
**Delegated to:** `everything-claude-code:backend-patterns`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | sh

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY alex/ ./alex/
COPY tools.yaml .
COPY CLAUDE.md .

# Set environment
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Run
CMD ["uvicorn", "alex.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

### Task 5.2: Cloud Build Pipeline
**Delegated to:** `everything-claude-code:backend-patterns`

```yaml
# cloudbuild.yaml
steps:
  # Build Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/alex:$COMMIT_SHA', '.']

  # Push to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/alex:$COMMIT_SHA']

  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'alex'
      - '--image=gcr.io/$PROJECT_ID/alex:$COMMIT_SHA'
      - '--region=us-central1'
      - '--platform=managed'
      - '--allow-unauthenticated'
      - '--set-secrets=NEO4J_URI=neo4j-uri:latest,NEO4J_PASSWORD=neo4j-password:latest,ANTHROPIC_API_KEY=anthropic-key:latest,GOOGLE_API_KEY=google-api-key:latest'
      - '--max-instances=3'
      - '--min-instances=0'
      - '--memory=2Gi'
      - '--cpu=2'
      - '--timeout=300'

images:
  - 'gcr.io/$PROJECT_ID/alex:$COMMIT_SHA'
```

---

### Task 5.3: Cloud Scheduler for Background Tasks
**Delegated to:** `everything-claude-code:backend-patterns`

**Scheduled Jobs:**
```bash
# Daily summarization (runs at 2 AM)
gcloud scheduler jobs create http alex-daily-summary \
  --schedule="0 2 * * *" \
  --uri="https://alex-xxxxx.run.app/tasks/summarize_daily" \
  --http-method=POST \
  --oidc-service-account-email=alex-scheduler@$PROJECT_ID.iam.gserviceaccount.com

# Weekly summarization (runs Monday at 3 AM)
gcloud scheduler jobs create http alex-weekly-summary \
  --schedule="0 3 * * 1" \
  --uri="https://alex-xxxxx.run.app/tasks/summarize_weekly" \
  --http-method=POST \
  --oidc-service-account-email=alex-scheduler@$PROJECT_ID.iam.gserviceaccount.com

# Repository mapping (runs daily at 4 AM)
gcloud scheduler jobs create http alex-repo-map \
  --schedule="0 4 * * *" \
  --uri="https://alex-xxxxx.run.app/tasks/map_repository" \
  --http-method=POST \
  --oidc-service-account-email=alex-scheduler@$PROJECT_ID.iam.gserviceaccount.com
```

---

## Phase 6: CLAUDE.md Constitution

### Task 6.1: Create AI Constitution
**Delegated to:** `everything-claude-code:architect`

```markdown
# CLAUDE.md - Alex AI Assistant Constitution

## Project Overview
Alex is an autonomous, self-reflective AI assistant with:
- Dual-Cortex architecture (Gemini 3 Flash + Pro)
- Neo4j Temporal Knowledge Graph memory
- Self-modification capabilities via Claude Code

## Architecture Rules
1. Never modify `cloudbuild.yaml` without human approval
2. All code changes must include tests
3. Database schema changes require migration scripts
4. Never delete historical interaction data

## Code Style
- Follow PEP 8 for Python
- Use type hints for all functions
- Docstrings required for public methods
- Maximum function length: 50 lines

## Folder Structure
- `/alex/cortex/` - LLM integration (DO NOT modify routing logic without approval)
- `/alex/memory/` - Graph database operations
- `/alex/engineering/` - Self-modification tools
- `/alex/agents/` - LangGraph orchestration

## Security
- Never log API keys or passwords
- All external connections must use HTTPS
- Validate all user inputs before database operations

## Testing Requirements
- Unit test coverage > 80%
- Integration tests for all API endpoints
- E2E tests for critical workflows
```

---

## Subagent Task Delegation Summary

| Phase | Task | Delegated To | Priority |
|-------|------|--------------|----------|
| 1.1 | Secure MCP Configuration | `security-reviewer` | High |
| 1.2 | Initialize Neo4j Schema | `architect` | High |
| 1.3 | Define MCP Tools | `backend-patterns` | High |
| 2.1 | Project Scaffolding | `planner` | High |
| 2.2 | Core Dependencies | `backend-patterns` | Medium |
| 2.3 | LangGraph Architecture | `architect` | High |
| 3.1 | Graph Store Implementation | `backend-patterns` | High |
| 3.2 | Summarization Pipeline | `backend-patterns` | Medium |
| 3.3 | Hybrid Retriever | `backend-patterns` | Medium |
| 4.1 | Claude Code Wrapper | `backend-patterns` | Medium |
| 4.2 | Repository Mapper | `backend-patterns` | Low |
| 5.1 | Dockerfile | `backend-patterns` | Medium |
| 5.2 | Cloud Build Pipeline | `backend-patterns` | Medium |
| 5.3 | Cloud Scheduler | `backend-patterns` | Low |
| 6.1 | CLAUDE.md Constitution | `architect` | Medium |

---

## Immediate Next Steps

1. **Update `tools.yaml`** with environment variables and tool definitions
2. **Create `schema/neo4j_schema.cypher`** and deploy to AuraDB
3. **Initialize Python project** with `pyproject.toml`
4. **Implement core `AlexState`** and LangGraph skeleton
5. **Test MCP Toolbox** connectivity to Neo4j

---

## Cost Estimates (Monthly)

| Service | Estimate |
|---------|----------|
| Neo4j AuraDB (Free tier) | $0 |
| Cloud Run (scale-to-zero) | $5-20 |
| Gemini 3 Flash (primary) | $10-30 |
| Gemini 3 Pro (escalated) | $5-15 |
| Claude Code (engineering) | $20-50 |
| **Total** | **$40-115/month** |

---

*Generated: 2026-01-25*
