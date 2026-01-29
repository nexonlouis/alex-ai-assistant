"""
Recursive Summarization for Alex AI Assistant.

Implements hierarchical summarization:
- Daily: Summarize all interactions from a day
- Weekly: Summarize daily summaries into weekly themes
- Monthly: Summarize weekly summaries into monthly insights

This enables efficient context retrieval at different temporal scales.
Uses PostgreSQL with pgvector for storage.
"""

from datetime import date, timedelta
from typing import Any

import structlog
from google import genai

from alex.config import settings
from alex.cortex.flash import get_client, generate_embedding
from alex.memory.postgres_store import PostgresStore

logger = structlog.get_logger()


# Summarization prompts
DAILY_SUMMARY_PROMPT = """You are Alex's memory consolidation system. Summarize the following interactions from {date}.

INTERACTIONS:
{interactions}

Create a concise summary (2-3 paragraphs) that captures:
1. Main topics discussed
2. Key decisions or conclusions reached
3. Any tasks or follow-ups mentioned
4. Notable technical concepts explored

Also extract 3-7 key topics as a comma-separated list.

Format your response as:
SUMMARY:
[Your summary here]

KEY_TOPICS:
[topic1, topic2, topic3, ...]
"""

WEEKLY_SUMMARY_PROMPT = """You are Alex's memory consolidation system. Create a weekly summary from the following daily summaries for week {week_id}.

DAILY SUMMARIES:
{daily_summaries}

Create a thematic summary (3-4 paragraphs) that:
1. Identifies recurring themes across the week
2. Tracks progress on ongoing projects or discussions
3. Notes any shifts in focus or priorities
4. Highlights key achievements or milestones

Also extract 5-10 key themes as a comma-separated list.

Format your response as:
SUMMARY:
[Your summary here]

KEY_THEMES:
[theme1, theme2, theme3, ...]
"""

MONTHLY_SUMMARY_PROMPT = """You are Alex's memory consolidation system. Create a monthly summary from the following weekly summaries for {month_name} {year}.

WEEKLY SUMMARIES:
{weekly_summaries}

Create a strategic summary (4-5 paragraphs) that:
1. Identifies major themes and patterns across the month
2. Tracks evolution of projects and priorities
3. Notes significant accomplishments
4. Suggests areas for future focus

Also extract 5-10 key themes as a comma-separated list.

Format your response as:
SUMMARY:
[Your summary here]

KEY_THEMES:
[theme1, theme2, theme3, ...]
"""


def _parse_summary_response(response: str) -> tuple[str, list[str]]:
    """Parse the LLM response into summary and topics/themes."""
    summary = ""
    topics = []

    # Split by markers
    parts = response.split("KEY_TOPICS:") if "KEY_TOPICS:" in response else response.split("KEY_THEMES:")

    if len(parts) >= 2:
        # Extract summary
        summary_part = parts[0]
        if "SUMMARY:" in summary_part:
            summary = summary_part.split("SUMMARY:")[1].strip()
        else:
            summary = summary_part.strip()

        # Extract topics/themes
        topics_part = parts[1].strip()
        # Handle both comma-separated and newline-separated lists
        if "," in topics_part:
            topics = [t.strip().strip("[]") for t in topics_part.split(",")]
        else:
            topics = [t.strip().strip("-").strip() for t in topics_part.split("\n") if t.strip()]
    else:
        # Fallback: treat entire response as summary
        summary = response.strip()
        if "SUMMARY:" in summary:
            summary = summary.split("SUMMARY:")[1].strip()

    # Clean up topics
    topics = [t for t in topics if t and len(t) > 1]

    return summary, topics


async def summarize_day(date_str: str) -> dict[str, Any]:
    """
    Generate a summary for a specific day's interactions.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Summary result with content, topics, and metadata
    """
    store = PostgresStore()

    # Get interactions for the day
    interactions = await store.get_interactions_for_date(date_str)

    if not interactions:
        logger.info("No interactions to summarize", date=date_str)
        return {"status": "skipped", "reason": "no_interactions", "date": date_str}

    # Format interactions for the prompt
    interaction_texts = []
    for i, interaction in enumerate(interactions, 1):
        user_msg = interaction.get("user_message", "")[:500]  # Truncate long messages
        assistant_msg = interaction.get("assistant_response", "")[:1000]
        intent = interaction.get("intent", "unknown")
        interaction_texts.append(
            f"[{i}] Intent: {intent}\nUser: {user_msg}\nAssistant: {assistant_msg}\n"
        )

    interactions_text = "\n---\n".join(interaction_texts)

    # Generate summary using Gemini Flash
    prompt = DAILY_SUMMARY_PROMPT.format(
        date=date_str,
        interactions=interactions_text,
    )

    client = get_client()
    response = await client.aio.models.generate_content(
        model=settings.flash_model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )

    # Parse response
    summary_content, key_topics = _parse_summary_response(response.text)

    # Generate embedding for the summary
    try:
        embedding = await generate_embedding(summary_content)
    except Exception as e:
        logger.warning("Failed to generate summary embedding", error=str(e))
        embedding = None

    # Store the summary
    await store.create_daily_summary(
        date_str=date_str,
        content=summary_content,
        key_topics=key_topics,
        interaction_count=len(interactions),
        model_used=settings.flash_model,
        embedding=embedding,
    )

    logger.info(
        "Daily summary created",
        date=date_str,
        interaction_count=len(interactions),
        topics_count=len(key_topics),
    )

    return {
        "status": "completed",
        "date": date_str,
        "interaction_count": len(interactions),
        "key_topics": key_topics,
        "summary_length": len(summary_content),
    }


async def summarize_week(week_id: str) -> dict[str, Any]:
    """
    Generate a summary for a specific week from daily summaries.

    Args:
        week_id: Week ID in YYYY-Wxx format

    Returns:
        Summary result with content, themes, and metadata
    """
    store = PostgresStore()

    # Get daily summaries for the week
    daily_summaries = await store.get_daily_summaries_for_week(week_id)

    if not daily_summaries:
        logger.info("No daily summaries to aggregate", week_id=week_id)
        return {"status": "skipped", "reason": "no_daily_summaries", "week_id": week_id}

    # Format daily summaries for the prompt
    summary_texts = []
    total_interactions = 0
    for ds in daily_summaries:
        date = ds.get("date", "unknown")
        content = ds.get("content", "")[:1500]
        topics = ds.get("key_topics", [])
        count = ds.get("interaction_count", 0)
        total_interactions += count

        topics_str = ", ".join(topics) if topics else "N/A"
        summary_texts.append(
            f"**{date}** ({count} interactions)\nTopics: {topics_str}\n{content}\n"
        )

    summaries_text = "\n---\n".join(summary_texts)

    # Generate summary using Gemini Flash
    prompt = WEEKLY_SUMMARY_PROMPT.format(
        week_id=week_id,
        daily_summaries=summaries_text,
    )

    client = get_client()
    response = await client.aio.models.generate_content(
        model=settings.flash_model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=3072,
        ),
    )

    # Parse response
    summary_content, key_themes = _parse_summary_response(response.text)

    # Generate embedding for the summary
    try:
        embedding = await generate_embedding(summary_content)
    except Exception as e:
        logger.warning("Failed to generate summary embedding", error=str(e))
        embedding = None

    # Store the summary
    await store.create_weekly_summary(
        week_id=week_id,
        content=summary_content,
        key_themes=key_themes,
        daily_summary_count=len(daily_summaries),
        total_interactions=total_interactions,
        model_used=settings.flash_model,
        embedding=embedding,
    )

    logger.info(
        "Weekly summary created",
        week_id=week_id,
        daily_count=len(daily_summaries),
        total_interactions=total_interactions,
        themes_count=len(key_themes),
    )

    return {
        "status": "completed",
        "week_id": week_id,
        "daily_summary_count": len(daily_summaries),
        "total_interactions": total_interactions,
        "key_themes": key_themes,
        "summary_length": len(summary_content),
    }


async def summarize_month(month_id: str) -> dict[str, Any]:
    """
    Generate a summary for a specific month from weekly summaries.

    Args:
        month_id: Month ID in YYYY-M format

    Returns:
        Summary result with content, themes, and metadata
    """
    store = PostgresStore()

    # Get weekly summaries for the month
    weekly_summaries = await store.get_weekly_summaries_for_month(month_id)

    if not weekly_summaries:
        logger.info("No weekly summaries to aggregate", month_id=month_id)
        return {"status": "skipped", "reason": "no_weekly_summaries", "month_id": month_id}

    # Parse month_id for display
    parts = month_id.split("-")
    year = int(parts[0])
    month_num = int(parts[1])
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_name = month_names[month_num]

    # Format weekly summaries for the prompt
    summary_texts = []
    total_interactions = 0
    for ws in weekly_summaries:
        week_id = ws.get("week_id", "unknown")
        content = ws.get("content", "")[:2000]
        themes = ws.get("key_themes", [])
        count = ws.get("total_interactions", 0)
        total_interactions += count

        themes_str = ", ".join(themes) if themes else "N/A"
        summary_texts.append(
            f"**{week_id}** ({count} interactions)\nThemes: {themes_str}\n{content}\n"
        )

    summaries_text = "\n---\n".join(summary_texts)

    # Generate summary using Gemini Pro (for higher quality monthly insights)
    prompt = MONTHLY_SUMMARY_PROMPT.format(
        month_name=month_name,
        year=year,
        weekly_summaries=summaries_text,
    )

    client = get_client()
    response = await client.aio.models.generate_content(
        model=settings.pro_model,  # Use Pro for monthly summaries
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=4096,
        ),
    )

    # Parse response
    summary_content, key_themes = _parse_summary_response(response.text)

    # Generate embedding for the summary
    try:
        embedding = await generate_embedding(summary_content)
    except Exception as e:
        logger.warning("Failed to generate summary embedding", error=str(e))
        embedding = None

    # Store the summary
    await store.create_monthly_summary(
        month_id=month_id,
        content=summary_content,
        key_themes=key_themes,
        weekly_summary_count=len(weekly_summaries),
        total_interactions=total_interactions,
        model_used=settings.pro_model,
        embedding=embedding,
    )

    logger.info(
        "Monthly summary created",
        month_id=month_id,
        weekly_count=len(weekly_summaries),
        total_interactions=total_interactions,
        themes_count=len(key_themes),
    )

    return {
        "status": "completed",
        "month_id": month_id,
        "month_name": f"{month_name} {year}",
        "weekly_summary_count": len(weekly_summaries),
        "total_interactions": total_interactions,
        "key_themes": key_themes,
        "summary_length": len(summary_content),
    }


async def run_daily_summarization(max_days: int = 7) -> dict[str, Any]:
    """
    Run summarization for all unsummarized days.

    Args:
        max_days: Maximum number of days to process

    Returns:
        Result summary
    """
    store = PostgresStore()
    results = {"processed": 0, "completed": 0, "skipped": 0, "errors": []}

    # Get days that need summarization
    unsummarized_days = await store.get_unsummarized_days(limit=max_days)

    logger.info("Starting daily summarization", days_to_process=len(unsummarized_days))

    for date_str in unsummarized_days:
        results["processed"] += 1
        try:
            result = await summarize_day(date_str)
            if result["status"] == "completed":
                results["completed"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            logger.error("Daily summarization failed", date=date_str, error=str(e))
            results["errors"].append(f"{date_str}: {str(e)}")

    return results


async def run_weekly_summarization(max_weeks: int = 4) -> dict[str, Any]:
    """
    Run summarization for all unsummarized weeks.

    Args:
        max_weeks: Maximum number of weeks to process

    Returns:
        Result summary
    """
    store = PostgresStore()
    results = {"processed": 0, "completed": 0, "skipped": 0, "errors": []}

    # Get weeks that need summarization
    unsummarized_weeks = await store.get_unsummarized_weeks(limit=max_weeks)

    logger.info("Starting weekly summarization", weeks_to_process=len(unsummarized_weeks))

    for week_id in unsummarized_weeks:
        results["processed"] += 1
        try:
            result = await summarize_week(week_id)
            if result["status"] == "completed":
                results["completed"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            logger.error("Weekly summarization failed", week_id=week_id, error=str(e))
            results["errors"].append(f"{week_id}: {str(e)}")

    return results


async def run_monthly_summarization(max_months: int = 2) -> dict[str, Any]:
    """
    Run summarization for all unsummarized months.

    Args:
        max_months: Maximum number of months to process

    Returns:
        Result summary
    """
    store = PostgresStore()
    results = {"processed": 0, "completed": 0, "skipped": 0, "errors": []}

    # Get months that need summarization
    unsummarized_months = await store.get_unsummarized_months(limit=max_months)

    logger.info("Starting monthly summarization", months_to_process=len(unsummarized_months))

    for month_id in unsummarized_months:
        results["processed"] += 1
        try:
            result = await summarize_month(month_id)
            if result["status"] == "completed":
                results["completed"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            logger.error("Monthly summarization failed", month_id=month_id, error=str(e))
            results["errors"].append(f"{month_id}: {str(e)}")

    return results


async def run_full_summarization_pipeline() -> dict[str, Any]:
    """
    Run the complete summarization pipeline: daily → weekly → monthly.

    This is the main entry point for scheduled summarization tasks.

    Returns:
        Results from all summarization levels
    """
    logger.info("Starting full summarization pipeline")

    results = {
        "daily": await run_daily_summarization(),
        "weekly": await run_weekly_summarization(),
        "monthly": await run_monthly_summarization(),
    }

    logger.info(
        "Summarization pipeline complete",
        daily_completed=results["daily"]["completed"],
        weekly_completed=results["weekly"]["completed"],
        monthly_completed=results["monthly"]["completed"],
    )

    return results
