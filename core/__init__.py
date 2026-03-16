# BirdsAiView core: scraping and deduplication (fetch-only for OpenClaw)
from core.scraper import fetch_rss, fetch_sources, fetch_playwright, fetch_newsapi
from core.deduplicator import deduplicate_semantic

__all__ = [
    "fetch_rss",
    "fetch_sources",
    "fetch_playwright",
    "fetch_newsapi",
    "deduplicate_semantic",
]
