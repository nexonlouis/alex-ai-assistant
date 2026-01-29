"""
Tools package for Alex AI Assistant.

Provides file system tools for self-modification capabilities.
"""

from alex.tools.filesystem import (
    TOOL_DEFINITIONS,
    execute_tool,
    read_file,
    write_file,
    list_directory,
    search_code,
    git_status,
    git_commit,
    FileSystemError,
    PermissionDeniedError,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "execute_tool",
    "read_file",
    "write_file",
    "list_directory",
    "search_code",
    "git_status",
    "git_commit",
    "FileSystemError",
    "PermissionDeniedError",
]
