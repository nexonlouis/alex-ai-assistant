"""
Gemini Pro model integration (Executive Cortex).

The Pro model handles:
- Complex reasoning tasks
- Architectural decisions
- Ambiguous request resolution
- Multi-step planning
"""

from google import genai
import structlog

from alex.config import settings
from alex.cortex.flash import get_client

logger = structlog.get_logger()


def get_pro_model() -> str:
    """Get the Pro model name."""
    return settings.pro_model


async def generate_pro_response(
    prompt: str,
    system_instruction: str | None = None,
    thinking_budget: int | None = None,
) -> str:
    """
    Generate a response using Gemini Pro with extended reasoning.

    Args:
        prompt: The user prompt
        system_instruction: Optional system instruction
        thinking_budget: Optional thinking token budget for complex tasks

    Returns:
        Generated response text
    """
    client = get_client()

    # Build prompt with reasoning instructions
    reasoning_prompt = """Before responding, analyze the request:
1. What is the user actually asking for?
2. What are the key constraints or requirements?
3. What approaches could solve this?
4. What are the tradeoffs of each approach?

Now provide your response:
"""

    if system_instruction:
        full_prompt = f"{system_instruction}\n\n{reasoning_prompt}\n\nUser request: {prompt}"
    else:
        full_prompt = f"{reasoning_prompt}\n\nUser request: {prompt}"

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

    return response.text


async def analyze_code_change(
    description: str,
    current_code: str | None = None,
    constraints: list[str] | None = None,
) -> dict:
    """
    Analyze a proposed code change using Pro's reasoning capabilities.

    Args:
        description: Description of the desired change
        current_code: Current code if available
        constraints: List of constraints to consider

    Returns:
        Analysis with recommendations
    """
    prompt = f"""Analyze this code change request:

Description: {description}

{"Current code:" + current_code if current_code else "No current code provided."}

{"Constraints: " + ", ".join(constraints) if constraints else ""}

Provide:
1. Understanding of the request
2. Proposed approach
3. Potential risks or issues
4. Recommended implementation steps
5. Test cases to consider

Format as structured JSON.
"""

    client = get_client()
    response = await client.aio.models.generate_content(
        model=settings.pro_model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8192,
        ),
    )

    # Parse response (Pro should return structured JSON)
    import json
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        return {"raw_analysis": response.text}
