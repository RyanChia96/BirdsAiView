"""
Surveillance Enricher skill — deep research for M&A and tech announcements.
Accepts item JSON via stdin or --item path. Returns enriched JSON.
"""
import os
import sys
import json

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    os.chdir(_REPO_ROOT)

    item = None
    if "--item" in sys.argv:
        idx = sys.argv.index("--item")
        path = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None
        if path and os.path.isfile(path):
            item = load_json(path)
    if item is None and not sys.stdin.isatty():
        try:
            item = json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    if not item:
        print("Usage: python run.py --item <path>  OR  echo '{\"title\":\"...\",\"summary\":\"...\"}' | python run.py")
        sys.exit(1)

    from core.enricher import enrich_item

    enriched = enrich_item(item.copy())

    if "--json" in sys.argv:
        print(json.dumps(enriched, ensure_ascii=False, indent=2))
    else:
        title = enriched.get("title", "")
        link = enriched.get("link", "")
        e = enriched.get("enrichment", "")
        if e:
            print(f"## {title}\n{link}\n\n### Research\n{e}")
        else:
            print(f"No enrichment (OpenClaw not configured or item not high-impact ma/tech): {title}")


if __name__ == "__main__":
    main()
