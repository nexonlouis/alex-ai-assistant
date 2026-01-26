"""
Main entry point for Alex AI Assistant.

FastAPI application that exposes the Alex agent via REST API.
"""

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alex import __version__
from alex.api.routes import router
from alex.config import settings
from alex.memory.graph_store import GraphStore

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.is_production else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown tasks.
    """
    # Startup
    logger.info(
        "Starting Alex AI Assistant",
        version=__version__,
        environment=settings.app_env,
    )

    # Initialize Neo4j connection
    try:
        await GraphStore.get_driver()
        logger.info("Neo4j connection established")
    except Exception as e:
        logger.error("Failed to connect to Neo4j", error=str(e))
        # Continue anyway - some endpoints may still work

    yield

    # Shutdown
    logger.info("Shutting down Alex AI Assistant")
    await GraphStore.close()


# Create FastAPI application
app = FastAPI(
    title="Alex AI Assistant",
    description="Autonomous, self-reflective AI assistant with temporal knowledge graph memory",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Alex AI Assistant",
        "version": __version__,
        "status": "running",
        "docs": "/docs",
    }


def run():
    """Run the application using uvicorn."""
    import uvicorn

    uvicorn.run(
        "alex.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
