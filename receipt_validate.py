"""receipt_validate.py — validate asin-hhc:receipt evidence receipts.

Validates a receipt against the bundled, published asin-hhc:receipt JSON
Schema (data/asin-hhc-receipt.schema.json — byte-identical to
https://dbottrader.github.io/asinmcp/artifacts/specs/asin-hhc-receipt.schema.json).

Stdlib only. Implements the JSON Schema (draft 2020-12) subset the published
schema actually uses: type, required, properties, additionalProperties,
enum, const, pattern, minimum, items, oneOf, and a date-time format check.
Adapted from the ASIN-HHC Tranche-1 validator approach (validate_receipts.py),
which cross-checks receipts against the same schema with the reference
`jsonschema` library; this subset validator is verified against that library
in the plugin's test suite (tests/run_tests.py) on real receipts.

No network access. No writes.
"""

import json
import re
from pathlib import Path

_PLUGIN_DIR = Path(__file__).parent
_SCHEMA_PATH = _PLUGIN_DIR / "data" / "asin-hhc-receipt.schema.json"

_SCHEMA = None


def load_schema():
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


def schema_sha256():
    import hashlib

    return hashlib.sha256(_SCHEMA_PATH.read_bytes()).hexdigest()


_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: (isinstance(v, (int, float)) and not isinstance(v, bool)),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}

_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _check(instance, schema, path, errors):
    if not isinstance(schema, dict):
        return
    if "oneOf" in schema:
        matches = 0
        for sub in schema["oneOf"]:
            sub_errors = []
            _check(instance, sub, path, sub_errors)
            if not sub_errors:
                matches += 1
        if matches != 1:
            errors.append(f"{path}: matches {matches} oneOf branches (expected exactly 1)")
        return
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    t = schema.get("type")
    if t is not None:
        check = _TYPE_CHECKS.get(t)
        if check is not None and not check(instance):
            errors.append(f"{path}: expected type {t}, got {type(instance).__name__}")
            return
    if isinstance(instance, str):
        pat = schema.get("pattern")
        if pat and not re.search(pat, instance):
            errors.append(f"{path}: {instance!r} does not match pattern {pat}")
        if schema.get("format") == "date-time" and not _DATETIME_RE.match(instance):
            errors.append(f"{path}: {instance!r} is not a valid RFC 3339 date-time")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                _check(value, props[key], f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property '{key}' not allowed")
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            _check(item, schema["items"], f"{path}[{i}]", errors)


def validate_receipt(receipt):
    """Return (valid: bool, errors: list[str]) for a receipt dict."""
    errors = []
    if not isinstance(receipt, dict):
        return False, ["receipt: expected a JSON object"]
    _check(receipt, load_schema(), "receipt", errors)
    return (len(errors) == 0), errors


def summarize(receipt):
    """Small factual summary of a receipt's evidence posture."""
    out = {
        "receipt_id": receipt.get("receipt_id"),
        "claim_id": receipt.get("claim_id"),
        "status": receipt.get("status"),
        "created_at": receipt.get("created_at"),
    }
    chain = receipt.get("chain")
    if isinstance(chain, dict):
        out["chain"] = {
            "seq": chain.get("seq"),
            "hash": chain.get("hash"),
            "prev_hash": chain.get("prev_hash"),
        }
    replay = receipt.get("replay")
    if isinstance(replay, dict):
        out["replay_status"] = replay.get("status")
    outputs = receipt.get("outputs")
    if isinstance(outputs, dict):
        out["result_hash"] = outputs.get("result_hash")
    return out
