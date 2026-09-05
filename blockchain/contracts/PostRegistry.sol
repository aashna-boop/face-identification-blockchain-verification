// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title PostRegistry
/// @notice Anchors a fingerprint (SHA-256 hash) of an off-chain "discovered
/// post" evidence bundle on-chain, so it can later be re-verified as
/// tamper-evident: recompute the hash of the evidence and compare it to
/// what was registered here. The full post content is never stored
/// on-chain, only its hash plus a small amount of context.
contract PostRegistry {
    struct Record {
        address submitter;
        uint256 timestamp;
        string sourceUrl;
        bool exists;
    }

    mapping(bytes32 => Record) private records;
    bytes32[] public recordIds;

    event PostRegistered(
        bytes32 indexed contentHash,
        address indexed submitter,
        uint256 timestamp,
        string sourceUrl
    );

    /// @notice Register a new evidence fingerprint. Reverts if this exact
    /// hash was already registered, so records can't be silently overwritten.
    function registerPost(bytes32 contentHash, string calldata sourceUrl) external {
        require(!records[contentHash].exists, "PostRegistry: already registered");
        records[contentHash] = Record({
            submitter: msg.sender,
            timestamp: block.timestamp,
            sourceUrl: sourceUrl,
            exists: true
        });
        recordIds.push(contentHash);
        emit PostRegistered(contentHash, msg.sender, block.timestamp, sourceUrl);
    }

    /// @notice Re-verify a fingerprint against the on-chain record.
    function getRecord(bytes32 contentHash)
        external
        view
        returns (address submitter, uint256 timestamp, string memory sourceUrl, bool exists)
    {
        Record memory r = records[contentHash];
        return (r.submitter, r.timestamp, r.sourceUrl, r.exists);
    }

    function totalRecords() external view returns (uint256) {
        return recordIds.length;
    }
}
