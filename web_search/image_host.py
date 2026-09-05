"""Temporary public hosting for the input photo.

SerpApi's Google Lens engine requires a publicly fetchable image URL, not a
local file. We upload to imgbb with a short expiration so the hosted copy
self-deletes shortly after the search runs, instead of leaving a permanent
public copy of someone's face sitting on a third-party site.
"""
from __future__ import annotations

import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
IMGBB_ENDPOINT = "https://api.imgbb.com/1/upload"
DEFAULT_EXPIRATION = int(os.getenv("IMGBB_EXPIRATION_SECONDS", "600"))


def upload_image(image_path: str, expiration_seconds: int = DEFAULT_EXPIRATION) -> str:
    if not IMGBB_API_KEY:
        raise RuntimeError(
            "IMGBB_API_KEY not set. Copy .env.example to .env and add a free "
            "key from https://api.imgbb.com/"
        )
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    resp = requests.post(
        IMGBB_ENDPOINT,
        data={
            "key": IMGBB_API_KEY,
            "image": b64,
            # Clamp to imgbb's accepted range (60s - 180 days).
            "expiration": max(60, min(expiration_seconds, 15552000)),
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"imgbb upload failed: {data}")
    return data["data"]["url"]
