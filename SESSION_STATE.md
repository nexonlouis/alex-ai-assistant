# Alex AI Assistant - Session State

**Last Updated:** 2026-02-11 (Database Sync)

## Current Status: LIVE IN PRODUCTION 🚀

**Service URL:** https://alex-api-102313356909.us-central1.run.app
**Local Web UI:** http://localhost:3000 (when running locally)

All core features deployed and verified:

### Completed Components

| Component | Status | Notes |
|-----------|--------|-------|
| PostgreSQL Schema | ✅ Deployed | Migrated from Neo4j with pgvector extension |
| Python Project | ✅ Complete | LangGraph + FastAPI architecture |
| LangGraph State | ✅ Fixed | Changed from Pydantic BaseModel to TypedDict for message compatibility |
| Intent Classification | ✅ Working | Gemini Flash classifies intents and complexity scores |
| Gemini Flash (Basal) | ✅ Working | Handles routine queries |
| API Endpoints | ✅ Working | `/api/v1/chat`, `/api/v1/health`, debug and admin endpoints |
| PostgreSQL Connection | ✅ Healthy | Connected to database with pgvector |
| Web UI | ✅ Working | Simple chat interface at `web/index.html` |

### Verified Components

| Component | Status | Notes |
|-----------|--------|-------|
| Memory Persistence | ✅ Verified | Interactions stored with Day/User/Concept linking |
| Day Linking | ✅ Verified | Temporal relationships working |
| User Linking | ✅ Verified | User interaction relationships working |
| Concept Extraction | ✅ Verified | Topics extracted and linked |
| Gemini Pro (Executive) | ✅ Verified | Routes correctly when complexity >= 0.7 |
| SDK Migration | ✅ Complete | Migrated from google-generativeai to google-genai |
| Semantic Search | ✅ Verified | Vector search working with 768-dim embeddings (pgvector) |
| Hybrid Retrieval | ✅ Verified | Temporal + semantic retrieval working |
| Embedding Generation | ✅ Verified | text-embedding-004 (768 dims) on store |

### Claude Code Integration

| Component | Status | Notes |
|-----------|--------|-------|
| Claude Integration Module | ✅ Complete | `alex/cortex/claude.py` - Anthropic API client |
| Engineering Node | ✅ Complete | `alex/agents/nodes/engineer.py` - handles engineering tasks |
| Graph Routing | ✅ Complete | Routes `code_change`, `refactor`, `debug`, `test` intents to Claude |
| Fallback to Gemini Pro | ✅ Working | Falls back to Pro when ANTHROPIC_API_KEY not set |
| API Key Configuration | ⚠️ Required | Add `ANTHROPIC_API_KEY` to `.env` for full Claude support |

### Recursive Summarization

| Component | Status | Notes |
|-----------|--------|-------|
| Summarizer Module | ✅ Complete | `alex/memory/summarizer.py` - LLM-powered summarization |
| Daily Summaries | ✅ Working | Summarizes day's interactions into key topics |
| Weekly Summaries | ✅ Working | Aggregates daily summaries into weekly themes |
| Monthly Summaries | ✅ Working | Aggregates weekly summaries into strategic insights |
| API Endpoints | ✅ Complete | `/tasks/summarize_daily`, `/tasks/summarize_weekly`, `/tasks/summarize_monthly`, `/tasks/summarize_all` |
| Debug Endpoints | ✅ Complete | `/debug/summaries`, `/debug/unsummarized` |

### TastyTrade Brokerage Integration

| Component | Status | Notes |
|-----------|--------|-------|
| TastyTrade Client | ✅ Complete | `alex/brokerage/tastytrade_client.py` - Direct HTTP API with session caching |
| Trading Tools | ✅ Complete | `alex/brokerage/tastytrade_tools.py` - Gemini function calling tools |
| Trade Intent Routing | ✅ Complete | `trade` intent classification and graph routing |
| Trade Node | ✅ Complete | `alex/agents/nodes/trade.py` - Safety-focused trading responses |
| Audit Logging | ✅ Complete | `trades` table in PostgreSQL for all executed trades |
| Unit Tests | ✅ Complete | 18 tests with mocked HTTP responses |

**Safety Mechanisms:**
- Sandbox mode by default (paper trading)
- Mandatory two-step confirmation flow (dry-run → confirm)
- 5-minute trade expiration window
- Full audit trail in PostgreSQL

**Available Tools:**
- `get_positions()` - List current positions with P&L
- `get_account_balances()` - Cash, buying power, net liquidating value
- `place_order_dry_run()` - Validate order, get trade_id for confirmation
- `close_position_dry_run()` - Validate position close, get trade_id
- `confirm_trade(trade_id)` - Execute validated trade
- `cancel_pending_trade(trade_id)` - Cancel without executing

### Database Sync (Local → Remote)

| Component | Status | Notes |
|-----------|--------|-------|
| Sync Module | ✅ Complete | `alex/sync/db_sync.py` - Incremental sync logic |
| Setup Script | ✅ Complete | `scripts/setup_sync_schedule.sh` - macOS launchd setup |
| Schedule | ✅ Active | Daily at 2:00 AM via launchd |
| State Tracking | ✅ Working | `~/.alex/sync_state.json` tracks last sync |
| Logs | ✅ Configured | `~/.alex/logs/sync.log` |

**Tables Synced:**
- `users`, `days`, `interactions`, `concepts`
- `interaction_concepts`, `code_changes`, `code_change_concepts`
- `daily_summaries`, `weekly_summaries`, `monthly_summaries`
- `trades`

**Commands:**
```bash
# Run sync manually
python -m alex.sync.db_sync

# Check sync status
python -m alex.sync.db_sync --status

# Force full sync (ignore last sync time)
python -m alex.sync.db_sync --force-full

# View sync logs
tail -f ~/.alex/logs/sync.log

# Manage schedule
launchctl unload ~/Library/LaunchAgents/com.alex.dbsync.plist  # Stop
launchctl load ~/Library/LaunchAgents/com.alex.dbsync.plist    # Start
```

### Production Deployment

| Component | Status | Notes |
|-----------|--------|-------|
| Cloud Run Service | ✅ Live | `alex-api` in `us-central1` |
| Service URL | ✅ Active | https://alex-api-102313356909.us-central1.run.app |
| Secret Manager | ✅ Configured | All secrets stored and accessible |
| Artifact Registry | ✅ Created | `alex-repo` for container images |
| Cloud Scheduler | ✅ Active | 3 jobs for automated summarization |

### Cloud Scheduler Jobs

| Job | Schedule (UTC) | Endpoint |
|-----|----------------|----------|
| `alex-daily-summary` | 2:00 AM daily | `/api/v1/tasks/summarize_daily` |
| `alex-weekly-summary` | 3:00 AM Mondays | `/api/v1/tasks/summarize_weekly` |
| `alex-monthly-summary` | 4:00 AM on 1st | `/api/v1/tasks/summarize_monthly` |

### Pending Components

| Component | Status | Notes |
|-----------|--------|-------|
| Repository Mapper | ⏳ Pending | Self-knowledge AST analysis |

## Key Files Modified

### State Management (TypedDict Fix)
Files updated to use `state.get("key")` instead of `state.key`:

1. `alex/agents/state.py` - Changed AlexState from BaseModel to TypedDict
2. `alex/agents/graph.py` - Updated invoke_alex and handle_error
3. `alex/agents/nodes/classify.py` - Updated classify_intent
4. `alex/agents/nodes/chat.py` - Updated respond_flash, respond_pro
5. `alex/agents/nodes/memory.py` - Updated retrieve_memory, store_interaction
6. `alex/agents/edges.py` - Updated routing functions
7. `alex/cortex/router.py` - Updated route_to_cortex, should_escalate

### Helper Functions (now standalone)
```python
from alex.agents.state import get_last_user_message, get_last_assistant_message

# Usage:
user_msg = get_last_user_message(state)  # Not state.get_last_user_message()
assistant_msg = get_last_assistant_message(state)
```

## Environment Setup

### Required Environment Variables (.env)
```
# For local development
POSTGRES_URI=postgresql://localhost:5432/alex
GOOGLE_API_KEY=<your-api-key>

# For database sync
LOCAL_POSTGRES_URI=postgresql://localhost:5432/alex
REMOTE_POSTGRES_URI=<your-neon-connection-string>
```

### Optional Environment Variables
```
ANTHROPIC_API_KEY=<your-api-key>  # For Claude Code integration
APP_ENV=development
LOG_LEVEL=INFO

# TastyTrade (Sandbox - Paper Trading)
TASTY_SANDBOX_USERNAME=<your-sandbox-username>
TASTY_SANDBOX_PASSWORD=<your-sandbox-password>

# TastyTrade (Production - Real Money)
TASTY_USERNAME=<your-username>
TASTY_PASSWORD=<your-password>
TASTY_USE_SANDBOX=true  # Set to false for production trading
```

### GCP APIs Enabled
- ✅ Generative Language API (required for Gemini)
- ✅ Cloud Run API
- ✅ Cloud Build API
- ✅ Secret Manager API
- ✅ Artifact Registry API
- ✅ Cloud Scheduler API

### Running the Server
```bash
# From project root
python3 -m alex.main

# Start the Web UI (in a separate terminal)
cd web && python3 -m http.server 3000
# Then open http://localhost:3000 in your browser

# Test endpoints
curl http://localhost:8080/api/v1/health
curl -X POST http://localhost:8080/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Hello Alex"}'

# Debug endpoints
curl http://localhost:8080/api/v1/debug/interactions          # Check stored interactions
curl http://localhost:8080/api/v1/debug/semantic-search?query=microservices  # Test semantic search
curl http://localhost:8080/api/v1/memory/today                # Get today's context

# Trading endpoints (requires TastyTrade credentials in .env)
curl -X POST http://localhost:8080/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Show me my positions"}'

curl -X POST http://localhost:8080/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is my account balance?"}'

# Admin endpoints
curl -X POST http://localhost:8080/api/v1/admin/backfill-embeddings    # Backfill missing embeddings
curl -X POST http://localhost:8080/api/v1/admin/update-vector-indexes  # Update vector indexes
```

## Architecture Overview

```
User Request
     │
     ▼
┌─────────────────┐
│ classify_intent │  ← Gemini Flash analyzes intent & complexity
└────────┬────────┘
         │
    ┌────┴────┬──────────┬─────────┬─────────┐
    ▼         ▼          ▼         ▼         ▼
 [simple]  [memory]  [complex]  [engineer]  [trade]
    │         │          │         │         │
    ▼         ▼          ▼         ▼         ▼
  Flash   retrieve    Pro      Claude     TastyTrade
           memory      │        Code       Tools
             │         │         │         │
             └────┬────┴─────────┴─────────┘
                  ▼
         store_interaction → PostgreSQL
                  │
                  ▼
                 END
```

## Next Steps (In Order)

1. ~~**Memory Persistence Testing**~~ ✅ COMPLETE
   - ✅ Interactions stored in PostgreSQL with embeddings
   - ✅ Interaction rows created with correct properties
   - ✅ Links to Day and Concepts working

2. ~~**Gemini Pro Routing**~~ ✅ COMPLETE
   - ✅ High-complexity queries (>= 0.7) route to Pro
   - ✅ Flash handles routine queries
   - ✅ SDK migrated to google-genai with gemini-3-flash/pro-preview models

3. ~~**Memory Retrieval Testing**~~ ✅ COMPLETE
   - ✅ Semantic search returns relevant past interactions
   - ✅ Vector indexes using pgvector (768 dimensions for text-embedding-004)
   - ✅ Hybrid retrieval (temporal + semantic) working
   - ✅ Alex recalls previous conversations accurately

4. ~~**Claude Code Integration**~~ ✅ COMPLETE
   - ✅ Created `alex/cortex/claude.py` - Anthropic API client
   - ✅ Created `alex/agents/nodes/engineer.py` - engineering node
   - ✅ Updated graph routing for engineering intents
   - ✅ Implemented Gemini Pro fallback when Claude not configured
   - ⚠️ Add `ANTHROPIC_API_KEY` to `.env` for full Claude support

5. ~~**Recursive Summarization**~~ ✅ COMPLETE
   - ✅ Created `alex/memory/summarizer.py` with LLM-powered summarization
   - ✅ Daily summaries extract key topics from interactions
   - ✅ Weekly summaries aggregate daily themes
   - ✅ Monthly summaries provide strategic insights
   - ✅ Full pipeline: `/tasks/summarize_all` endpoint

6. ~~**Production Deployment**~~ ✅ COMPLETE
   - ✅ Dockerfile for Cloud Run (Python 3.12-slim, non-root user)
   - ✅ cloudbuild.yaml for CI/CD pipeline
   - ✅ Secret Manager configuration via setup script
   - ✅ .gcloudignore and .dockerignore for optimized builds
   - Run `./scripts/setup_gcp.sh` to deploy

7. ~~**Database Migration**~~ ✅ COMPLETE
   - ✅ Migrated from Neo4j to PostgreSQL with pgvector
   - ✅ All data and relationships preserved
   - ✅ Vector search working with cosine similarity

8. **Optional Enhancements**
   - ✅ Cloud Scheduler for automated summarization (COMPLETE)
   - Custom domain mapping
   - Cloud Monitoring alerts

## Troubleshooting

### Server won't start
```bash
# Check if port is in use
lsof -ti:8080 | xargs kill -9

# Check Python packages
python3 -c "import langgraph; import langchain; print('OK')"
```

### PostgreSQL connection fails
```bash
# Test connection directly
python3 -c "
import asyncpg
import asyncio

async def test():
    conn = await asyncpg.connect('postgresql://localhost:5432/alex')
    result = await conn.fetchval('SELECT 1')
    print(f'Connected: {result}')
    await conn.close()

asyncio.run(test())
"
```

### Chat returns error
- Check Generative Language API is enabled in GCP
- Check GOOGLE_API_KEY is set in .env
- Check server logs for specific error

## Key Configuration

### Gemini SDK (google-genai)
```python
# requirements.txt
google-genai>=1.0.0  # NOT google-generativeai (deprecated)

# Model names (config.py)
flash_model = "gemini-3-flash-preview"
pro_model = "gemini-3-pro-preview"
embedding_model = "text-embedding-004"
embedding_dimensions = 768  # text-embedding-004 outputs 768 dims
```

### PostgreSQL Vector Indexes (pgvector)
All vector columns configured for 768 dimensions (matching text-embedding-004):
- `interactions.embedding` - Interaction embeddings
- `concepts.embedding` - Concept embeddings
- `projects.embedding` - Project embeddings
- `daily_summaries.embedding` - Daily summary embeddings
- `weekly_summaries.embedding` - Weekly summary embeddings

### Model Routing
- complexity_score < 0.7 → Gemini Flash (fast, routine queries)
- complexity_score >= 0.7 → Gemini Pro (complex, in-depth analysis)
- Engineering intents → Claude Code (with Gemini Pro fallback)

### Claude Code Integration
```python
# requirements.txt
anthropic>=0.40.0

# .env (add this for full Claude support)
ANTHROPIC_API_KEY=your-api-key-here

# Supported engineering intents:
# - code_change: Implement new code or modify existing
# - refactor: Improve code structure
# - debug: Fix bugs and issues
# - test: Write tests
# - deploy: Deployment guidance

# Files:
# alex/cortex/claude.py - Anthropic API client
# alex/agents/nodes/engineer.py - Engineering node
```

### Claude Code Fallback Behavior
When `ANTHROPIC_API_KEY` is not configured:
1. Engineering tasks are routed to the engineer node
2. Engineer node detects missing API key
3. Falls back to Gemini Pro with engineering-specific prompts
4. Response indicates "gemini-3-pro-preview (fallback)" in metadata

### TastyTrade Brokerage Configuration
```python
# .env configuration
TASTY_SANDBOX_USERNAME=your-sandbox-email
TASTY_SANDBOX_PASSWORD=your-sandbox-password
TASTY_USE_SANDBOX=true  # Default: paper trading mode

# For production (real money) - use with caution!
TASTY_USERNAME=your-email
TASTY_PASSWORD=your-password
TASTY_USE_SANDBOX=false

# Files:
# alex/brokerage/tastytrade_client.py - Session management
# alex/brokerage/tastytrade_tools.py - Trading tools
# alex/agents/nodes/trade.py - Trade response node
# schema/migrations/003_add_trades_table.sql - Audit table

# Trade confirmation flow:
# 1. User: "Buy 100 shares of AAPL"
# 2. Alex calls place_order_dry_run() → returns trade_id
# 3. Alex presents: "Ready to BUY 100 AAPL @ market. Confirm?"
# 4. User: "Yes, confirm"
# 5. Alex calls confirm_trade(trade_id) → executes order
# 6. Trade logged to PostgreSQL trades table

# Session caching:
# Sessions cached at ~/.alex/tastytrade/session.json
# Automatically reused if valid, re-authenticated if expired
```

### Recursive Summarization
```python
# Summarization hierarchy:
# Interaction → DailySummary → WeeklySummary → MonthlySummary

# API Endpoints:
POST /api/v1/tasks/summarize_daily   # Summarize unsummarized days
POST /api/v1/tasks/summarize_weekly  # Aggregate into weekly themes
POST /api/v1/tasks/summarize_monthly # Aggregate into monthly insights
POST /api/v1/tasks/summarize_all     # Run full pipeline

# Debug Endpoints:
GET /api/v1/debug/summaries          # View all generated summaries
GET /api/v1/debug/unsummarized       # See what needs summarization

# Models used:
# - Daily/Weekly: Gemini Flash (fast, cost-effective)
# - Monthly: Gemini Pro (higher quality strategic insights)
```

## Production Deployment

### Live Service Details

| Property | Value |
|----------|-------|
| **Service URL** | https://alex-api-102313356909.us-central1.run.app |
| **Project ID** | `alex-ai-assistant-485218` |
| **Region** | `us-central1` |
| **Memory** | 1Gi |
| **CPU** | 1 |
| **Timeout** | 300s |
| **Deployed** | 2026-01-26 |

### Deployment Files
- ✅ `Dockerfile` - Container image (Python 3.12-slim, non-root user)
- ✅ `cloudbuild.yaml` - CI/CD pipeline for Cloud Build
- ✅ `.gcloudignore` - Excludes dev files from deployment
- ✅ `.dockerignore` - Optimizes Docker build context
- ✅ `scripts/setup_gcp.sh` - Interactive GCP setup script

### Secrets in Secret Manager (All Configured)
| Secret | Status |
|--------|--------|
| `GOOGLE_API_KEY` | ✅ Active |
| `POSTGRES_URI` | ✅ Active |
| `ANTHROPIC_API_KEY` | ✅ Active |

### Cloud Scheduler Jobs (Automated Summarization)
| Job | Schedule | Next Run |
|-----|----------|----------|
| `alex-daily-summary` | 2:00 AM UTC daily | Check scheduler |
| `alex-weekly-summary` | 3:00 AM UTC Mondays | Check scheduler |
| `alex-monthly-summary` | 4:00 AM UTC on 1st | Check scheduler |

### Quick Commands

```bash
# Health check
curl https://alex-api-102313356909.us-central1.run.app/api/v1/health

# Chat with Alex
curl -X POST https://alex-api-102313356909.us-central1.run.app/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Hello Alex"}'

# View logs
gcloud run services logs read alex-api --region us-central1

# Redeploy (after code changes)
gcloud run deploy alex-api --source . --region us-central1

# Manually trigger summarization
gcloud scheduler jobs run alex-daily-summary --location=us-central1

# List scheduler jobs
gcloud scheduler jobs list --location=us-central1
```

### Redeployment

```bash
# Option 1: Direct deployment
gcloud run deploy alex-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,POSTGRES_URI=POSTGRES_URI:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="APP_ENV=production,LOG_LEVEL=INFO"

# Option 2: Use Cloud Build (CI/CD)
gcloud builds submit --config cloudbuild.yaml
```

## Migration History

- **2026-01-25**: Initial implementation with Neo4j AuraDB
- **2026-02-11**: Migrated from Neo4j to PostgreSQL with pgvector
- **2026-02-11**: Added TastyTrade brokerage integration with trade confirmation flow
- **2026-02-11**: Added database sync (local → remote Neon) with daily launchd schedule
