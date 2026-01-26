"""
Configuration management for Alex AI Assistant.

Loads settings from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Alex AI Assistant"
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    port: int = 8080

    # Neo4j Configuration
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: SecretStr = Field(default=SecretStr("password"))
    neo4j_database: str = Field(default="neo4j")

    # Google AI (Gemini) Configuration
    google_api_key: SecretStr | None = Field(default=None)
    google_project_id: str | None = Field(default=None)
    google_region: str = Field(default="us-central1")

    # Model Configuration
    # Gemini 3 models (latest via google-genai SDK)
    flash_model: str = Field(default="gemini-3-flash-preview")
    pro_model: str = Field(default="gemini-3-pro-preview")
    complexity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # Anthropic (Claude Code) Configuration
    anthropic_api_key: SecretStr | None = Field(default=None)

    # Memory Configuration
    embedding_model: str = Field(default="text-embedding-004")
    embedding_dimensions: int = Field(default=768)  # Gemini text-embedding-004 uses 768 dims
    max_context_tokens: int = Field(default=100000)

    # Summarization
    summarization_batch_size: int = Field(default=100)
    daily_summary_hour: int = Field(default=2)  # 2 AM

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience access
settings = get_settings()
