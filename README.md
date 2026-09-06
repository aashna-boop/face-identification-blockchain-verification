# Face Identification & Blockchain Verification

Built for HH Goa 2026 Shortlisting Task 3.

A pipeline that takes a face photo, genuinely searches the web for a matching
social media post, re-verifies that the match is actually the same face, and
anchors a tamper-evident fingerprint of the discovered post on a local
blockchain — with a script that later re-verifies the saved evidence against
the on-chain record.

```
face photo → face encoding (DeepFace)
           → reverse-image search (SerpApi Google Lens)
           → re-verify candidate is the same face (cosine distance on embeddings)
           → hash the matched post's evidence (SHA-256)
           → register the hash on a local Ethereum chain (Hardhat + Solidity)
           → re-verify the saved evidence against the on-chain record
```

## Ethics & scope — read this first

Requirement #2 of the task ("use a face to find someone's social media") is,
at face value, the mechanism behind facial-recognition search tools like
Clearview AI / PimEyes, which have been widely criticized for enabling
stalking and doxxing. This project is built and demonstrated **only against
the author's own photo and the author's own public social media post** —
never against a stranger's photo without consent.

Practical guardrails baked into the code, not just this paragraph:

- `pipeline.py` refuses to run the full pipeline unless you pass `--consent`,
  a deliberate confirmation that you have the right to search for and anchor
  this particular photo.
- The photo is hosted temporarily (auto-expires, default 10 minutes) via
  imgbb only for the duration of the search call — it isn't kept anywhere
  public afterwards.
- The pipeline never fabricates a "match." If no candidate's face embedding
  actually matches the input within the model's threshold, it says so and
  stops rather than anchoring a guess.

**If you fork or reuse this code: don't point it at other people's photos
without their consent.**

## Architecture

| Stage | Module | What it does |
|---|---|---|
| 1. Face ID | [`face_id/detector.py`](face_id/detector.py) | Detects the face and computes a Facenet512 embedding via [DeepFace](https://github.com/serengil/deepface). |
| 2. Web search | [`web_search/reverse_search.py`](web_search/reverse_search.py) | Calls SerpApi's `google_lens` engine (a real, live reverse-image search) and ranks results, preferring known social-media domains. |
| — hosting | [`web_search/image_host.py`](web_search/image_host.py) | Briefly uploads the photo to imgbb (self-expiring) since Lens needs a public URL. |
| 2 (fallback) | [`web_search/bing_search.py`](web_search/bing_search.py) | If Lens finds no verified match, tries Bing Visual Search — a different, independently-crawled index that sometimes has a post Google hasn't indexed (e.g. lower-engagement accounts). Only runs if `BING_VISUAL_SEARCH_API_KEY` is set; skipped otherwise. |
| 2.5 Verification | [`verification/face_match.py`](verification/face_match.py) | Downloads each candidate image and re-runs stage 1's face encoding on it, comparing cosine distance to the original — the "match" is confirmed by the face pipeline itself, not just Lens's visual similarity score. |
| 3. Blockchain | [`blockchain/`](blockchain/) | Hashes the matched post's metadata (SHA-256), stores the hash + source URL on-chain via the `PostRegistry` Solidity contract, on a local Hardhat Ethereum node. |
| Orchestration | [`pipeline.py`](pipeline.py) | Runs all of the above end-to-end and prints a readable trace for the demo recording. |

### Why a hash goes on-chain, not the whole post

The full "discovered post" evidence (URL, title, source, thumbnail, match
distance, timestamp) is saved off-chain as JSON in `output/`. Only its
SHA-256 hash (plus the source URL, for human context) is written on-chain.
Re-verification means recomputing the hash of the saved JSON and checking it
against `PostRegistry.getRecord(hash)`: if the JSON was altered even slightly
afterwards, the recomputed hash won't match anything on-chain — that
mismatch *is* the tamper-evidence. `pipeline.py --tamper-demo` shows this
directly by mutating a copy of the evidence and re-verifying it live.

## Which blockchain

A **local Ethereum node run via Hardhat** (`npx hardhat node`), which is the
"local/simulated chain" option the task explicitly allows. This keeps the
demo fully self-contained (no wallet, no testnet faucet, no API keys for the
chain itself) while still being a real EVM executing a real Solidity
contract — `PostRegistry.sol` — with genuine transactions, block numbers,
and an event log, just on a private chain instead of a public one.

To move this to a public testnet instead, only `blockchain/chain.py` needs
to change: point `CHAIN_RPC_URL` (in `.env`) at a provider like Alchemy/
Infura and fund an account from a faucet; `registry.py` and `pipeline.py`
don't need to change at all.

## Setup

### 1. Python dependencies

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

The first run of DeepFace downloads its model weights (~100 MB) from GitHub
automatically — needs internet access once.

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
- `SERPAPI_API_KEY` — free plan (100 searches/month, no card), from https://serpapi.com/manage-api-key
- `BING_VISUAL_SEARCH_API_KEY` — optional. Free F0 tier (1,000 transactions/month) from a Bing Search v7 resource at https://portal.azure.com/. Only used as a fallback if Google Lens finds no verified match; leave blank to skip it.

## Running it

**Terminal 1** — start the local chain (leave running):

```bash
npx hardhat node
```

**Terminal 2** — run the full pipeline against your own photo:

```bash
python pipeline.py --image sample_data/your_photo.jpg --consent
```

Add `--tamper-demo` to also see a mutated record fail re-verification in the
same run.

**Re-verify later**, independent of the search step, against whichever
evidence file the run above saved:

```bash
python pipeline.py --verify output/evidence_20260905T120000Z.json
```

## Known limitations

- **Free-tier quotas.** SerpApi's free plan is 100 searches/month; imgbb's
  free tier is generous but not unlimited.
- **Face-match threshold is heuristic.** Facenet512's cosine-distance
  threshold (0.30) is DeepFace's published default, not tuned for this
  specific task — a low-quality candidate thumbnail can produce a false
  negative (real match missed) more easily than a false positive.
- **Reverse-image search coverage.** Google Lens (via SerpApi) only surfaces
  what Google has indexed; a genuinely obscure, very recent, or
  low-engagement post may not appear even if it exists. The optional Bing
  Visual Search fallback (`web_search/bing_search.py`) helps by checking a
  second, independently-crawled index, but it's still bounded by whatever
  Bing itself has indexed — no reverse-image search can surface a post that
  no crawler has ever picked up. That gap is deliberate: closing it fully
  would mean building our own bulk social-media scraper/face-index (the
  Clearview AI/PimEyes approach), which this project intentionally avoids —
  see Ethics & scope above.
- **Chain state resets with the node.** Since `npx hardhat node` runs an
  in-memory chain, stopping it wipes all registered records; the cached
  contract address in `blockchain/deployment.json` is auto-redeployed if the
  node has restarted. This is fine for demoing the mechanism, but it's not
  a persistent ledger across sessions unless you point `CHAIN_RPC_URL` at a
  long-running node or public testnet instead.
- **Not exhaustive identity verification.** A face-embedding match is
  evidence, not proof, of identity — it's presented here as "verified
  within this pipeline's threshold," not a legal or forensic guarantee.
  Facenet512's own published benchmark accuracy (~99.65% on the LFW dataset)
  is measured on clean, frontal photo pairs, not compressed/filtered/cropped
  social-media thumbnails — real-world accuracy on that harder input is
  unmeasured and almost certainly lower.
- **First match wins, not best match.** `pipeline.py` stops at the first
  candidate whose embedding clears the threshold, in social-domain-first
  order — it does not compare every candidate and pick the globally closest
  one.
- **Verification uses the search engine's cached thumbnail, not the live
  post image.** If Lens's thumbnail is stale, watermarked, or cropped
  differently from the actual post, the embedding comparison can diverge
  from what a human looking at the real post would conclude.
- **Single-face assumption.** `encode_face` picks the most confident face
  in the input photo; a group photo will be encoded using whichever face
  DeepFace is most confident about, not necessarily the intended one.
- **No liveness/anti-spoof check.** The pipeline can't distinguish a real
  photo from a photo-of-a-photo or an AI-generated face — anything that
  produces a detectable face embedding is accepted as input.
- **Scope, by design.** As covered above, this is built and demoed for
  self-search only; it is not hardened or intended for searching third
  parties' photos without their consent.
