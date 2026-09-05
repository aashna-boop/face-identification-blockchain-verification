"""Stage 2.5: verify a search hit is actually the same face, not just a
visually/textually similar page.

Most reverse-image demos stop at "SerpApi returned a link, done." Here we
re-run the same face-encoding step from stage 1 on each candidate image and
compare embeddings, so a "match" means the face pipeline itself confirmed
it - not just that Google Lens thought the pictures looked alike.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np
import requests

from face_id.detector import FaceEncoding, encode_face

# Cosine-distance thresholds DeepFace publishes per model (lower = stricter).
THRESHOLDS = {
    "Facenet512": 0.30,
    "Facenet": 0.40,
    "VGG-Face": 0.40,
    "ArcFace": 0.68,
    "OpenFace": 0.10,
}


@dataclass
class MatchResult:
    is_match: bool
    distance: float
    threshold: float
    error: Optional[str] = None


def cosine_distance(a, b) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return 1.0 - float(a @ b) / (float(np.linalg.norm(a)) * float(np.linalg.norm(b)))


def _download_to_temp(image_url: str) -> str:
    resp = requests.get(image_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    suffix = ".jpg"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return path


def verify_candidate(original: FaceEncoding, candidate_image_url: str) -> MatchResult:
    """Download a candidate image and compare its face embedding to `original`."""
    threshold = THRESHOLDS.get(original.model, 0.40)
    tmp_path = None
    try:
        tmp_path = _download_to_temp(candidate_image_url)
        candidate = encode_face(tmp_path)
    except FileNotFoundError:
        return MatchResult(is_match=False, distance=1.0, threshold=threshold, error="download_failed")
    except ValueError:
        # No detectable face in the candidate image (text post, logo, meme, etc.)
        return MatchResult(is_match=False, distance=1.0, threshold=threshold, error="no_face_in_candidate")
    except requests.RequestException as e:
        return MatchResult(is_match=False, distance=1.0, threshold=threshold, error=f"fetch_error: {e}")
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.remove(tmp_path)

    dist = cosine_distance(original.embedding, candidate.embedding)
    return MatchResult(is_match=dist <= threshold, distance=dist, threshold=threshold)
