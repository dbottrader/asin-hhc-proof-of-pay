#!/usr/bin/env python3
"""Local test run for the asin-hhc-proof-of-pay Hermes plugin.

No Hermes CLI is installed on this machine, so this harness loads the plugin
package the way Hermes does (package import, register(ctx)) with a stub ctx
that records registrations, then invokes the handlers exactly as the tool
registry would (args dict in, JSON string out).

Network tests hit the REAL public URLs. (The board tool used to be
exercised against a local snapshot via a file:// snapshot_url override;
that override was removed for URL safety in the 2026-11-05 Teknium fix,
so the board tests now read the public live.json directly.)
"""
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "asin-hhc-proof-of-pay"
sys.path.insert(0, str(PKG_DIR))

# --- load the plugin package with package semantics (hyphenated dir name) ---
spec = importlib.util.spec_from_file_location(
    "asin_hhc_pop", PKG_DIR / "__init__.py", submodule_search_locations=[str(PKG_DIR)]
)
plugin = importlib.util.module_from_spec(spec)
sys.modules["asin_hhc_pop"] = plugin
spec.loader.exec_module(plugin)

tools = plugin.tools
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


class StubCtx:
    def __init__(self):
        self.tools = {}

    def get_config(self, key, default=None):
        return default

    def register_tool(self, name, toolset, schema, handler):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}


# 1. registration + manifest drift
ctx = StubCtx()
plugin.register(ctx)
declared = []
in_tools = False
for line in (PKG_DIR / "plugin.yaml").read_text().splitlines():
    if line.startswith("provides_tools:"):
        in_tools = True
        continue
    if in_tools:
        s = line.strip()
        if s.startswith("- "):
            declared.append(s[2:])
        elif s and not line.startswith(" "):
            break
check("register() registers the 3 declared tools",
      sorted(ctx.tools) == sorted(declared) == sorted(
          ["asin_hhc_verify_receipt", "asin_hhc_check_provenance", "asin_hhc_board"]),
      f"registered={sorted(ctx.tools)}")
check("schemas' names match registered names",
      all(ctx.tools[n]["schema"]["name"] == n for n in ctx.tools))

H = {n: ctx.tools[n]["handler"] for n in ctx.tools}
J = lambda s: json.loads(s)

# 2. bundled schema == published schema (live fetch)
import hashlib
live_schema = urllib.request.urlopen(
    "https://dbottrader.github.io/asinmcp/artifacts/specs/asin-hhc-receipt.schema.json",
    timeout=30).read()
bundled_sha = hashlib.sha256((PKG_DIR / "data" / "asin-hhc-receipt.schema.json").read_bytes()).hexdigest()
live_sha = hashlib.sha256(live_schema).hexdigest()
check("bundled schema byte-identical to published schema",
      bundled_sha == live_sha, f"sha256={bundled_sha[:16]}…")

# 3. receipt verification: real evidence receipt (live system, cutover cycle)
sample = json.loads((ROOT / "tests" / "sample_evidence_receipt.json").read_text())
out = J(H["asin_hhc_verify_receipt"]({"receipt": sample}))
check("real evidence receipt validates", out.get("valid") is True, json.dumps(out)[:220])
import jsonschema
schema_doc = json.loads(live_schema.decode())
jsonschema.validate(sample, schema_doc)
check("reference jsonschema lib agrees (valid)", True)

raw = json.loads((ROOT / "tests" / "sample_raw_ledger_entry.json").read_text())
out_raw = J(H["asin_hhc_verify_receipt"]({"receipt": raw}))
try:
    jsonschema.validate(raw, schema_doc)
    ref_valid = True
except Exception:
    ref_valid = False
check("raw ledger entry correctly INVALID (plugin and reference agree)",
      out_raw.get("valid") is False and ref_valid is False,
      f"errors={out_raw.get('error_count')}")

tampered = dict(sample, status="PAID_IN_FULL")
out_t = J(H["asin_hhc_verify_receipt"]({"receipt_json": json.dumps(tampered)}))
check("tampered receipt (bogus status) INVALID via receipt_json input",
      out_t.get("valid") is False)

out_none = J(H["asin_hhc_verify_receipt"]({}))
check("missing input returns error JSON (never raises)", out_none.get("ok") is False)

# 4. provenance against the REAL public index
out_p = J(H["asin_hhc_check_provenance"]({}))
check("provenance chain verifies against public index",
      out_p.get("chain", {}).get("chain_valid") is True,
      f"entries={out_p.get('chain', {}).get('entries_seen')} head={str(out_p.get('chain', {}).get('computed_head'))[:16]}…")
out_e = J(H["asin_hhc_check_provenance"]({"name": "receipt schema"}))
check("entry lookup by name finds an entry with recomputed hash OK",
      out_e.get("entry") is not None and out_e.get("entry_hash_recomputed_ok") is True,
      f"entry={ (out_e.get('entry') or {}).get('name') }")

# 5. board: the public live snapshot (snapshot_url override was removed
# for URL safety — the tool always fetches the configured base_url host)
out_b = J(H["asin_hhc_board"]({"query": "open"}))
bounties = out_b.get("open_bounties", [])
check("board 'open' lists the funded bounties from the public snapshot",
      out_b.get("ok") is True and len(bounties) >= 1
      and abs((out_b.get("open_bounties_total_hhc") or 0)
              - sum(b.get("price_hhc") or 0 for b in bounties)) < 0.011
      and all(b.get("work_id") and b.get("escrow_id") for b in bounties),
      f"count={len(bounties)} total={out_b.get('open_bounties_total_hhc')} HHC")
out_s = J(H["asin_hhc_board"]({"query": "settled"}))
st = out_s.get("settlements", {})
check("board 'settled' returns settlement totals with splits",
      st.get("paid_count") is not None and st.get("settled_hhc_total") is not None
      and abs((st.get("to_workers_hhc") or 0) + (st.get("to_verifiers_hhc") or 0) - (st.get("settled_hhc_total") or 0)) < 0.011,
      json.dumps(st))
out_sum = J(H["asin_hhc_board"]({"query": "summary"}))
check("board 'summary' carries scoreboard + provenance head",
      out_sum.get("scoreboard", {}).get("agents") is not None
      and out_sum.get("provenance_head") == "fadbd275bc9885b12aa649af98e77d17a033aba6a22dc5dc12e6d8bc74fd85f6",
      f"agents={out_sum.get('scoreboard', {}).get('agents')}")

# 6. URL safety (catalog review 2026-11-05): arbitrary / private URLs
# must be refused; public https fetches must still work; the old
# index_url / snapshot_url overrides are gone.
import pop_client as _pc
check("is_safe_url accepts a public https URL",
      _pc.is_safe_url("https://dbottrader.github.io/asinmcp/artifacts/live.json")[0] is True)
check("is_safe_url refuses http",
      _pc.is_safe_url("http://dbottrader.github.io/asinmcp/artifacts/live.json")[0] is False)
for _bad in ("https://localhost/x.json", "https://127.0.0.1/x.json",
             "https://10.0.0.5/x.json", "https://192.168.1.1/x.json",
             "https://169.254.169.254/latest/meta-data/",
             "https://[::1]/x.json", "https://intranet/x.json",
             "https://user:pass@example.com/x.json"):
    check(f"is_safe_url refuses {_bad}",
          _pc.is_safe_url(_bad)[0] is False)
for _u, _why in (("http://dbottrader.github.io/asinmcp/artifacts/live.json", "http"),
                 ("https://localhost/asin-hhc-receipt.schema.json", "localhost"),
                 ("https://127.0.0.1/x.json", "loopback"),
                 ("https://10.0.0.5/x.json", "private"),
                 ("https://192.168.1.1/x.json", "private"),
                 ("https://169.254.169.254/latest/meta-data/", "link-local")):
    _o = J(H["asin_hhc_verify_receipt"]({"receipt_url": _u}))
    check(f"receipt_url {_why} URL refused",
          _o.get("ok") is False and "refused" in str(_o.get("error", "")).lower(),
          str(_o.get("error"))[:120])
# Positive control: a safe public https host fetches (an index is not a
# receipt, so valid=False is the expected outcome — the point is the
# fetch itself is allowed, not that the document validates).
_o = J(H["asin_hhc_verify_receipt"](
    {"receipt_url": "https://dbottrader.github.io/asinmcp/artifacts/specs/provenance-index.json"}))
check("receipt_url public https host fetches (document fetched, not a receipt)",
      _o.get("ok") is True and _o.get("valid") is False,
      f"ok={_o.get('ok')} valid={_o.get('valid')} errors={_o.get('error_count')}")
_o = J(H["asin_hhc_check_provenance"]({"index_url": "https://example.com/index.json"}))
check("index_url override removed (returns error)",
      _o.get("ok") is False and "removed" in str(_o.get("error", "")),
      str(_o.get("error"))[:120])
_o = J(H["asin_hhc_board"]({"query": "open", "snapshot_url": "https://example.com/live.json"}))
check("snapshot_url override removed (returns error)",
      _o.get("ok") is False and "removed" in str(_o.get("error", "")),
      str(_o.get("error"))[:120])

fails = [r for r in RESULTS if not r[1]]
print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} checks passed")
sys.exit(1 if fails else 0)
