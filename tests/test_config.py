"""Tests for configuration module."""

import pytest
from alex.config import Settings, get_settings


def test_settings_defaults():
    """Test that settings have sensible defaults."""
    settings = Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
    )

    assert settings.app_env == "development"
    assert settings.port == 8080
    assert settings.flash_model == "gemini-2.0-flash"
    assert settings.complexity_threshold == 0.7


def test_settings_is_development():
    """Test development mode detection."""
    settings = Settings(
        app_env="development",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
    )
    assert settings.is_development is True
    assert settings.is_production is False


def test_settings_is_production():
    """Test production mode detection."""
    settings = Settings(
        app_env="production",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
    )
    assert settings.is_development is False
    assert settings.is_production is True


def test_get_settings_cached():
    """Test that get_settings returns cached instance."""
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2
