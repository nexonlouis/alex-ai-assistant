"""
Gemini Flash model integration (Basal Cortex).

The Flash model handles:
- Routine conversations
- Intent classification
- Quick responses
- Background summarization
"""

from functools import lru_cache

from google import genai
import structlog

from alex.config import settings

logger = structlog.get_logger()

# Global client instance
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Get or create the Gemini client."""
    global _client
    if _client is None:
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY not configured")
        _client = genai.Client(api_key=settings.google_api_key.get_secret_value())
        logger.info("Gemini client initialized")
    return _client


def get_flash_model() -> str:
    """Get the Flash model name."""
    return settings.flash_model


async def generate_flash_response(
    prompt: str,
    system_instruction: str | None = None,
) -> str:
    """
    Generate a response using Gemini Flash.

    Args:
        prompt: The user prompt
        system_instruction: Optional system instruction

    Returns:
        Generated response text
    """
    client = get_client()

    if system_instruction:
        full_prompt = f"{system_instruction}\n\n{prompt}"
    else:
        full_prompt = prompt

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

    return response.text


async def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding for text using Gemini embedding model.

    Args:
        text: Text to embed

    Returns:
        Embedding vector
    """
    client = get_client()

    result = await client.aio.models.embed_content(
        model=f"models/{settings.embedding_model}",
        contents=text,
    )

    return result.embeddings[0].values
