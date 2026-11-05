"""Tool handlers — ASIN-HHC Proof of Pay.

Three read-only verification tools over ASIN-HHC's published artifacts:

- asin_hhc_verify_receipt: validate an asin-hhc:receipt evidence receipt
  against the bundled published JSON Schema.
- asin_hhc_check_provenance: fetch the public provenance index, recompute
  its hash chain, and report one artifact's chain position.
- asin_hhc_board: read the public live board snapshot — open bounties and
  recent settlements with worker/verifier splits.

Handlers follow the Hermes contract: signature (args: dict, **kwargs),
always return a JSON string, never raise.
"""

import json

try:  # package context (Hermes loads the plugin as a package)
    from . import pop_client, provenance, receipt_validate
except ImportError:  # direct module context (tests, tooling)
    import pop_client, provenance, receipt_validate


def _err(msg):
    return json.dumps({"ok": False, "error": msg})


def verify_receipt(args: dict, **kwargs) -> str:
    """Validate an evidence receipt against the published asin-hhc:receipt schema."""
    try:
        receipt = args.get("receipt")
        if receipt is None and args.get("receipt_json"):
            try:
                receipt = json.loads(args["receipt_json"])
            except (ValueError, TypeError) as e:
                return _err(f"receipt_json is not valid JSON: {e}")
        if receipt is None and args.get("receipt_url"):
            # Caller-supplied URL: fetched only if it passes the public-
            # https safety gate (no http, no private/loopback/link-local
            # host, no redirect to one). See pop_client.is_safe_url.
            try:
                receipt = pop_client.fetch_json(args["receipt_url"], external=True)
            except Exception as e:
                return _err(f"could not fetch receipt_url: {e}")
        if receipt is None:
            return _err("provide one of: receipt (object), receipt_json (string), receipt_url")
        valid, errors = receipt_validate.validate_receipt(receipt)
        return json.dumps(
            {
                "ok": True,
                "valid": valid,
                "schema": "asin-hhc:receipt (bundled published schema, "
                f"sha256 {receipt_validate.schema_sha256()[:16]}…)",
                "errors": errors[:25],
                "error_count": len(errors),
                "receipt": receipt_validate.summarize(receipt)
                if isinstance(receipt, dict)
                else None,
            }
        )
    except Exception as e:  # handlers never raise
        return _err(f"verification failed: {e}")


def check_provenance(args: dict, **kwargs) -> str:
    """Verify the provenance index chain and look up one artifact in it."""
    try:
        # No URL override: the index is always fetched from the configured
        # base_url host. An index_url argument used to let the model point
        # the fetch at any host; it was removed for URL safety (catalog
        # review 2026-11-05).
        if args.get("index_url"):
            return _err(
                "index_url override was removed for URL safety: the "
                "provenance index is fetched only from the configured "
                "base_url host"
            )
        url = pop_client.provenance_index_url()
        try:
            doc = pop_client.fetch_json(url)
        except Exception as e:
            return _err(f"could not fetch provenance index ({url}): {e}")
        chain = provenance.verify_chain(doc)
        out = {"ok": True, "index_url": url, "chain": chain}
        name, idx, urlsub = args.get("name"), args.get("index"), args.get("url_contains")
        if name is not None or idx is not None or urlsub is not None:
            entry = provenance.find_entry(doc, name=name, index=idx, url_contains=urlsub)
            if entry is None:
                out["entry"] = None
                out["entry_note"] = "no entry matched the lookup"
            else:
                out["entry"] = provenance.entry_view(entry)
                out["entry_hash_recomputed_ok"] = (
                    provenance.canonical_hash(entry) == entry.get("index_hash")
                )
        return json.dumps(out)
    except Exception as e:
        return _err(f"provenance check failed: {e}")


def board(args: dict, **kwargs) -> str:
    """Answer what's open / what settled from the public live board snapshot."""
    try:
        query = (args.get("query") or "summary").lower()
        if query not in ("summary", "open", "settled"):
            return _err("query must be one of: summary, open, settled")
        # No URL override: the snapshot is always fetched from the
        # configured base_url host (see check_provenance above).
        if args.get("snapshot_url"):
            return _err(
                "snapshot_url override was removed for URL safety: the "
                "live board snapshot is fetched only from the configured "
                "base_url host"
            )
        url = pop_client.live_snapshot_url()
        try:
            snap = pop_client.fetch_json(url)
        except Exception as e:
            return _err(
                f"could not fetch live board snapshot ({url}): {e}. "
                "The snapshot is exported from the running ASIN-HHC system and "
                "published on the same cadence as the board page."
            )
        out = {
            "ok": True,
            "snapshot_url": url,
            "snapshot_generated_at": snap.get("generated_at_local"),
            "snapshot_mode": snap.get("mode"),
            "limitations": snap.get("limitations"),
        }
        if query in ("summary", "open"):
            out["open_bounties"] = [
                {
                    "title": b.get("title"),
                    "work_id": b.get("work_id"),
                    "escrow_id": b.get("escrow_id"),
                    "price_hhc": b.get("price_hhc"),
                    "state": b.get("state"),
                }
                for b in snap.get("open_bounties", [])
            ]
            out["open_bounties_total_hhc"] = sum(
                b.get("price_hhc") or 0 for b in snap.get("open_bounties", [])
            )
        if query in ("summary", "settled"):
            sb = snap.get("scoreboard", {})
            out["settlements"] = {
                "paid_count": sb.get("paid_settlements_count"),
                "refunded_count": sb.get("refunded_settlements_count"),
                "settled_hhc_total": sb.get("settled_hhc"),
                "to_workers_hhc": sb.get("settled_worker_hhc"),
                "to_verifiers_hhc": sb.get("settled_verifier_hhc"),
            }
            out["recent_settlements"] = [
                {
                    "ts": ev.get("ts_iso"),
                    "label": ev.get("label"),
                    "title": ev.get("title"),
                    "escrow_id": ev.get("escrow_id"),
                    "receipt": ev.get("receipt"),
                    "detail": ev.get("detail"),
                }
                for ev in snap.get("activity_feed", [])
                if "TERMINAL" in str(ev.get("detail", ""))
                or "settle" in str(ev.get("type", "")).lower()
            ][:10]
        if query == "summary":
            sb = snap.get("scoreboard", {})
            out["scoreboard"] = {
                "agents": sb.get("agents_count"),
                "external_joins": (sb.get("external_joins") or {}).get("count"),
                "escrows_by_state": sb.get("escrows_by_state"),
                "claims": sb.get("claims_count"),
            }
            out["provenance_head"] = (snap.get("provenance") or {}).get("head_hash")
        return json.dumps(out)
    except Exception as e:
        return _err(f"board read failed: {e}")
