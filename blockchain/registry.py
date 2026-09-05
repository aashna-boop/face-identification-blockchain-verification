"""Stage 3: register a discovered-post fingerprint on-chain, and re-verify it.

The evidence dict is hashed with SHA-256 into a bytes32 value; that's what
goes on-chain (plus the source URL for human context). The full evidence
JSON stays off-chain (saved under output/) - re-verification means
recomputing the same hash from that file and checking it against the
on-chain record, which is what makes tampering detectable.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .chain import get_or_deploy_contract, get_web3


def canonical_hash(evidence: Dict[str, Any]) -> bytes:
    blob = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).digest()  # exactly 32 bytes -> fits Solidity bytes32


def register_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    w3 = get_web3()
    contract = get_or_deploy_contract(w3)
    content_hash = canonical_hash(evidence)

    tx_hash = contract.functions.registerPost(
        content_hash, evidence.get("post_url", "")
    ).transact()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    block = w3.eth.get_block(receipt.blockNumber)

    return {
        "content_hash": "0x" + content_hash.hex(),
        "tx_hash": receipt.transactionHash.hex(),
        "block_number": receipt.blockNumber,
        "block_timestamp": block["timestamp"],
        "contract_address": contract.address,
        "submitter": w3.eth.default_account,
    }


def verify_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute the hash of `evidence` as it stands right now and look it
    up on-chain. If the evidence has been altered since registration, the
    recomputed hash won't match any record, so `on_chain` comes back False.
    """
    w3 = get_web3()
    contract = get_or_deploy_contract(w3)
    content_hash = canonical_hash(evidence)

    submitter, timestamp, source_url, exists = contract.functions.getRecord(content_hash).call()

    return {
        "content_hash": "0x" + content_hash.hex(),
        "on_chain": exists,
        "submitter": submitter,
        "timestamp": timestamp,
        "source_url": source_url,
        "contract_address": contract.address,
    }
