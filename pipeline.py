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


def _print_candidates(candidates) -> None:
    for i, c in enumerate(candidates, 1):
        tag = "[social]" if c.is_social else "[other] "
        print(f"  {i:>2}. {tag} {c.title[:60]!r} -> {c.link}")


def _find_verified_match(original, candidates):
    """Check candidates in order, return (candidate, match_result, checked_count)
    for the first one whose face embedding actually matches, or (None, None,
    checked_count) if none did. Never fabricates a match.
    """
    from verification.face_match import verify_candidate

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
            return c, result, checked
    return None, None, checked


def run_full_pipeline(image_path: str, top_k: int, tamper_demo: bool) -> None:
    from face_id.detector import encode_face
    from web_search.image_host import upload_image
    from web_search import reverse_search, bing_search

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
    candidates = reverse_search.search_by_image_url(public_url, limit=top_k)
    engine_used = "google_lens"
    total_checked = 0

    if candidates:
        _print_candidates(candidates)
        _hr("STAGE 2.5 — Re-verifying candidates against the original face")
        candidate, match, checked = _find_verified_match(original, candidates)
        total_checked += checked
    else:
        print("No visual matches returned by Google Lens.")
        candidate = match = None

    if candidate is None:
        if bing_search.is_configured():
            _hr("STAGE 2 (fallback) — Bing Visual Search")
            print("Google Lens found no verified match; trying Bing's independent "
                  "image index as a second opinion...")
            bing_candidates = bing_search.search_by_image_file(image_path, limit=top_k)
            if bing_candidates:
                _print_candidates(bing_candidates)
                _hr("STAGE 2.5 (fallback) — Re-verifying Bing candidates against the original face")
                candidate, match, checked = _find_verified_match(original, bing_candidates)
                total_checked += checked
                if candidate is not None:
                    engine_used = "bing_visual_search"
            else:
                print("No visual matches returned by Bing Visual Search either.")
        else:
            print("\n(No BING_VISUAL_SEARCH_API_KEY configured, so no fallback search "
                  "was attempted — see .env.example.)")

    if candidate is None:
        print(f"\nChecked {total_checked} candidate image(s) across all configured "
              "search backends; none verified as the same face. Not fabricating a "
              "match — stopping here. Try a clearer input photo, increase --top-k, "
              "or configure BING_VISUAL_SEARCH_API_KEY for a second search backend.")
        return
    _hr("Matched post found")
    print(f"URL      : {candidate.link}")
    print(f"Source   : {candidate.source}")
    print(f"Title    : {candidate.title}")
    print(f"Distance : {match.distance:.4f} (<= {match.threshold} threshold)")
    print(f"Found via: {engine_used}")

    evidence = {
        "post_url": candidate.link,
        "post_source": candidate.source,
        "post_title": candidate.title,
        "post_thumbnail": candidate.thumbnail,
        "search_engine": engine_used,
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
