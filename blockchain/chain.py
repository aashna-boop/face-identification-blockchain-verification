"""Connect to the local Hardhat chain and deploy/reuse PostRegistry.

The chain itself is `npx hardhat node` (a real local Ethereum node, just not
public) - the "local/simulated chain" option the task explicitly allows.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

_HERE = os.path.dirname(__file__)
ARTIFACT_PATH = os.path.join(
    _HERE, "artifacts", "blockchain", "contracts", "PostRegistry.sol", "PostRegistry.json"
)
DEPLOYMENT_PATH = os.path.join(_HERE, "deployment.json")
RPC_URL = os.getenv("CHAIN_RPC_URL", "http://127.0.0.1:8545")


def get_web3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        raise RuntimeError(
            f"Could not reach a local chain at {RPC_URL}.\n"
            "Start one first (in its own terminal, from the project root):\n"
            "    npx hardhat node"
        )
    w3.eth.default_account = w3.eth.accounts[0]
    return w3


def _load_artifact() -> dict:
    if not os.path.isfile(ARTIFACT_PATH):
        raise RuntimeError(
            "PostRegistry hasn't been compiled yet. From the project root run:\n"
            "    npm install\n"
            "    npx hardhat compile"
        )
    with open(ARTIFACT_PATH) as f:
        return json.load(f)


def get_or_deploy_contract(w3: Web3):
    """Deploy PostRegistry once per running Hardhat node, then reuse it.

    The deployed address is cached in deployment.json. If the node has been
    restarted since (its in-memory state resets), the cached address will
    have no code any more, so we redeploy automatically.
    """
    artifact = _load_artifact()
    abi, bytecode = artifact["abi"], artifact["bytecode"]

    if os.path.isfile(DEPLOYMENT_PATH):
        with open(DEPLOYMENT_PATH) as f:
            cached = json.load(f)
        address = Web3.to_checksum_address(cached["address"])
        if w3.eth.get_code(address) not in (b"", "0x"):
            return w3.eth.contract(address=address, abi=abi)

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = contract.constructor().transact()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    with open(DEPLOYMENT_PATH, "w") as f:
        json.dump({"address": receipt.contractAddress}, f)

    return w3.eth.contract(address=receipt.contractAddress, abi=abi)
