"""
Claude Code integration for Alex AI Assistant.

The Claude cortex handles engineering tasks:
- Code implementation
- Refactoring
- Debugging
- Test writing
- Architecture implementation
"""

import anthropic
import structlog

from alex.config import settings

logger = structlog.get_logger()

_client: anthropic.AsyncAnthropic | None = None


def get_claude_client() -> anthropic.AsyncAnthropic:
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        _client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
    return _client


CLAUDE_SYSTEM_PROMPT = """You are Claude, an expert software engineer working as part of Alex AI Assistant's engineering cortex.

Your role is to handle engineering tasks that require code implementation, refactoring, debugging, or technical deep-dives.

Key guidelines:
1. Provide complete, working code - not pseudocode or partial implementations
2. Follow best practices for the language/framework being used
3. Include error handling and edge cases
4. Write clear comments for complex logic
5. Consider security implications
6. Suggest tests when appropriate

When analyzing code:
- Be thorough but concise
- Identify root causes, not just symptoms
- Propose concrete solutions with code examples

Format your responses clearly with:
- Code blocks for all code (with language specifiers)
- Brief explanations of your approach
- Any caveats or limitations

Remember: You're part of a larger system. Alex (the coordinator) will relay your responses to the user."""


async def generate_engineering_response(
    task_description: str,
    context: str | None = None,
    code_context: str | None = None,
    intent: str = "code_change",
) -> str:
    """
    Generate a response for an engineering task using Claude.

    Args:
        task_description: Description of the engineering task
        context: Optional context from memory/previous conversations
        code_context: Optional relevant code snippets
        intent: The specific engineering intent (code_change, refactor, debug, test, deploy)

    Returns:
        Claude's response with code and explanations
    """
    client = get_claude_client()

    # Build the user message with context
    user_message_parts = []

    if context:
        user_message_parts.append(f"## Context from previous conversations:\n{context}\n")

    if code_context:
        user_message_parts.append(f"## Relevant code:\n```\n{code_context}\n```\n")

    # Add intent-specific instructions
    intent_instructions = {
        "code_change": "Implement the requested code changes. Provide complete, working code.",
        "refactor": "Refactor the code to improve quality, readability, and maintainability. Explain your changes.",
        "debug": "Analyze the issue and provide a fix. Explain the root cause and your solution.",
        "test": "Write comprehensive tests for the described functionality. Include edge cases.",
        "deploy": "Provide deployment instructions and any necessary configuration changes.",
    }

    instruction = intent_instructions.get(intent, intent_instructions["code_change"])
    user_message_parts.append(f"## Task ({intent}):\n{instruction}\n")
    user_message_parts.append(f"## Request:\n{task_description}")

    user_message = "\n".join(user_message_parts)

    logger.info(
        "Calling Claude for engineering task",
        intent=intent,
        task_length=len(task_description),
    )

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16384,
        system=CLAUDE_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_message}
        ],
    )

    # Extract text from response
    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    logger.info(
        "Claude response received",
        intent=intent,
        response_length=len(response_text),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    return response_text


async def analyze_and_implement(
    request: str,
    memory_context: dict | None = None,
) -> dict:
    """
    Analyze an engineering request and provide implementation.

    This is a higher-level function that:
    1. Analyzes the request to understand requirements
    2. Generates implementation code
    3. Suggests tests

    Args:
        request: The engineering request
        memory_context: Optional context from Alex's memory

    Returns:
        Dict with analysis, implementation, and test suggestions
    """
    # Build context string from memory
    context_str = None
    if memory_context:
        context_parts = []
        if memory_context.get("daily_summary"):
            context_parts.append(f"Today's context: {memory_context['daily_summary']}")
        if memory_context.get("relevant_interactions"):
            for interaction in memory_context["relevant_interactions"][:3]:
                context_parts.append(
                    f"Previous discussion: {interaction.get('user_message', '')[:200]}"
                )
        if context_parts:
            context_str = "\n".join(context_parts)

    # Generate implementation
    response = await generate_engineering_response(
        task_description=request,
        context=context_str,
        intent="code_change",
    )

    return {
        "implementation": response,
        "model": "claude-sonnet-4-20250514",
        "cortex": "claude_code",
    }


async def debug_issue(
    issue_description: str,
    error_message: str | None = None,
    stack_trace: str | None = None,
    relevant_code: str | None = None,
) -> str:
    """
    Debug an issue using Claude's analysis capabilities.

    Args:
        issue_description: Description of the issue
        error_message: Optional error message
        stack_trace: Optional stack trace
        relevant_code: Optional code that may be causing the issue

    Returns:
        Analysis and fix recommendation
    """
    task_parts = [issue_description]

    if error_message:
        task_parts.append(f"\n**Error message:**\n```\n{error_message}\n```")

    if stack_trace:
        task_parts.append(f"\n**Stack trace:**\n```\n{stack_trace}\n```")

    task_description = "\n".join(task_parts)

    return await generate_engineering_response(
        task_description=task_description,
        code_context=relevant_code,
        intent="debug",
    )


async def write_tests(
    functionality_description: str,
    code_to_test: str | None = None,
    test_framework: str = "pytest",
) -> str:
    """
    Generate tests for described functionality.

    Args:
        functionality_description: What should be tested
        code_to_test: Optional code to test
        test_framework: Testing framework to use

    Returns:
        Generated test code
    """
    task_description = f"""Write comprehensive tests for the following functionality using {test_framework}.

Functionality: {functionality_description}

Include:
- Happy path tests
- Edge cases
- Error handling tests
- Any necessary mocks or fixtures"""

    return await generate_engineering_response(
        task_description=task_description,
        code_context=code_to_test,
        intent="test",
    )
