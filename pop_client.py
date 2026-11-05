"""pop_client.py — read-only fetching of ASIN-HHC public artifacts.

Fetches JSON documents from the ASIN-HHC public artifacts base
(GitHub Pages). GET only, no credentials, no writes, short timeout so
unattended runs fail cleanly instead of hanging.
"""

import json
import urllib.request

DEFAULT_BASE_URL = "https://dbottrader.github.io/asinmcp/artifacts"
_TIMEOUT = 20
_UA = "asin-hhc-proof-of-pay-hermes-plugin/0.1.0"

_base_url = DEFAULT_BASE_URL


def configure(base_url):
    global _base_url
    if base_url:
        _base_url = str(base_url).rstrip("/")


def base_url():
    return _base_url


def fetch_json(url):
    """Fetch and parse a JSON document. Raises OSError/ValueError on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def provenance_index_url():
    return f"{_base_url}/specs/provenance-index.json"


def live_snapshot_url():
    return f"{_base_url}/live.json"
