#!/usr/bin/env python3
"""End-to-end pipeline: face scan -> web/social search -> blockchain verification.

Ethical scope (read this before running against any photo):
  This tool is built to be run against your OWN photo, to find and anchor
  YOUR OWN real public social post. It is not intended, and should not be
  used, to identify or track other people from their photos without their
  consent. The --consent flag below is a deliberate speed bump for that.

Usage:
  Full pipeline (search + verify + blockchain):
    python pipeline.py --image path/to/your_photo.jpg --consent

  Re-verify a previously saved evidence file against the chain later:
    python pipeline.py --verify output/evidence_<timestamp>.json

  Demonstrate tamper detection (mutates evidence in memory, re-verifies):
    python pipeline.py --image path/to/your_photo.jpg --consent --tamper-demo
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()


def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run_full_pipeline(image_path: str, top_k: int, tamper_demo: bool) -> None:
    from face_id.detector import encode_face
    from web_search.image_host import upload_image
    from web_search.reverse_search import search_by_image_url
    from verification.face_match import verify_candidate
    from blockchain.registry import register_evidence, verify_evidence

    _hr("STAGE 1 — Face detection & encoding")
    original = encode_face(image_path)
    print(f"Input image     : {image_path}")
    print(f"Image SHA-256   : {original.source_sha256}")
    print(f"Model/detector  : {original.model} / {original.detector}")
    print(f"Embedding dims  : {len(original.embedding)}")

    _hr("STAGE 2 — Reverse-image / social-media search (SerpApi Google Lens)")
    print("Uploading photo to a short-lived public URL (required by the search API)...")
    public_url = upload_image(image_path)
    print(f"Temporary public URL: {public_url}")

    print(f"Searching for visual matches (top {top_k} considered)...")
    candidates = search_by_image_url(public_url, limit=top_k)
    if not candidates:
        print("No visual matches returned by the search API. Stopping — "
              "nothing to verify or anchor on-chain.")
        return

    for i, c in enumerate(candidates, 1):
        tag = "[social]" if c.is_social else "[other] "
        print(f"  {i:>2}. {tag} {c.title[:60]!r} -> {c.link}")

    _hr("STAGE 2.5 — Re-verifying candidates against the original face")
    verified = None
    checked = 0
    for c in candidates:
        if not c.thumbnail:
            continue
        checked += 1
        result = verify_candidate(original, c.thumbnail)
        status = "MATCH" if result.is_match else "no match"
        detail = result.error or f"distance={result.distance:.4f} (threshold {result.threshold})"
        print(f"  - {c.link}\n      {status} — {detail}")
        if result.is_match:
            verified = (c, result)
            break

    if verified is None:
        print(f"\nChecked {checked} candidate image(s); none verified as the same "
              "face. Not fabricating a match — stopping here. Try a clearer "
              "input photo or increase --top-k.")
        return

    candidate, match = verified
    _hr("Matched post found")
    print(f"URL      : {candidate.link}")
    print(f"Source   : {candidate.source}")
    print(f"Title    : {candidate.title}")
    print(f"Distance : {match.distance:.4f} (<= {match.threshold} threshold)")

    evidence = {
        "post_url": candidate.link,
        "post_source": candidate.source,
        "post_title": candidate.title,
        "post_thumbnail": candidate.thumbnail,
        "match_distance": round(match.distance, 6),
        "match_threshold": match.threshold,
        "face_model": original.model,
        "face_detector": original.detector,
        "input_image_sha256": original.source_sha256,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs("output", exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = os.path.join("output", f"evidence_{stamp}.json")
    with open(evidence_path, "w") as f:
        json.dump(evidence, f, indent=2)
    print(f"\nSaved off-chain evidence record: {evidence_path}")

    _hr("STAGE 3 — Anchoring the evidence fingerprint on-chain")
    onchain = register_evidence(evidence)
    print(f"Contract address : {onchain['contract_address']}")
    print(f"Tx hash          : {onchain['tx_hash']}")
    print(f"Block number     : {onchain['block_number']}")
    print(f"Content hash     : {onchain['content_hash']}")

    _hr("STAGE 3.5 — Re-verifying the saved evidence against the chain")
    with open(evidence_path) as f:
        reloaded = json.load(f)
    check = verify_evidence(reloaded)
    print(f"On-chain?  : {check['on_chain']}")
    print(f"Submitter  : {check['submitter']}")
    print(f"Source URL : {check['source_url']}")
    if check["on_chain"]:
        print("\n✅ VERIFIED — evidence file matches the on-chain record.")
    else:
        print("\n⚠️  Not found on-chain — something is inconsistent.")

    if tamper_demo:
        _hr("BONUS — tamper-evidence demo")
        tampered = copy.deepcopy(reloaded)
        tampered["post_title"] = tampered["post_title"] + " (edited after the fact)"
        print("Mutated a copy of the evidence (changed post_title) and re-verifying...")
        tampered_check = verify_evidence(tampered)
        print(f"On-chain? : {tampered_check['on_chain']}")
        if not tampered_check["on_chain"]:
            print("❌ As expected: the tampered content hashes differently and "
                  "matches no on-chain record — this is what tamper-evidence looks like.")


def run_verify_only(evidence_path: str) -> None:
    from blockchain.registry import verify_evidence

    with open(evidence_path) as f:
        evidence = json.load(f)

    _hr(f"Re-verifying {evidence_path} against the chain")
    check = verify_evidence(evidence)
    print(json.dumps(check, indent=2))
    print("\n✅ VERIFIED" if check["on_chain"] else "\n❌ NOT FOUND ON-CHAIN (missing or tampered)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", help="Path to the input face photo (your own).")
    parser.add_argument("--consent", action="store_true",
                         help="Confirms you have the right to search/anchor this photo "
                              "(required to run the full pipeline).")
    parser.add_argument("--top-k", type=int, default=10, help="Max search candidates to consider.")
    parser.add_argument("--tamper-demo", action="store_true",
                         help="After verifying, also show a mutated copy failing verification.")
    parser.add_argument("--verify", metavar="EVIDENCE_JSON",
                         help="Skip search; just re-verify a saved evidence file against the chain.")
    args = parser.parse_args()

    if args.verify:
        run_verify_only(args.verify)
        return

    if not args.image:
        parser.error("--image is required (or use --verify EVIDENCE_JSON)")

    if not args.consent:
        parser.error(
            "Refusing to run: pass --consent to confirm this photo is yours (or you "
            "otherwise have the subject's permission) to search for and anchor on-chain. "
            "See the Ethics section in README.md."
        )

    run_full_pipeline(args.image, args.top_k, args.tamper_demo)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - top-level CLI error reporting
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
