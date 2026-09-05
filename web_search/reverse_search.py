"""Stage 2: genuine reverse-image / web search via SerpApi's Google Lens engine.

This makes a real, live API call for every run - nothing here is a
hardcoded or pre-picked result. If SerpApi returns nothing (or nothing that
looks like a real social post), the pipeline says so rather than fabricating
a match.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

SOCIAL_DOMAINS = (
    "instagram.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "linkedin.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "threads.net",
)


@dataclass
class Candidate:
    title: str
    link: str
    source: str
    thumbnail: Optional[str]
    is_social: bool


def _looks_social(link: str, source: str) -> bool:
    haystack = f"{link} {source}".lower()
    return any(domain in haystack for domain in SOCIAL_DOMAINS)


def search_by_image_url(image_url: str, limit: int = 20) -> List[Candidate]:
    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "SERPAPI_API_KEY not set. Copy .env.example to .env and add a "
            "free key from https://serpapi.com/manage-api-key"
        )

    params = {
        "engine": "google_lens",
        "url": image_url,
        "api_key": SERPAPI_API_KEY,
    }
    resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"SerpApi error: {data['error']}")

    raw_matches = data.get("visual_matches", [])[:limit]
    candidates = []
    for m in raw_matches:
        link = m.get("link", "")
        source = m.get("source", "")
        candidates.append(
            Candidate(
                title=m.get("title", ""),
                link=link,
                source=source,
                thumbnail=m.get("thumbnail"),
                is_social=_looks_social(link, source),
            )
        )

    # Prefer genuine social-media hits (what the task asks for) but keep
    # everything else as a fallback in case Lens surfaces the post via a
    # reposting/aggregator site instead.
    candidates.sort(key=lambda c: not c.is_social)
    return candidates
