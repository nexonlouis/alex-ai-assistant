"""
Self-modification node for Alex AI Assistant.

Enables Alex to read, modify, and manage its own codebase with
full memory tracking of all changes.
"""

import json
import time
from typing import Any
from uuid import uuid4

import structlog
from google import genai
from langchain_core.messages import AIMessage

from alex.agents.state import AlexState, get_last_user_message
from alex.config import settings
from alex.cortex.flash import get_client
from alex.memory.postgres_store import PostgresStore
from alex.tools.filesystem import (
    TOOL_DEFINITIONS,
    execute_tool,
    PROJECT_ROOT,
)

logger = structlog.get_logger()

# System prompt for self-modification tasks
SELF_MODIFY_PROMPT = """You are Alex, an AI assistant with the ability to read and modify your own codebase.

You have access to file system tools to:
- Read files in your codebase
- Write/modify files
- Search for code patterns
- List directories
- Commit changes to git

IMPORTANT GUIDELINES:
1. ALWAYS read a file before modifying it
2. Make minimal, focused changes
3. Follow existing code patterns and style
4. Add appropriate error handling
5. Include docstrings for new functions
6. Test your changes mentally before applying
7. Commit changes with clear, descriptive messages

Your codebase is located at: {project_root}

Key directories:
- alex/agents/ - LangGraph nodes and state
- alex/cortex/ - LLM integrations (Gemini, Claude)
- alex/memory/ - Neo4j knowledge graph
- alex/tools/ - File system tools
- alex/api/ - FastAPI endpoints
- tests/ - Test files
- web/ - Web UI

When making changes, explain your reasoning clearly.
"""

# Convert tool definitions to Gemini format
def _get_gemini_tools() -> list:
    """Convert tool definitions to Gemini function declarations."""
    declarations = []
    for tool in TOOL_DEFINITIONS:
        declarations.append(genai.types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=tool["parameters"],
        ))
    return [genai.types.Tool(function_declarations=declarations)]


async def respond_self_modify(state: AlexState) -> dict[str, Any]:
    """
    Handle self-modification requests using file system tools.

    This node:
    1. Understands the modification request
    2. Uses tools to explore and modify the codebase
    3. Tracks all changes in Neo4j memory
    4. Optionally commits changes to git

    Args:
        state: Current agent state

    Returns:
        Updated state with response
    """
    start_time = time.time()
    metadata = state.get("metadata")
    session_id = state.get("session_id")
    user_id = state.get("user_id", "primary_user")

    logger.info(
        "Self-modification node processing",
        session_id=session_id,
    )

    try:
        user_message = get_last_user_message(state)
        if not user_message:
            raise ValueError("No user message found")

        # Build system prompt
        system_prompt = SELF_MODIFY_PROMPT.format(project_root=PROJECT_ROOT)

        # Initialize Gemini client with tools
        client = get_client()
        tools = _get_gemini_tools()

        # Build conversation for context
        contents = [
            genai.types.Content(
                role="user",
                parts=[genai.types.Part(text=f"{system_prompt}\n\nUser request: {user_message}")]
            )
        ]

        # Track files modified and tool calls
        files_modified = []
        tool_results = []
        max_iterations = 10
        iteration = 0

        # Agentic loop with tool calling
        while iteration < max_iterations:
            iteration += 1

            response = await client.aio.models.generate_content(
                model=settings.flash_model,
                contents=contents,
                config=genai.types.GenerateContentConfig(
                    tools=tools,
                    temperature=0.2,  # Lower temperature for code
                ),
            )

            # Check if we have function calls
            if response.candidates and response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts
                has_function_call = any(
                    hasattr(part, 'function_call') and part.function_call
                    for part in parts
                )

                if has_function_call:
                    # Process function calls
                    function_responses = []

                    for part in parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            func_call = part.function_call
                            func_name = func_call.name
                            func_args = dict(func_call.args) if func_call.args else {}

                            logger.info(
                                "Executing tool",
                                tool=func_name,
                                args=func_args,
                            )

                            # Execute the tool
                            result = await execute_tool(func_name, func_args)
                            tool_results.append({
                                "tool": func_name,
                                "args": func_args,
                                "result": result,
                            })

                            # Track file modifications
                            if func_name == "write_file" and result.get("success"):
                                files_modified.append(func_args.get("path"))

                            function_responses.append(
                                genai.types.Part(
                                    function_response=genai.types.FunctionResponse(
                                        name=func_name,
                                        response={"result": json.dumps(result, default=str)},
                                    )
                                )
                            )

                    # Add assistant's response and function results to conversation
                    contents.append(response.candidates[0].content)
                    contents.append(genai.types.Content(
                        role="user",
                        parts=function_responses,
                    ))

                    # Continue the loop for more tool calls
                    continue

            # No more function calls, we have the final response
            break

        # Extract final text response
        final_response = ""
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    final_response += part.text

        # Store code changes in memory if files were modified
        if files_modified:
            graph_store = PostgresStore()
            change_id = str(uuid4())

            # Extract description from the response or user message
            description = f"Modified files based on request: {user_message[:200]}"

            await graph_store.store_code_change(
                change_id=change_id,
                user_id=user_id,
                files_modified=files_modified,
                description=description,
                reasoning=user_message,
                change_type="feature",  # Could be inferred from intent
                commit_sha=None,  # Will be set if committed
            )

            logger.info(
                "Code changes recorded in memory",
                change_id=change_id,
                files=files_modified,
            )

        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)

        # Update metadata
        if metadata:
            metadata.model_used = settings.flash_model
            metadata.latency_ms = latency_ms

        # Build response summary
        if files_modified:
            final_response += f"\n\n**Files modified:** {', '.join(files_modified)}"

        logger.info(
            "Self-modification complete",
            files_modified=len(files_modified),
            tool_calls=len(tool_results),
            latency_ms=latency_ms,
        )

        return {
            "messages": [AIMessage(content=final_response)],
            "current_cortex": "self_modify",
            "processing_stage": "self_modify",
            "tool_outputs": {
                "files_modified": files_modified,
                "tool_results": tool_results,
            },
            "metadata": metadata,
        }

    except Exception as e:
        logger.error("Self-modification failed", error=str(e))

        error_response = (
            f"I encountered an error while trying to modify the codebase: {str(e)}\n\n"
            "This could be due to:\n"
            "- File permission issues\n"
            "- Protected file access\n"
            "- Invalid file paths\n\n"
            "Please check the request and try again."
        )

        return {
            "messages": [AIMessage(content=error_response)],
            "current_cortex": "flash",
            "processing_stage": "error",
            "error": str(e),
        }


async def list_recent_changes(state: AlexState) -> dict[str, Any]:
    """
    List recent code changes made by Alex.

    This allows Alex to recall and report on its own modifications.
    """
    try:
        graph_store = PostgresStore()
        changes = await graph_store.get_recent_code_changes(limit=10)

        if not changes:
            response = "I haven't made any code changes yet that I can recall."
        else:
            response = "Here are my recent code changes:\n\n"
            for change in changes:
                response += f"**{change['timestamp'][:10]}** - {change['description']}\n"
                response += f"  Files: {', '.join(change['files_modified'])}\n"
                if change['commit_sha']:
                    response += f"  Commit: {change['commit_sha'][:8]}\n"
                response += "\n"

        return {
            "messages": [AIMessage(content=response)],
            "processing_stage": "recall_changes",
        }

    except Exception as e:
        logger.error("Failed to list changes", error=str(e))
        return {
            "messages": [AIMessage(content=f"Error recalling changes: {str(e)}")],
            "processing_stage": "error",
            "error": str(e),
        }
