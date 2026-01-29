"""
Intent classification node for Alex AI Assistant.

Uses Gemini Flash to classify user intent and determine routing.
"""

import json
import structlog
from typing import Any

from google import genai

from alex.agents.state import AlexState, get_last_user_message
from alex.cortex.flash import get_client
from alex.config import settings

logger = structlog.get_logger()

CLASSIFICATION_PROMPT = """Analyze the following user message and classify it.

User message: {message}

Respond with a JSON object containing:
{{
    "intent": "<one of: chat, question, code_change, refactor, debug, test, memory_query, task_planning, creative, self_modify>",
    "complexity_score": <float between 0.0 and 1.0, where 1.0 is highly complex>,
    "topics": [<list of main topics/concepts mentioned>],
    "entities": [<list of named entities like people, projects, files>],
    "requires_memory": <boolean, true if the query references past conversations or needs context>,
    "is_ambiguous": <boolean, true if the request is vague or needs clarification>
}}

Intent guidelines:
- self_modify: User gives a DIRECT COMMAND for Alex to modify its own code, add features to itself, or read its own files. Must be an action request, not a question. Examples: "add a /weather command to yourself", "read your main.py", "update your system prompt", "show me your code for X". NOT for questions like "can you modify yourself?" or "what can you do?"
- question: User asks ABOUT Alex's capabilities, architecture, or how it works. Examples: "can you modify your code?", "what are your capabilities?", "how do you work?"
- code_change: User asks about external code, not Alex's own codebase
- chat: General conversation, greetings, simple questions
- Other intents: memory_query, task_planning, creative, etc.

Guidelines for complexity_score:
- 0.0-0.3: Simple greetings, factual questions, straightforward requests
- 0.4-0.6: Questions requiring some reasoning, multi-step explanations
- 0.7-0.9: Complex planning, architectural decisions, ambiguous requests
- 1.0: Highly complex tasks requiring deep analysis

Only respond with the JSON object, no additional text."""


async def classify_intent(state: AlexState) -> dict[str, Any]:
    """
    Classify user intent using Gemini Flash.

    This node runs at the start of every interaction to determine:
    - What the user wants (intent)
    - How complex the request is (complexity_score)
    - What topics/entities are involved
    - Whether memory retrieval is needed
    """
    logger.info("Classifying intent", session_id=state.get("session_id"))

    user_message = get_last_user_message(state)
    if not user_message:
        logger.warning("No user message found")
        return {
            "processing_stage": "error",
            "error": "No user message to classify",
        }

    try:
        client = get_client()
        prompt = CLASSIFICATION_PROMPT.format(message=user_message)

        response = await client.aio.models.generate_content(
            model=settings.flash_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.3,  # Lower temperature for consistent classification
                max_output_tokens=1024,
            ),
        )
        response_text = response.text.strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        classification = json.loads(response_text)

        logger.info(
            "Intent classified",
            intent=classification.get("intent"),
            complexity=classification.get("complexity_score"),
            topics=classification.get("topics"),
        )

        # Update state with classification results
        metadata = state.get("metadata")
        return {
            "metadata": metadata.model_copy(
                update={
                    "intent": classification.get("intent", "chat"),
                    "complexity_score": classification.get("complexity_score", 0.3),
                    "topics_extracted": classification.get("topics", []),
                    "entities_extracted": classification.get("entities", []),
                }
            ),
            "processing_stage": "classify",
        }

    except json.JSONDecodeError as e:
        logger.error("Failed to parse classification response", error=str(e))
        # Default to chat intent with medium complexity
        metadata = state.get("metadata")
        return {
            "metadata": metadata.model_copy(
                update={
                    "intent": "chat",
                    "complexity_score": 0.5,
                }
            ),
            "processing_stage": "classify",
        }

    except Exception as e:
        logger.error("Classification failed", error=str(e))
        return {
            "processing_stage": "error",
            "error": f"Classification failed: {str(e)}",
        }
