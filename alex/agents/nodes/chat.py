"""
Chat response nodes for Alex AI Assistant.

Implements the dual-cortex response generation:
- Flash: Fast, cost-effective responses for routine queries
- Pro: Deep reasoning for complex tasks
"""

import time
from typing import Any

from google import genai
import structlog

from alex.agents.state import AlexState, get_last_user_message
from alex.cortex.flash import get_client, get_flash_model
from alex.cortex.pro import get_pro_model
from alex.config import settings
from langchain_core.messages import HumanMessage, AIMessage

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are Alex, an intelligent AI assistant with persistent memory.

You have access to your memory context which includes:
- Today's summary and recent interactions
- Relevant past conversations
- Related concepts and projects you've discussed

Use this context naturally in your responses. Reference past discussions when relevant,
but don't force connections if they're not useful.

Key traits:
- Helpful and thorough, but concise
- Technical expertise, especially in software and AI
- Self-aware of your own architecture and capabilities
- Honest about limitations and uncertainties

Current context:
{memory_context}
"""


def format_memory_context(state: AlexState) -> str:
    """Format memory context for inclusion in the prompt."""
    ctx = state.get("memory_context")
    if not ctx:
        return "No specific context available."

    parts = []

    if ctx.daily_summary:
        parts.append(f"Today's Summary:\n{ctx.daily_summary}")

    if ctx.relevant_interactions:
        parts.append("Relevant Past Interactions:")
        for interaction in ctx.relevant_interactions[:3]:
            user_msg = interaction.get("user_message", "")[:200]
            parts.append(f"  - User asked: {user_msg}...")

    if ctx.related_concepts:
        parts.append(f"Related Concepts: {', '.join(ctx.related_concepts[:5])}")

    if ctx.related_projects:
        parts.append(f"Related Projects: {', '.join(ctx.related_projects[:3])}")

    return "\n\n".join(parts) if parts else "No specific context available."


def build_conversation_contents(state: AlexState, system_prompt: str) -> list:
    """Build conversation contents for the Gemini API."""
    contents = []

    # Add conversation history
    state_messages = state.get("messages", [])
    for msg in state_messages[-10:]:  # Last 10 messages for context
        if isinstance(msg, HumanMessage):
            contents.append(genai.types.Content(
                role="user",
                parts=[genai.types.Part(text=msg.content)]
            ))
        elif isinstance(msg, AIMessage):
            contents.append(genai.types.Content(
                role="model",
                parts=[genai.types.Part(text=msg.content)]
            ))
        elif isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                contents.append(genai.types.Content(
                    role="user",
                    parts=[genai.types.Part(text=content)]
                ))
            elif role == "assistant":
                contents.append(genai.types.Content(
                    role="model",
                    parts=[genai.types.Part(text=content)]
                ))

    # If the last message is from user, prepend system context
    if contents and contents[-1].role == "user":
        # Augment the last user message with system context
        last_content = contents[-1]
        original_text = last_content.parts[0].text if last_content.parts else ""
        augmented_text = f"{system_prompt}\n\nUser: {original_text}"
        contents[-1] = genai.types.Content(
            role="user",
            parts=[genai.types.Part(text=augmented_text)]
        )

    return contents


async def respond_flash(state: AlexState) -> dict[str, Any]:
    """
    Generate response using Gemini Flash (Basal Cortex).

    Used for:
    - Routine conversations
    - Simple questions
    - Low-complexity tasks
    """
    metadata = state.get("metadata")
    logger.info(
        "Generating Flash response",
        session_id=state.get("session_id"),
        intent=metadata.intent if metadata else None,
    )

    start_time = time.time()

    try:
        client = get_client()

        # Build conversation history
        system_prompt = SYSTEM_PROMPT.format(
            memory_context=format_memory_context(state)
        )

        # Get user message
        user_message = get_last_user_message(state) or ""
        full_prompt = f"{system_prompt}\n\nUser: {user_message}"

        # Generate response
        response = await client.aio.models.generate_content(
            model=settings.flash_model,
            contents=full_prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
            ),
        )
        response_text = response.text

        latency_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Flash response generated",
            latency_ms=latency_ms,
            response_length=len(response_text),
        )

        return {
            "messages": [AIMessage(content=response_text)],
            "current_cortex": "flash",
            "metadata": metadata.model_copy(
                update={
                    "model_used": settings.flash_model,
                    "latency_ms": latency_ms,
                    "token_count_output": len(response_text) // 4,  # Rough estimate
                }
            ) if metadata else None,
            "processing_stage": "generate_response",
        }

    except Exception as e:
        logger.error("Flash response failed", error=str(e))
        return {
            "processing_stage": "error",
            "error": f"Response generation failed: {str(e)}",
        }


async def respond_pro(state: AlexState) -> dict[str, Any]:
    """
    Generate response using Gemini Pro (Executive Cortex).

    Used for:
    - Complex reasoning tasks
    - Architectural decisions
    - Ambiguous requests requiring clarification
    - Multi-step planning
    """
    metadata = state.get("metadata")
    logger.info(
        "Generating Pro response",
        session_id=state.get("session_id"),
        intent=metadata.intent if metadata else None,
        complexity=metadata.complexity_score if metadata else None,
    )

    start_time = time.time()

    try:
        client = get_client()

        # Enhanced system prompt for complex reasoning
        system_prompt = SYSTEM_PROMPT.format(
            memory_context=format_memory_context(state)
        )
        system_prompt += """

For this complex task, take your time to:
1. Analyze the request thoroughly
2. Consider multiple approaches
3. Identify potential issues or ambiguities
4. Provide a well-structured response
"""

        # Get user message
        user_message = get_last_user_message(state) or ""
        full_prompt = f"{system_prompt}\n\nUser: {user_message}"

        # Generate response with Pro model
        response = await client.aio.models.generate_content(
            model=settings.pro_model,
            contents=full_prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.8,
                top_p=0.95,
                top_k=40,
                max_output_tokens=16384,  # Higher limit for complex responses
            ),
        )
        response_text = response.text

        latency_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Pro response generated",
            latency_ms=latency_ms,
            response_length=len(response_text),
        )

        return {
            "messages": [AIMessage(content=response_text)],
            "current_cortex": "pro",
            "metadata": metadata.model_copy(
                update={
                    "model_used": settings.pro_model,
                    "latency_ms": latency_ms,
                    "token_count_output": len(response_text) // 4,
                }
            ) if metadata else None,
            "processing_stage": "generate_response",
        }

    except Exception as e:
        logger.error("Pro response failed", error=str(e))
        # Fall back to Flash on Pro failure
        logger.info("Falling back to Flash")
        return await respond_flash(state)
