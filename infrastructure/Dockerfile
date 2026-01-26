# Alex AI Assistant - Docker Image
# Multi-stage build for smaller final image

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir build && \
    pip wheel --no-cache-dir --wheel-dir /wheels -e .

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI (optional, for engineering tasks)
# RUN curl -fsSL https://claude.ai/install.sh | sh

# Copy wheels from builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code
COPY alex/ ./alex/
COPY CLAUDE.md .
COPY tools.yaml* ./

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV APP_ENV=production

# Create non-root user
RUN useradd -m -u 1000 alex
USER alex

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# Run application
EXPOSE ${PORT}
CMD ["python", "-m", "alex.main"]
