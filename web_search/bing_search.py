"""Stage 2 fallback: Bing Visual Search (Azure Cognitive Services).

Google Lens (via SerpApi) and Bing crawl and index the web independently -
a post that Google never picked up (common for lower-engagement accounts)
can still show up here, and vice versa. This is only ever used as a
fallback when the primary search found no verified match; it's a second
opinion from a second existing search index, not infrastructure we built
ourselves.

Unlike Lens, Bing Visual Search accepts the raw image file directly, so we
don't need to route it through the temporary imgbb hosting step first.
"""
from __future__ import annotations

import os
from typing import List

import requests
from dotenv import load_dotenv

from .reverse_search import Candidate, _looks_social

load_dotenv()

BING_VISUAL_SEARCH_API_KEY = os.getenv("BING_VISUAL_SEARCH_API_KEY")
BING_VISUAL_SEARCH_ENDPOINT = os.getenv(
    "BING_VISUAL_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/images/visualsearch"
)

# The action types that actually correspond to "this image appears on these
# pages" results. Bing's response also carries things like shopping/product
# suggestions, cropping guidance, etc., which aren't relevant here.
_PAGE_MATCH_ACTION_TYPES = {"PagesIncluding", "VisualSearch"}


def is_configured() -> bool:
    return bool(BING_VISUAL_SEARCH_API_KEY)


def search_by_image_file(image_path: str, limit: int = 20) -> List[Candidate]:
    if not BING_VISUAL_SEARCH_API_KEY:
        raise RuntimeError(
            "BING_VISUAL_SEARCH_API_KEY not set. Copy .env.example to .env and add a "
            "free key from a Bing Search v7 resource (F0 free tier, 1,000 "
            "transactions/month) at https://portal.azure.com/"
        )

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    resp = requests.post(
        BING_VISUAL_SEARCH_ENDPOINT,
        headers={"Ocp-Apim-Subscription-Key": BING_VISUAL_SEARCH_API_KEY},
        files={"image": ("image.jpg", image_bytes, "application/octet-stream")},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    candidates: List[Candidate] = []
    seen_links = set()
    for tag in data.get("tags", []):
        for action in tag.get("actions", []):
            if action.get("actionType") not in _PAGE_MATCH_ACTION_TYPES:
                continue
            for item in action.get("data", {}).get("value", []):
                link = item.get("hostPageUrl", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                source = item.get("hostPageDisplayUrl", "")
                candidates.append(
                    Candidate(
                        title=item.get("name", ""),
                        link=link,
                        source=source,
                        thumbnail=item.get("thumbnailUrl") or item.get("contentUrl"),
                        is_social=_looks_social(link, source),
                    )
                )

    candidates.sort(key=lambda c: not c.is_social)
    return candidates[:limit]
