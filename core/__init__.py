# BirdsAiView core: shared logic for Telegram, scraping, and AI processing
from core.telegram import send_telegram, get_telegram_config, html_escape
from core.scraper import fetch_rss, fetch_playwright
from core.processor import is_relevant, summarize_item, summarize_batch

__all__ = [
    "send_telegram",
    "get_telegram_config",
    "html_escape",
    "fetch_rss",
    "fetch_playwright",
    "is_relevant",
    "summarize_item",
    "summarize_batch",
]
