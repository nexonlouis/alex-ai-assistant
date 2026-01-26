"""
Engineering node for Alex AI Assistant.

Handles engineering tasks by delegating to Claude Code (Anthropic).
"""

import time
from typing import Any

import structlog
from langchain_core.messages import AIMessage

from alex.agents.state import AlexState, get_last_user_message
from alex.cortex.claude import generate_engineering_response, analyze_and_implement

logger = structlog.get_logger()


def _build_memory_context_string(state: AlexState) -> str | None:
    """Build a context string from memory for Claude."""
    memory_context = state.get("memory_context")
    if not memory_context:
        return None

    context_parts = []

    # Add daily summary if available
    if memory_context.daily_summary:
        context_parts.append(f"Today's context: {memory_context.daily_summary}")

    # Add weekly summary for broader context
    if memory_context.weekly_summary:
        context_parts.append(f"This week: {memory_context.weekly_summary}")

    # Add relevant past interactions
    if memory_context.relevant_interactions:
        context_parts.append("\nRelevant past discussions:")
        for interaction in memory_context.relevant_interactions[:3]:
            user_msg = interaction.get("user_message", "")[:300]
            context_parts.append(f"- User asked: {user_msg}")

    # Add related concepts
    if memory_context.related_concepts:
        concepts = ", ".join(memory_context.related_concepts[:5])
        context_parts.append(f"\nRelated topics: {concepts}")

    # Add related projects
    if memory_context.related_projects:
        projects = ", ".join(memory_context.related_projects[:3])
        context_parts.append(f"Related projects: {projects}")

    return "\n".join(context_parts) if context_parts else None


async def respond_engineer(state: AlexState) -> dict[str, Any]:
    """
    Handle engineering tasks using Claude Code.

    This node:
    1. Extracts the engineering request from state
    2. Builds context from memory
    3. Delegates to Claude for implementation
    4. Returns the response

    Engineering intents handled:
    - code_change: Implement new code or modify existing
    - refactor: Improve code structure
    - debug: Fix bugs and issues
    - test: Write tests
    - deploy: Deployment guidance
    """
    start_time = time.time()
    metadata = state.get("metadata")
    intent = metadata.intent if metadata else "code_change"

    logger.info(
        "Engineering node processing",
        session_id=state.get("session_id"),
        intent=intent,
    )

    try:
        user_message = get_last_user_message(state)
        if not user_message:
            raise ValueError("No user message found")

        # Build context from memory
        context_str = _build_memory_context_string(state)

        # Generate response using Claude
        response = await generate_engineering_response(
            task_description=user_message,
            context=context_str,
            intent=intent,
        )

        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)

        # Update metadata
        if metadata:
            metadata.model_used = "claude-sonnet-4-20250514"
            metadata.latency_ms = latency_ms

        logger.info(
            "Engineering response generated",
            intent=intent,
            latency_ms=latency_ms,
            response_length=len(response),
        )

        return {
            "messages": [AIMessage(content=response)],
            "current_cortex": "claude_code",
            "processing_stage": "engineer",
            "metadata": metadata,
        }

    except ValueError as e:
        # Handle configuration errors (missing API key) - fallback to Gemini Pro
        logger.warning(
            "Claude not configured, falling back to Gemini Pro",
            error=str(e),
        )

        # Import here to avoid circular imports
        from alex.cortex.pro import generate_pro_response

        # Use Gemini Pro as fallback for engineering tasks
        engineering_prompt = f"""You are handling an engineering task. Provide complete, working code with:
- Proper error handling
- Type hints (for Python)
- Clear comments for complex logic
- Security considerations

Task: {user_message}"""

        try:
            fallback_response = await generate_pro_response(
                prompt=engineering_prompt,
                system_instruction="You are an expert software engineer. Provide production-ready code.",
            )

            latency_ms = int((time.time() - start_time) * 1000)
            if metadata:
                metadata.model_used = "gemini-3-pro-preview (fallback)"
                metadata.latency_ms = latency_ms

            return {
                "messages": [AIMessage(content=fallback_response)],
                "current_cortex": "pro",
                "processing_stage": "engineer_fallback",
                "metadata": metadata,
            }
        except Exception as fallback_error:
            logger.error("Fallback to Pro also failed", error=str(fallback_error))
            return {
                "messages": [AIMessage(content=(
                    "I apologize, but I'm unable to process engineering tasks at the moment. "
                    "Neither Claude Code nor Gemini Pro are available. "
                    "Please check your API key configurations."
                ))],
                "current_cortex": "flash",
                "processing_stage": "error",
                "error": str(e),
            }

    except Exception as e:
        logger.error("Engineering node failed", error=str(e))

        # Provide a helpful error message
        error_response = (
            f"I encountered an issue while processing this engineering request: {str(e)}\n\n"
            "I can still help with:\n"
            "- General coding questions (will use Gemini)\n"
            "- Architecture discussions\n"
            "- Code review suggestions\n\n"
            "Would you like me to try a different approach?"
        )

        return {
            "messages": [AIMessage(content=error_response)],
            "current_cortex": "flash",
            "processing_stage": "error",
            "error": str(e),
        }


async def analyze_engineering_request(state: AlexState) -> dict[str, Any]:
    """
    Analyze an engineering request before implementation.

    This is an optional analysis step that can be used for complex tasks
    to first understand and plan before implementing.
    """
    metadata = state.get("metadata")

    try:
        user_message = get_last_user_message(state)
        if not user_message:
            raise ValueError("No user message found")

        # Build memory context dict for analysis
        memory_context = state.get("memory_context")
        memory_dict = None
        if memory_context:
            memory_dict = {
                "daily_summary": memory_context.daily_summary,
                "weekly_summary": memory_context.weekly_summary,
                "relevant_interactions": memory_context.relevant_interactions,
            }

        # Analyze and get implementation
        result = await analyze_and_implement(
            request=user_message,
            memory_context=memory_dict,
        )

        response = result.get("implementation", "Unable to analyze request.")

        if metadata:
            metadata.model_used = result.get("model", "claude-sonnet-4-20250514")

        return {
            "messages": [AIMessage(content=response)],
            "current_cortex": "claude_code",
            "processing_stage": "engineer_analyze",
            "tool_outputs": {"engineering_analysis": result},
            "metadata": metadata,
        }

    except Exception as e:
        logger.error("Engineering analysis failed", error=str(e))
        return {
            "messages": [AIMessage(content=f"Analysis failed: {str(e)}")],
            "processing_stage": "error",
            "error": str(e),
        }
