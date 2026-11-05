"""provenance.py — verify the ASIN-HHC public provenance index hash chain.

Ported from the published verifier
(https://dbottrader.github.io/asinmcp/artifacts/specs/verify_index.py).

The index is a hash chain: entry 0's prev_index_hash is the ASIN-HHC mesh
ledger tip hash at build time (the seed), and every entry's index_hash is
sha256 over the canonical JSON of the entry (all fields except index_hash,
keys sorted). The chain head is the last entry's index_hash. Recomputing the
chain checks the index is internally consistent: every entry hashes
correctly and links to the previous one, so any altered entry breaks
its own hash and every link after it. It does not prove the publisher
did not re-issue the whole chain — that would need the seed or the
chain head anchored somewhere independent.

This module verifies the chain structure from the fetched index document
itself. File-level sha256 fingerprints recorded in entries can only be
recomputed where the canonical files are publicly fetchable; entries whose
public_url is set are reported, files are not downloaded here.

Stdlib only.
"""

import hashlib
import json


def canonical_hash(entry):
    canon = {k: entry[k] for k in sorted(entry) if k != "index_hash"}
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def verify_chain(index_doc):
    """Walk the full chain. Return a result dict (never raises)."""
    entries = index_doc.get("entries")
    anchor = index_doc.get("ledger_anchor") or {}
    seed = anchor.get("tip_hash")
    declared_head = index_doc.get("head_hash")
    result = {
        "entry_count": index_doc.get("entry_count"),
        "entries_seen": 0,
        "seed": seed,
        "ledger_anchor_height": anchor.get("height"),
        "declared_head": declared_head,
        "computed_head": None,
        "chain_valid": False,
        "first_break": None,
    }
    if not isinstance(entries, list) or not entries or not seed:
        result["first_break"] = "index document missing entries or ledger anchor"
        return result
    prev = seed
    for i, entry in enumerate(entries):
        result["entries_seen"] = i + 1
        if entry.get("prev_index_hash") != prev:
            result["first_break"] = (
                f"entry {i} ({entry.get('name')!r}): prev_index_hash does not "
                f"match the previous entry's index_hash"
            )
            return result
        recomputed = canonical_hash(entry)
        if recomputed != entry.get("index_hash"):
            result["first_break"] = (
                f"entry {i} ({entry.get('name')!r}): index_hash mismatch — "
                f"entry content was altered after publication"
            )
            return result
        prev = entry["index_hash"]
    result["computed_head"] = prev
    result["chain_valid"] = prev == declared_head
    if not result["chain_valid"]:
        result["first_break"] = "computed chain head != declared head_hash"
    return result


def find_entry(index_doc, name=None, index=None, url_contains=None):
    """Locate one entry by 0-based index, name substring, or public_url substring."""
    entries = index_doc.get("entries") or []
    if index is not None:
        if 0 <= index < len(entries):
            return entries[index]
        return None
    for entry in entries:
        if name and name.lower() in str(entry.get("name", "")).lower():
            return entry
        if url_contains and url_contains in str(entry.get("public_url") or ""):
            return entry
    return None


def entry_view(entry):
    """The factual fields a user needs to judge an artifact's provenance."""
    return {
        "index": entry.get("index"),
        "name": entry.get("name"),
        "kind": entry.get("kind"),
        "description": entry.get("description"),
        "public_url": entry.get("public_url"),
        "publish_status": entry.get("publish_status"),
        "file_sha256": entry.get("file_sha256"),
        "date_anchor": entry.get("date_anchor"),
        "date_anchor_basis": entry.get("date_anchor_basis"),
        "date_uncertain": entry.get("date_uncertain"),
        "traces_to": entry.get("traces_to"),
        "index_hash": entry.get("index_hash"),
        "prev_index_hash": entry.get("prev_index_hash"),
    }
