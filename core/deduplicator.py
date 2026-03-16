"""
Deduplicator: Semantic title-similarity deduplication for news items.
Uses TF-IDF + cosine similarity to cluster same-story articles across sources.
Keeps highest-quality source per cluster (threshold ~0.85).
"""
from typing import Any

# Optional scikit-learn; fail gracefully if not installed
def _get_tfidf():
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        return TfidfVectorizer, cosine_similarity
    except ImportError:
        return None, None


def _source_priority(source: str) -> int:
    """Priority score for source (higher = prefer when deduping)."""
    s = (source or "").lower()
    if "bnm.gov" in s or "bank negara" in s:
        return 3
    if "gov.my" in s or "dosm" in s or "official" in s:
        return 3
    if "thestar" in s or "edge" in s or "malaymail" in s:
        return 2
    return 1


def _item_quality(item: dict[str, Any]) -> float:
    """Composite quality for choosing which item to keep in a cluster."""
    return float(_source_priority(item.get("source", "")))


def deduplicate_semantic(
    items: list[dict[str, Any]],
    threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """
    Deduplicate items by title similarity. When two items have cosine similarity
    >= threshold, keep the one with higher quality (source priority + optional quality_score).
    Returns deduplicated list.
    """
    if len(items) <= 1:
        return items

    TfidfVectorizer, cosine_similarity = _get_tfidf()
    if TfidfVectorizer is None or cosine_similarity is None:
        return items  # No sklearn: skip semantic dedup, return as-is

    titles = [it.get("title", "") or "" for it in items]
    if not any(t.strip() for t in titles):
        return items

    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    try:
        X = vectorizer.fit_transform(titles)
    except ValueError:
        return items

    sim = cosine_similarity(X)
    n = len(items)
    keep = [True] * n

    for i in range(n):
        if not keep[i]:
            continue
        for j in range(i + 1, n):
            if not keep[j]:
                continue
            if sim[i, j] >= threshold:
                qi = _item_quality(items[i])
                qj = _item_quality(items[j])
                if qj > qi:
                    keep[i] = False
                    break
                else:
                    keep[j] = False

    return [it for it, k in zip(items, keep) if k]
