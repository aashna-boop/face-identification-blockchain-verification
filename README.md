# Face Identification & Blockchain Verification

*Built for HH Goa 2026 — Task 3*

> **TL;DR:** Take a face photo → search the open web for a matching social
> post → make the face pipeline itself re-check that the match is real →
> hash the evidence → anchor that hash on a local blockchain → prove later
> that the evidence hasn't been tampered with. Every step is designed to be
> **self-search only**. This is not, and will never become, a Clearview AI
> clone.

```
face photo ──▶ face encoding (DeepFace, Facenet512)
           ──▶ reverse-image search (SerpApi Google Lens)
           ──▶ re-verify candidate is the same face (cosine distance)
           ──▶ hash the matched post's evidence (SHA-256)
           ──▶ anchor the hash on a local Ethereum chain (Hardhat + Solidity)
           ──▶ re-verify saved evidence against the on-chain record, anytime later
```

---

## Why this README leads with ethics, not features

Task 3's brief — "use a face to find someone's social media" — describes,
almost word for word, the mechanism behind **Clearview AI** and **PimEyes**:
tools that scrape billions of faces without consent and let anyone with an
account unmask a stranger from a single photo. Clearview has been fined by
multiple European data protection authorities and banned from selling to
most U.S. companies for exactly this reason — it turns a technique with
legitimate uses (verifying *your own* identity, reuniting *your own*
accounts, detecting deepfakes of *yourself*) into a mass surveillance and
stalking tool the moment you point it at someone else without their
knowledge.

So the build brief here was: **implement the mechanism, refuse the misuse.**
Concretely, that means:

| Clearview AI / PimEyes | This project |
|---|---|
| Scrapes billions of faces from the entire internet into a private index, without consent | Runs a live search *at query time* against a search engine's existing public index — nothing is scraped or stored in bulk |
| Works on anyone's photo, no questions asked | Refuses to run (`pipeline.py` exits) unless you pass `--consent`, an explicit acknowledgment that you have the right to search this photo |
| Sold to police, ICE, retailers, private individuals to identify strangers | Not sold to anyone; demoed and documented for **self-verification only** |
| Keeps your uploaded photo indefinitely | The query photo is hosted only long enough for the reverse-image search API to fetch it (auto-expires, default 10 minutes), then it's gone |
| Presents a "match" with confidence you can't audit | If no candidate clears the face-embedding threshold, the pipeline says so and **stops** — it never fabricates a match to make the demo look better |

If you fork this: **don't point it at someone else's photo without their
consent.** The guardrails below are code, not just this paragraph — but they
can obviously be stripped out by anyone determined to misuse this. Please
don't be that person.

---

## Architecture

| Stage | Module | What it actually does |
|---|---|---|
| 1. Face ID | `face_id/detector.py` | Detects the face and computes a Facenet512 embedding via [DeepFace](https://github.com/serengil/deepface). |
| 2. Web search | `web_search/reverse_search.py` | Calls SerpApi's `google_lens` engine — a real, live reverse-image search — and ranks results, preferring known social-media domains. |
| 2. Hosting | `web_search/image_host.py` | Briefly uploads the query photo to imgbb (self-expiring) since Lens needs a public URL to search against. |
| 2. Fallback | `web_search/yandex_search.py` | If Lens finds no verified match, tries SerpApi's `yandex_images` engine — an independently-crawled index that occasionally has posts Google hasn't indexed. Reuses the same `SERPAPI_API_KEY`. (Bing Visual Search was the original fallback; Microsoft fully retired the Bing Search APIs on August 11, 2025.) |
| 2.5 Verification | `verification/face_match.py` | Downloads each candidate image and re-runs stage 1's face encoding on *that* image, comparing cosine distance to the original. The "match" is confirmed by the face pipeline itself — not just Lens's visual-similarity score. |
| 3. Blockchain | `blockchain/` | Hashes the matched post's evidence (SHA-256) and writes the hash + source URL on-chain via the `PostRegistry` Solidity contract, on a local Hardhat Ethereum node. |
| Orchestration | `pipeline.py` | Runs all of the above end-to-end with a readable trace, and handles later re-verification. |

### Why only a hash goes on-chain

The full evidence bundle (URL, title, source, thumbnail, match distance,
timestamp) is saved off-chain as JSON in `output/`. Only its SHA-256 hash
(plus the source URL for human context) goes on-chain. To re-verify: recompute
the hash of the saved JSON and check it against `PostRegistry.getRecord(hash)`.
If the JSON was altered afterward, even by one byte, the recomputed hash
won't match anything on-chain — that mismatch *is* the tamper-evidence.
Run `python pipeline.py --tamper-demo` to see this live: it mutates a copy of
the evidence and shows re-verification fail in real time.

### Which blockchain, and why

A **local Ethereum node run via Hardhat** (`npx hardhat node`) — the
local/simulated chain option the task explicitly allows. That keeps the demo
fully self-contained (no wallet, no testnet faucet, no chain-side API keys)
while still being a real EVM executing a real Solidity contract
(`PostRegistry.sol`) with genuine transactions, block numbers, and an event
log — just on a private chain instead of a public one.

To move to a public testnet instead: point `CHAIN_RPC_URL` in `.env` at a
provider like Alchemy or Infura and fund an account from a faucet.
`registry.py` and `pipeline.py` need zero changes.

---

## Setup

### 1. Python dependencies

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

DeepFace downloads its model weights (~100 MB) on first run — needs internet
access once.

### 2. Blockchain (Node.js + Hardhat)

```bash
npm install
npx hardhat compile
```

### 3. API keys

```bash
copy .env.example .env
```

Fill in `.env`:

- `IMGBB_API_KEY` — free, no card, from https://api.imgbb.com/
- `SERPAPI_API_KEY` — free plan (100 searches/month, no card), from
  https://serpapi.com/manage-api-key. Powers both the primary Google Lens
  search and the Yandex fallback — no separate key needed.

---

## Running it

**Terminal 1** — start the local chain (leave running):

```bash
npx hardhat node
```

**Terminal 2** — run the full pipeline against **your own** photo:

```bash
python pipeline.py --image sample_data/your_photo.jpg --consent
```

Add `--tamper-demo` to watch a mutated record fail re-verification in the
same run.

**Re-verify later**, independent of the search step, against whichever
evidence file was saved:

```bash
python pipeline.py --verify output/evidence_20260905T120000Z.json
```

---

## Known limitations

- **Free-tier quotas.** SerpApi's free plan is 100 searches/month; imgbb's
  free tier is generous but not unlimited.
- **Face-match threshold is heuristic.** Facenet512's cosine-distance
  threshold (0.30) is DeepFace's published default, not tuned for this task —
  a low-quality candidate thumbnail is more likely to cause a false negative
  (real match missed) than a false positive.
- **Search coverage is bounded on purpose.** Google Lens and the Yandex
  fallback only surface what those engines have already indexed. A genuinely
  obscure or very recent post may not appear even if it exists. Closing that
  gap completely would mean building our own bulk face-indexing scraper —
  the Clearview/PimEyes approach — which this project deliberately avoids.
- **Chain state resets with the node.** `npx hardhat node` runs an in-memory
  chain; stopping it wipes all registered records. `blockchain/deployment.json`
  auto-redeploys the contract if the node has restarted. Fine for a demo, not
  a persistent ledger unless you point at a long-running node or public testnet.
- **A face match is evidence, not proof.** Facenet512's own benchmark accuracy
  (~99.65% on LFW) is measured on clean, frontal photo pairs — not compressed,
  filtered, or cropped social-media thumbnails. Real-world accuracy on that
  harder input is unmeasured and likely lower.
- **First match wins, not best match.** The pipeline stops at the first
  candidate that clears the threshold, in social-domain-first order — it
  doesn't compare every candidate and pick the globally closest one.
- **Verification uses the search engine's cached thumbnail**, not the live
  post image — a stale or differently-cropped thumbnail can make the
  embedding comparison diverge from what a human would conclude.
- **Single-face assumption.** `encode_face` picks the most confident face in
  the input photo; a group photo may not encode the face you intended.
- **No liveness/anti-spoof check.** The pipeline can't tell a real photo from
  a photo-of-a-photo or an AI-generated face.
- **Scope, by design.** This is built and demoed for **self-search only**. It
  is not hardened, tested, or intended for searching third parties' photos
  without their consent — see *Why this README leads with ethics* above.

---

## License

MIT. See `LICENSE`. The license covers the code, not permission to use it
against people who haven't agreed to be searched.
