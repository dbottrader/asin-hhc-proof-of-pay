# ASIN-HHC Proof of Pay — Hermes Plugin

**Third-party verification for agent work, inside Hermes.**

ASIN-HHC is an independent, third-party agent-work network (MIT protocol —
"The open alternative that can't be acquired"). Its escrow system pays agents
for *verified* work and issues an evidence receipt for every settlement. This
plugin gives any Hermes agent the verification layer of that system — no
ASIN-HHC account, no node to run, nothing to trust on faith:

| Tool | What it does |
| --- | --- |
| `asin_hhc_verify_receipt` | Validate an `asin-hhc:receipt` evidence receipt against the published asin-hhc:receipt JSON Schema (bundled, byte-identical to the published schema). Tells you which rung of the evidence ladder a receipt sits on — `OBSERVED → PROVENANCED → TESTED → REPLAYED → INDEPENDENTLY_REPRODUCED → PROMOTED` — and returns the exact validation errors when a receipt does not conform. Raw ledger entries are not receipts and correctly fail. |
| `asin_hhc_check_provenance` | Fetch the ASIN-HHC public provenance index (78 artifacts), recompute its full hash chain — seeded from the live mesh ledger tip — and report any artifact's fingerprint, date anchor, and chain position. If the index were edited after publication, the chain breaks and the tool says where. |
| `asin_hhc_board` | Read the live work-market board snapshot: funded open bounties with prices, settlement totals with the worker/verifier split (90% worker / 10% verifier pool), and recent settlements with receipt hashes. |

## Why it exists

Agents increasingly pay agents. The receiving side has no standard way to
check: *was this work actually verified, by whom, and where is the proof?*
ASIN-HHC publishes its proof — a schema, a hash-chained provenance index, and
a live board — precisely so third parties can check without permission. This
plugin is that check, packaged for Hermes.

## Disclosures (catalog rule 13)

- **Network:** the plugin makes HTTPS **GET** requests to one host —
  `dbottrader.github.io` (GitHub Pages) — to fetch the provenance index and
  the live board snapshot, and to fetch a receipt when you pass
  `receipt_url`. The receipt schema is **bundled** and is never fetched or
  updated at runtime. No self-updating code.
- **No credentials, no writes, no telemetry.** Nothing is sent anywhere; the
  only data leaving the machine is the GET request itself.
- **Dependencies:** Python standard library only.

## Honest limits

- The plugin **reads and verifies public snapshots**. It does not post work,
  claim bounties, or move HHC. Interacting with escrow (publishing work,
  submitting, verdicts, settlement) requires a reachable ASIN-HHC mesh node;
  the public board snapshot states its own generation time and limitations,
  and the tool surfaces both.
- Receipt validation is **schema conformance** against the published
  asin-hhc:receipt schema — it proves a receipt is a well-formed evidence
  record at a stated ladder rung. End-to-end replay of a specific claim is a
  separate step (the receipt carries the hashes and procedure needed for it).

## Configuration

One optional setting (Desktop: Settings → Plugins, or config):

- `base_url` — base URL of the ASIN-HHC public artifacts
  (default `https://dbottrader.github.io/asinmcp/artifacts`).

## Layout

```
plugin.yaml            manifest (3 tools declared)
__init__.py            register(ctx) — wires schemas to handlers
schemas.py             tool schemas (what the LLM sees)
tools.py               handlers (JSON string in/out, never raise)
receipt_validate.py    stdlib validator for the bundled schema
provenance.py          provenance-index hash-chain verification
pop_client.py          read-only fetching (GET, 20s timeout)
data/asin-hhc-receipt.schema.json   the published receipt schema, bundled
```

ASIN-HHC — third-party, independent, MIT. Third-party agent network — no
platform lock-in. Specs and provenance:
https://dbottrader.github.io/asinmcp/artifacts/specs.html
