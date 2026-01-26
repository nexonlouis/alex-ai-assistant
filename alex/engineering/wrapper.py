"""
Claude Code wrapper for Alex AI Assistant.

Provides a headless interface to Claude Code CLI for autonomous
software engineering tasks.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog

from alex.config import settings

logger = structlog.get_logger()


class ClaudeCodeWrapper:
    """
    Headless wrapper for Claude Code CLI.

    Executes Claude Code in non-interactive mode for:
    - Code modifications
    - Test execution
    - Refactoring
    - Bug fixes
    """

    def __init__(
        self,
        working_dir: str | Path | None = None,
        timeout: int = 600,
    ):
        """
        Initialize the Claude Code wrapper.

        Args:
            working_dir: Working directory for code operations
            timeout: Maximum execution time in seconds
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.timeout = timeout

    async def invoke(
        self,
        prompt: str,
        context_files: list[str] | None = None,
        allow_edits: bool = False,
    ) -> dict[str, Any]:
        """
        Execute Claude Code with a prompt.

        Args:
            prompt: The task description for Claude Code
            context_files: Optional list of files to include as context
            allow_edits: Whether to allow file modifications

        Returns:
            Result dictionary with status and output
        """
        # Build command
        cmd = ["claude", "--print", prompt]

        if not allow_edits:
            cmd.append("--readonly")

        logger.info(
            "Invoking Claude Code",
            prompt_length=len(prompt),
            working_dir=str(self.working_dir),
            allow_edits=allow_edits,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "ANTHROPIC_API_KEY": settings.anthropic_api_key.get_secret_value()
                    if settings.anthropic_api_key
                    else "",
                },
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            result = {
                "status": "success" if process.returncode == 0 else "error",
                "return_code": process.returncode,
                "output": stdout.decode("utf-8"),
                "error": stderr.decode("utf-8") if stderr else None,
            }

            logger.info(
                "Claude Code completed",
                status=result["status"],
                return_code=result["return_code"],
                output_length=len(result["output"]),
            )

            return result

        except asyncio.TimeoutError:
            logger.error("Claude Code timed out", timeout=self.timeout)
            return {
                "status": "error",
                "return_code": -1,
                "output": "",
                "error": f"Operation timed out after {self.timeout} seconds",
            }

        except FileNotFoundError:
            logger.error("Claude Code CLI not found")
            return {
                "status": "error",
                "return_code": -1,
                "output": "",
                "error": "Claude Code CLI not installed. Run: npm install -g @anthropic-ai/claude-code",
            }

        except Exception as e:
            logger.error("Claude Code failed", error=str(e))
            return {
                "status": "error",
                "return_code": -1,
                "output": "",
                "error": str(e),
            }

    async def analyze_code(self, file_path: str, question: str) -> dict[str, Any]:
        """
        Analyze code and answer a question about it.

        Args:
            file_path: Path to the file to analyze
            question: Question about the code

        Returns:
            Analysis result
        """
        prompt = f"""Analyze the file at {file_path} and answer this question:

{question}

Provide a clear, technical answer."""

        return await self.invoke(prompt, context_files=[file_path], allow_edits=False)

    async def fix_bug(
        self,
        description: str,
        file_path: str | None = None,
        test_command: str | None = None,
    ) -> dict[str, Any]:
        """
        Fix a bug in the codebase.

        Args:
            description: Description of the bug
            file_path: Optional specific file with the bug
            test_command: Optional command to verify the fix

        Returns:
            Fix result
        """
        prompt = f"""Fix this bug:

{description}

{"File: " + file_path if file_path else ""}
{"After fixing, verify with: " + test_command if test_command else ""}

Make minimal changes to fix the issue."""

        return await self.invoke(
            prompt,
            context_files=[file_path] if file_path else None,
            allow_edits=True,
        )

    async def run_tests(self, test_path: str = "tests/") -> dict[str, Any]:
        """
        Run tests and report results.

        Args:
            test_path: Path to test files

        Returns:
            Test results
        """
        prompt = f"""Run the tests at {test_path} and provide a summary of:
1. Total tests run
2. Passed tests
3. Failed tests (with brief descriptions)
4. Any recommendations"""

        return await self.invoke(prompt, allow_edits=False)
