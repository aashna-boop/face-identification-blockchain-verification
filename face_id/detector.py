"""Stage 1: Face detection + encoding.

Wraps DeepFace so the rest of the pipeline only deals with a plain
FaceEncoding value object, not a particular CV library's API.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.getenv("FACE_MODEL", "Facenet512")
DETECTOR_BACKEND = os.getenv("FACE_DETECTOR", "opencv")


@dataclass
class FaceEncoding:
    embedding: List[float]
    model: str
    detector: str
    source_path: str
    source_sha256: str = field(default="")


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def encode_face(image_path: str) -> FaceEncoding:
    """Detect the primary face in `image_path` and return its embedding.

    Raises FileNotFoundError if the path doesn't exist, or ValueError if no
    face could be detected (DeepFace raises when enforce_detection=True).
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)

    # Imported lazily: deepface pulls in tensorflow, which is slow to import
    # and unnecessary for anything that only touches evidence/blockchain code.
    from deepface import DeepFace

    try:
        reps = DeepFace.represent(
            img_path=image_path,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR_BACKEND,
            enforce_detection=True,
        )
    except ValueError as e:
        raise ValueError(f"No face detected in {image_path}: {e}") from e

    if not reps:
        raise ValueError(f"No face detected in {image_path}")

    # If more than one face is in frame, use the most confidently detected one.
    best = max(reps, key=lambda r: r.get("face_confidence", 0))

    return FaceEncoding(
        embedding=best["embedding"],
        model=MODEL_NAME,
        detector=DETECTOR_BACKEND,
        source_path=image_path,
        source_sha256=sha256_of_file(image_path),
    )
