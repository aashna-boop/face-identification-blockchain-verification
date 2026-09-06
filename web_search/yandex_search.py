"""Stage 2 fallback: Yandex reverse-image search (via SerpApi's yandex_images
engine).

Google Lens and Yandex Images crawl and rank the web independently -
Yandex is well-regarded (in OSINT circles) for surfacing face matches
Google misses, especially for lower-engagement social accounts. This reuses
the same SerpApi account/key as the primary search (just a different
engine), so no separate signup is needed.

(Note: Bing Visual Search was the original fallback choice here, but
Microsoft fully retired the Bing Search APIs - including Visual Search -
on August 11, 2025. Yandex, via SerpApi, replaced it.)
"""
from __future__ import annotations

import os
from typing import List

import requests
from dotenv import load_dotenv

from .reverse_search import SERPAPI_ENDPOINT, Candidate, _looks_social

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")


def is_configured() -> bool:
    return bool(SERPAPI_API_KEY)


def search_by_image_url(image_url: str, limit: int = 20) -> List[Candidate]:
    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "SERPAPI_API_KEY not set - this fallback reuses the same SerpApi "
            "key as the primary Google Lens search."
        )

    params = {
        "engine": "yandex_images",
        "url": image_url,
        "api_key": SERPAPI_API_KEY,
    }
    resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"SerpApi (Yandex) error: {data['error']}")

    raw_results = data.get("image_results", [])[:limit]
    candidates: List[Candidate] = []
    for m in raw_results:
        link = m.get("link", "")
        source = m.get("source", "")
        thumbnail = (m.get("thumbnail") or {}).get("link") or (m.get("original_image") or {}).get("link")
        candidates.append(
            Candidate(
                title=m.get("title", ""),
                link=link,
                source=source,
                thumbnail=thumbnail,
                is_social=_looks_social(link, source),
            )
        )

    candidates.sort(key=lambda c: not c.is_social)
    return candidates
