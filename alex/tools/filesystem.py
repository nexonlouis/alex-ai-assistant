"""
File system tools for Alex AI Assistant.

Provides controlled file system access for self-modification capabilities.
All operations are logged and tracked in Neo4j for memory persistence.
"""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# Allowed paths for file operations (relative to project root)
ALLOWED_PATHS = [
    "alex/",
    "tests/",
    "web/",
    "schema/",
    "scripts/",
]

# Protected files that require explicit confirmation
PROTECTED_FILES = [
    "cloudbuild.yaml",
    "CLAUDE.md",
    "SESSION_STATE.md",
    "alex/config.py",
    "schema/neo4j_schema.cypher",
    ".env",
    ".env.example",
]

# File extensions allowed for modification
ALLOWED_EXTENSIONS = [
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt", ".rst",
    ".sh", ".bash",
    ".cypher", ".sql",
]


class FileSystemError(Exception):
    """Base exception for file system operations."""
    pass


class PermissionDeniedError(FileSystemError):
    """Raised when operation is not permitted."""
    pass


class FileNotFoundError(FileSystemError):
    """Raised when file doesn't exist."""
    pass


def _is_path_allowed(path: str) -> bool:
    """Check if path is within allowed directories."""
    try:
        resolved = (PROJECT_ROOT / path).resolve()
        # Ensure path is within project root
        resolved.relative_to(PROJECT_ROOT)

        # Check if path starts with any allowed prefix
        rel_path = str(resolved.relative_to(PROJECT_ROOT))
        return any(rel_path.startswith(allowed) for allowed in ALLOWED_PATHS)
    except ValueError:
        return False


def _is_protected_file(path: str) -> bool:
    """Check if file is in protected list."""
    try:
        resolved = (PROJECT_ROOT / path).resolve()
        rel_path = str(resolved.relative_to(PROJECT_ROOT))
        return rel_path in PROTECTED_FILES or any(
            rel_path.endswith(f"/{pf}") for pf in PROTECTED_FILES
        )
    except ValueError:
        return True  # If we can't resolve, treat as protected


def _has_allowed_extension(path: str) -> bool:
    """Check if file has an allowed extension."""
    return any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def _get_absolute_path(path: str) -> Path:
    """Convert relative path to absolute, validated path."""
    abs_path = (PROJECT_ROOT / path).resolve()

    # Security check: ensure we're still within project root
    try:
        abs_path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise PermissionDeniedError(f"Path escapes project root: {path}")

    return abs_path


async def read_file(path: str) -> dict[str, Any]:
    """
    Read contents of a file.

    Args:
        path: Relative path from project root

    Returns:
        Dict with file contents and metadata
    """
    logger.info("Reading file", path=path)

    if not _is_path_allowed(path):
        raise PermissionDeniedError(f"Path not in allowed directories: {path}")

    abs_path = _get_absolute_path(path)

    if not abs_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not abs_path.is_file():
        raise FileSystemError(f"Not a file: {path}")

    try:
        content = abs_path.read_text(encoding="utf-8")

        return {
            "success": True,
            "path": path,
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
            "lines": len(content.splitlines()),
        }
    except Exception as e:
        logger.error("Failed to read file", path=path, error=str(e))
        raise FileSystemError(f"Failed to read file: {e}")


async def write_file(
    path: str,
    content: str,
    create_dirs: bool = True,
    require_confirmation: bool = True,
) -> dict[str, Any]:
    """
    Write content to a file.

    Args:
        path: Relative path from project root
        content: Content to write
        create_dirs: Create parent directories if needed
        require_confirmation: If True and file is protected, raise error

    Returns:
        Dict with operation result
    """
    logger.info("Writing file", path=path, content_length=len(content))

    if not _is_path_allowed(path):
        raise PermissionDeniedError(f"Path not in allowed directories: {path}")

    if not _has_allowed_extension(path):
        raise PermissionDeniedError(f"File extension not allowed: {path}")

    if _is_protected_file(path) and require_confirmation:
        raise PermissionDeniedError(
            f"File is protected and requires explicit confirmation: {path}"
        )

    abs_path = _get_absolute_path(path)

    # Track if this is a new file or modification
    is_new = not abs_path.exists()
    old_content = None if is_new else abs_path.read_text(encoding="utf-8")

    try:
        if create_dirs:
            abs_path.parent.mkdir(parents=True, exist_ok=True)

        abs_path.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": path,
            "action": "created" if is_new else "modified",
            "size_bytes": len(content.encode("utf-8")),
            "lines": len(content.splitlines()),
            "previous_content": old_content,
        }
    except Exception as e:
        logger.error("Failed to write file", path=path, error=str(e))
        raise FileSystemError(f"Failed to write file: {e}")


async def list_directory(path: str = "", recursive: bool = False) -> dict[str, Any]:
    """
    List contents of a directory.

    Args:
        path: Relative path from project root (empty for root)
        recursive: If True, list all files recursively

    Returns:
        Dict with directory listing
    """
    logger.info("Listing directory", path=path, recursive=recursive)

    if path and not _is_path_allowed(path):
        raise PermissionDeniedError(f"Path not in allowed directories: {path}")

    abs_path = _get_absolute_path(path) if path else PROJECT_ROOT

    if not abs_path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    if not abs_path.is_dir():
        raise FileSystemError(f"Not a directory: {path}")

    try:
        items = []

        if recursive:
            for item in abs_path.rglob("*"):
                if item.is_file():
                    rel_path = str(item.relative_to(PROJECT_ROOT))
                    # Only include allowed paths
                    if _is_path_allowed(rel_path):
                        items.append({
                            "path": rel_path,
                            "type": "file",
                            "size": item.stat().st_size,
                        })
        else:
            for item in abs_path.iterdir():
                rel_path = str(item.relative_to(PROJECT_ROOT))
                # Only include allowed paths or check for directories
                if item.is_dir():
                    if any(rel_path.startswith(a.rstrip("/")) for a in ALLOWED_PATHS):
                        items.append({
                            "path": rel_path,
                            "type": "directory",
                        })
                elif _is_path_allowed(rel_path):
                    items.append({
                        "path": rel_path,
                        "type": "file",
                        "size": item.stat().st_size,
                    })

        return {
            "success": True,
            "path": path or ".",
            "items": sorted(items, key=lambda x: (x["type"] == "file", x["path"])),
            "count": len(items),
        }
    except Exception as e:
        logger.error("Failed to list directory", path=path, error=str(e))
        raise FileSystemError(f"Failed to list directory: {e}")


async def search_code(
    pattern: str,
    path: str = "",
    file_pattern: str = "*.py",
    max_results: int = 50,
) -> dict[str, Any]:
    """
    Search for pattern in code files.

    Args:
        pattern: Regex pattern to search for
        path: Directory to search in (relative to project root)
        file_pattern: Glob pattern for files to search
        max_results: Maximum number of results

    Returns:
        Dict with search results
    """
    logger.info("Searching code", pattern=pattern, path=path, file_pattern=file_pattern)

    search_path = PROJECT_ROOT / path if path else PROJECT_ROOT

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise FileSystemError(f"Invalid regex pattern: {e}")

    results = []
    files_searched = 0

    try:
        for file_path in search_path.rglob(file_pattern):
            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(PROJECT_ROOT))

            # Only search in allowed paths
            if not _is_path_allowed(rel_path):
                continue

            files_searched += 1

            try:
                content = file_path.read_text(encoding="utf-8")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        results.append({
                            "file": rel_path,
                            "line": i,
                            "content": line.strip()[:200],  # Limit line length
                        })

                        if len(results) >= max_results:
                            break
            except (UnicodeDecodeError, PermissionError):
                continue  # Skip binary or unreadable files

            if len(results) >= max_results:
                break

        return {
            "success": True,
            "pattern": pattern,
            "results": results,
            "count": len(results),
            "files_searched": files_searched,
            "truncated": len(results) >= max_results,
        }
    except Exception as e:
        logger.error("Search failed", pattern=pattern, error=str(e))
        raise FileSystemError(f"Search failed: {e}")


async def git_status() -> dict[str, Any]:
    """
    Get current git status.

    Returns:
        Dict with git status information
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        changes = []
        for line in result.stdout.strip().splitlines():
            if line:
                status = line[:2].strip()
                file_path = line[3:]
                changes.append({"status": status, "file": file_path})

        return {
            "success": True,
            "changes": changes,
            "has_changes": len(changes) > 0,
        }
    except Exception as e:
        logger.error("Git status failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


async def git_commit(message: str, files: list[str] | None = None) -> dict[str, Any]:
    """
    Commit changes to git.

    Args:
        message: Commit message
        files: Specific files to commit (None for all staged)

    Returns:
        Dict with commit result
    """
    logger.info("Committing changes", message=message, files=files)

    try:
        # Add files
        if files:
            for f in files:
                if not _is_path_allowed(f):
                    raise PermissionDeniedError(f"Cannot commit file outside allowed paths: {f}")
            subprocess.run(
                ["git", "add"] + files,
                cwd=PROJECT_ROOT,
                check=True,
                timeout=10,
            )
        else:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=PROJECT_ROOT,
                check=True,
                timeout=10,
            )

        # Commit with co-author
        full_message = f"{message}\n\nCo-Authored-By: Alex AI <alex@ai-assistant.local>"
        result = subprocess.run(
            ["git", "commit", "-m", full_message],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            if "nothing to commit" in result.stdout.lower():
                return {
                    "success": True,
                    "message": "Nothing to commit",
                    "sha": None,
                }
            raise FileSystemError(f"Commit failed: {result.stderr}")

        # Get commit SHA
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return {
            "success": True,
            "message": message,
            "sha": sha_result.stdout.strip(),
        }
    except subprocess.TimeoutExpired:
        raise FileSystemError("Git operation timed out")
    except Exception as e:
        logger.error("Git commit failed", error=str(e))
        raise FileSystemError(f"Git commit failed: {e}")


# Tool definitions for function calling
TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the Alex codebase. Use this to understand existing code before making changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file (e.g., 'alex/agents/graph.py')",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Use this to create new files or modify existing ones. Always read the file first before modifying.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Complete content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories. Use this to explore the codebase structure.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to directory (empty for project root)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "If true, list all files recursively",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in code files. Use regex patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (empty for entire project)",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern for files (default: *.py)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "git_status",
        "description": "Get the current git status showing modified, added, and deleted files.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "git_commit",
        "description": "Commit changes to git with a descriptive message. Use after making file changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message describing the changes",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific files to commit (optional, commits all if not specified)",
                },
            },
            "required": ["message"],
        },
    },
]


async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a tool by name with given arguments.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        Tool execution result
    """
    tools = {
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
        "search_code": search_code,
        "git_status": git_status,
        "git_commit": git_commit,
    }

    if name not in tools:
        return {"success": False, "error": f"Unknown tool: {name}"}

    try:
        result = await tools[name](**arguments)
        return result
    except (PermissionDeniedError, FileNotFoundError, FileSystemError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("Tool execution failed", tool=name, error=str(e))
        return {"success": False, "error": f"Tool execution failed: {e}"}
