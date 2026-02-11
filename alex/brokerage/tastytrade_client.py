"""
TastyTrade client for Alex AI Assistant.

Handles session management with direct API calls to TastyTrade.
Supports both sandbox (paper trading) and production modes.

Note: TastyTrade requires 2FA for production accounts. Session tokens are
cached to avoid repeated 2FA prompts.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

from alex.config import settings

logger = structlog.get_logger()

# API endpoints
SANDBOX_API_URL = "https://api.cert.tastyworks.com"
PRODUCTION_API_URL = "https://api.tastyworks.com"

# Session cache file location
SESSION_CACHE_DIR = Path.home() / ".alex" / "tastytrade"
SESSION_CACHE_FILE = SESSION_CACHE_DIR / "session.json"


@dataclass
class TastyTradeSession:
    """Represents an authenticated TastyTrade session."""

    session_token: str
    remember_token: str | None
    user_id: str
    email: str
    is_sandbox: bool

    @property
    def api_url(self) -> str:
        """Get the appropriate API URL."""
        return SANDBOX_API_URL if self.is_sandbox else PRODUCTION_API_URL

    @property
    def headers(self) -> dict[str, str]:
        """Get headers for authenticated requests."""
        return {
            "Authorization": self.session_token,
            "Content-Type": "application/json",
        }


# Cached session instance
_session: TastyTradeSession | None = None


def _load_cached_session() -> TastyTradeSession | None:
    """Load session from cache file if valid."""
    if not SESSION_CACHE_FILE.exists():
        return None

    try:
        with open(SESSION_CACHE_FILE) as f:
            data = json.load(f)

        # Check if it's for the right mode
        is_sandbox = settings.tasty_use_sandbox
        if data.get("is_sandbox") != is_sandbox:
            return None

        session = TastyTradeSession(
            session_token=data["session_token"],
            remember_token=data.get("remember_token"),
            user_id=data["user_id"],
            email=data["email"],
            is_sandbox=data["is_sandbox"],
        )

        # Validate the session is still active
        if _validate_session(session):
            logger.info("Loaded cached TastyTrade session", email=session.email)
            return session

    except (json.JSONDecodeError, KeyError) as e:
        logger.debug("Failed to load cached session", error=str(e))

    return None


def _save_session(session: TastyTradeSession):
    """Save session to cache file."""
    SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "session_token": session.session_token,
        "remember_token": session.remember_token,
        "user_id": session.user_id,
        "email": session.email,
        "is_sandbox": session.is_sandbox,
    }

    with open(SESSION_CACHE_FILE, "w") as f:
        json.dump(data, f)

    # Set restrictive permissions (owner read/write only)
    os.chmod(SESSION_CACHE_FILE, 0o600)


def _validate_session(session: TastyTradeSession) -> bool:
    """Check if a session is still valid by making a test request."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{session.api_url}/customers/me",
                headers=session.headers,
            )
            return response.status_code == 200
    except Exception:
        return False


def _create_session_with_credentials(
    username: str,
    password: str,
    is_sandbox: bool,
    remember_token: str | None = None,
) -> TastyTradeSession:
    """
    Create a new session using username/password.

    Args:
        username: TastyTrade username
        password: TastyTrade password
        is_sandbox: Whether to use sandbox API
        remember_token: Optional remember token to skip 2FA

    Returns:
        Authenticated session

    Raises:
        ValueError: If authentication fails or 2FA is required
    """
    api_url = SANDBOX_API_URL if is_sandbox else PRODUCTION_API_URL

    payload: dict[str, Any] = {
        "login": username,
        "password": password,
    }

    if remember_token:
        payload["remember-token"] = remember_token

    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{api_url}/sessions", json=payload)

        if response.status_code == 201:
            data = response.json().get("data", {})
            user = data.get("user", {})

            session = TastyTradeSession(
                session_token=data.get("session-token", ""),
                remember_token=data.get("remember-token"),
                user_id=str(user.get("id", "")),
                email=user.get("email", username),
                is_sandbox=is_sandbox,
            )

            _save_session(session)
            return session

        elif response.status_code == 403:
            error_data = response.json().get("error", {})
            error_code = error_data.get("code", "")

            if error_code == "invalid_credentials" and "two factor" in error_data.get(
                "message", ""
            ).lower():
                raise ValueError(
                    "Two-factor authentication required. "
                    "Please log in via the TastyTrade website/app first to generate a remember token, "
                    "or set TASTY_REMEMBER_TOKEN in your environment."
                )

            raise ValueError(f"Authentication failed: {error_data.get('message', 'Unknown error')}")

        else:
            raise ValueError(f"Authentication failed with status {response.status_code}")


def get_session() -> TastyTradeSession:
    """
    Get or create a cached TastyTrade session.

    Returns the sandbox session if tasty_use_sandbox is True (default),
    otherwise returns the production session.

    Returns:
        Active TastyTrade session

    Raises:
        ValueError: If credentials are not configured or authentication fails
    """
    global _session

    if _session is not None:
        return _session

    # Try to load cached session first
    _session = _load_cached_session()
    if _session is not None:
        return _session

    # Create new session
    if settings.tasty_use_sandbox:
        if not settings.tasty_sandbox_username or not settings.tasty_sandbox_password:
            raise ValueError(
                "TastyTrade sandbox credentials not configured. "
                "Set TASTY_SANDBOX_USERNAME and TASTY_SANDBOX_PASSWORD."
            )
        username = settings.tasty_sandbox_username
        password = settings.tasty_sandbox_password.get_secret_value()
        is_sandbox = True
        mode = "sandbox"
    else:
        if not settings.tasty_username or not settings.tasty_password:
            raise ValueError(
                "TastyTrade production credentials not configured. "
                "Set TASTY_USERNAME and TASTY_PASSWORD."
            )
        username = settings.tasty_username
        password = settings.tasty_password.get_secret_value()
        is_sandbox = False
        mode = "production"

    logger.info("Creating TastyTrade session", mode=mode)

    # Check for remember token (to bypass 2FA)
    remember_token = os.environ.get("TASTY_REMEMBER_TOKEN")

    _session = _create_session_with_credentials(
        username=username,
        password=password,
        is_sandbox=is_sandbox,
        remember_token=remember_token,
    )

    logger.info("TastyTrade session created", mode=mode, email=_session.email)

    return _session


def get_accounts() -> list[dict[str, Any]]:
    """
    Get all trading accounts for the authenticated user.

    Returns:
        List of account dictionaries
    """
    session = get_session()

    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{session.api_url}/customers/me/accounts",
            headers=session.headers,
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to get accounts: {response.status_code}")

        data = response.json()
        accounts = data.get("data", {}).get("items", [])

        logger.info("Retrieved accounts", count=len(accounts))
        return accounts


def get_primary_account() -> dict[str, Any]:
    """
    Get the primary (first) trading account.

    Returns:
        Account dictionary

    Raises:
        ValueError: If no accounts are available
    """
    accounts = get_accounts()

    if not accounts:
        raise ValueError("No trading accounts found for this user.")

    account = accounts[0].get("account", accounts[0])
    account_number = account.get("account-number", "")

    # Mask account number for privacy
    masked = account_number[:4] + "****" if account_number else None
    logger.info(
        "Using primary account",
        account_number=masked,
        nickname=account.get("nickname"),
    )

    return account


def close_session():
    """Close the active session and clear the cache."""
    global _session

    if _session is not None:
        # Optionally delete the session on the server
        try:
            with httpx.Client(timeout=10.0) as client:
                client.delete(
                    f"{_session.api_url}/sessions",
                    headers=_session.headers,
                )
        except Exception:
            pass

        logger.info("Closing TastyTrade session")
        _session = None

    # Clear cache file
    if SESSION_CACHE_FILE.exists():
        SESSION_CACHE_FILE.unlink()


def is_sandbox_mode() -> bool:
    """Check if currently operating in sandbox (paper trading) mode."""
    return settings.tasty_use_sandbox
