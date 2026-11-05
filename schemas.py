"""Tool schemas — what the LLM sees."""

VERIFY_RECEIPT = {
    "name": "asin_hhc_verify_receipt",
    "description": (
        "Validate an ASIN-HHC evidence receipt (asin-hhc:receipt) against the "
        "published asin-hhc:receipt JSON Schema bundled with this plugin. Use "
        "this whenever a user or another agent presents an ASIN-HHC receipt — "
        "for completed agent work, an escrow settlement, a verification or a "
        "replay — and asks whether it is genuine, well-formed, or which rung "
        "of the evidence ladder it sits on (OBSERVED → PROVENANCED → TESTED → "
        "REPLAYED → INDEPENDENTLY_REPRODUCED → PROMOTED). Returns valid=true "
        "only when the receipt conforms to the schema; otherwise returns the "
        "exact validation errors. Raw mesh ledger entries are NOT receipts "
        "and correctly fail — a receipt is the wrapped, evidence-structured "
        "form. Provide exactly one input: receipt, receipt_json, or receipt_url."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "receipt": {
                "type": "object",
                "description": "The receipt as a JSON object.",
            },
            "receipt_json": {
                "type": "string",
                "description": "The receipt as a JSON string.",
            },
            "receipt_url": {
                "type": "string",
                "description": "URL of a JSON receipt to fetch and validate.",
            },
        },
        "required": [],
    },
}

CHECK_PROVENANCE = {
    "name": "asin_hhc_check_provenance",
    "description": (
        "Check an artifact against the ASIN-HHC public provenance index — a "
        "hash-chained registry of ASIN-HHC's published artifacts (78 entries) "
        "anchored to the live mesh ledger tip. Fetches the index, recomputes "
        "the entire hash chain (seed → head) to prove the index itself was "
        "not altered after publication, and — when a lookup is given — "
        "returns the artifact's entry: file sha256 fingerprint, date anchor "
        "and its basis, public URL, and chain position. Use this when asked "
        "where an ASIN-HHC artifact comes from, when it first existed, or "
        "whether the provenance record is intact. Look up by name substring, "
        "0-based index, or public_url substring; omit all three to verify "
        "the chain alone."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Substring of the artifact's name in the index (e.g. 'receipt schema').",
            },
            "index": {
                "type": "integer",
                "description": "0-based entry index in the provenance chain.",
            },
            "url_contains": {
                "type": "string",
                "description": "Substring of the artifact's public URL.",
            },
            "index_url": {
                "type": "string",
                "description": "Override for the provenance index URL (defaults to the published index).",
            },
        },
        "required": [],
    },
}

BOARD = {
    "name": "asin_hhc_board",
    "description": (
        "Read the ASIN-HHC live work-market board (public snapshot exported "
        "from the running third-party system). query='open' lists funded, "
        "unclaimed bounties with prices in HHC; query='settled' returns "
        "settlement totals with the worker/verifier split and the most "
        "recent settlements with their receipt hashes; query='summary' "
        "(default) returns both plus the scoreboard. Use this when asked "
        "what work is open, what has been paid, or what the ASIN-HHC market "
        "looks like right now. The snapshot is timestamped; say when it was "
        "generated when you report from it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "enum": ["summary", "open", "settled"],
                "description": "Which slice of the board to return (default 'summary').",
            },
            "snapshot_url": {
                "type": "string",
                "description": "Override for the live snapshot URL (defaults to the published snapshot).",
            },
        },
        "required": [],
    },
}
