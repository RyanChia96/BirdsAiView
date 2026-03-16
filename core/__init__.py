# BirdsAiView core: shared logic for Telegram, scraping, and AI processing
from core.telegram import send_telegram, get_telegram_config, html_escape
from core.scraper import fetch_rss, fetch_sources, fetch_playwright, fetch_newsapi
from core.processor import (
    is_relevant,
    summarize_item,
    summarize_batch,
    compute_quality_score,
    classify_event,
    classify_events_batch,
    score_impact_batch,
    sort_by_impact,
)
from core.deduplicator import deduplicate_semantic

__all__ = [
    "send_telegram",
    "get_telegram_config",
    "html_escape",
    "fetch_rss",
    "fetch_sources",
    "fetch_playwright",
    "fetch_newsapi",
    "is_relevant",
    "summarize_item",
    "summarize_batch",
    "compute_quality_score",
    "classify_event",
    "classify_events_batch",
    "score_impact_batch",
    "sort_by_impact",
    "deduplicate_semantic",
]
