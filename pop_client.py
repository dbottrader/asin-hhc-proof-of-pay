"""pop_client.py — read-only fetching of ASIN-HHC public artifacts.

Fetches JSON documents from the ASIN-HHC public artifacts base
(GitHub Pages). GET only, no credentials, no writes, short timeout so
unattended runs fail cleanly instead of hanging.

URL safety (catalog review, 2026-11-05): the model must never be able to
make this plugin fetch an arbitrary URL. Internal fetches (provenance
index, live board snapshot) go only to the configured base_url host over
https. A caller-supplied receipt_url is fetched only if it passes
is_safe_url: https scheme, a public (global) host, no userinfo, and no
redirect — at any hop — to an unsafe target. The check is stdlib-only
(urllib.parse + ipaddress + socket), mirroring the policy of Hermes'
tools.url_safety.is_safe_url, so the plugin keeps no Hermes dependency.
"""

import ipaddress
import json
import urllib.error
import urllib.parse
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


def _host_is_global(host):
    """True only for a public host, judged from the hostname as written —
    deliberately WITHOUT a DNS lookup. Rationale, measured on this
    machine: sandboxed/proxied environments return synthetic addresses
    (e.g. 198.18.0.0/15) for every public hostname, so resolving here
    would reject genuinely public hosts. Literal IPs must be global
    (private, loopback, link-local, reserved, multicast and unspecified
    all fail). Hostnames must be fully qualified public names: not
    localhost, not *.local, not single-label (intranet) names. Residual
    limitation, stated plainly: a hostile DNS answer (rebinding) is not
    caught by this check — the same limitation Hermes' own is_safe_url
    documents for its URL-form check. The fetch itself goes through the
    user's normal network stack/proxy, which resolves the name."""
    if not host:
        return False
    host = host.rstrip(".").lower()
    if host in ("localhost",):
        return False
    if host.endswith(".local"):
        return False
    if "." not in host:
        return False  # single-label names are intranet names
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass  # a dotted public hostname: accepted on its form
    return True


def is_safe_url(url):
    """Public-https-only URL gate for caller-supplied URLs.

    Returns (safe: bool, reason: str). Safe means: https scheme, no
    userinfo, a host present, and that host is public by form (see
    _host_is_global). The gate judges the URL as written and does not
    resolve DNS; a fetch after the check could in principle resolve
    differently (DNS rebinding), which is the same property Hermes' own
    is_safe_url has for its URL-form check — the gate is a policy check
    on the requested URL, not a guarantee about the network path.
    """
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError as e:
        return False, f"unparsable URL: {e}"
    if parts.scheme != "https":
        return False, "only https:// URLs are fetched"
    if parts.username or parts.password:
        return False, "URLs with embedded credentials are refused"
    if not parts.hostname:
        return False, "URL has no host"
    if not _host_is_global(parts.hostname):
        return False, (
            f"host {parts.hostname!r} is not a public host "
            "(private, loopback, link-local, reserved, or unresolvable)"
        )
    return True, ""


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect whose target fails the same safety check as
    the original URL (for external fetches) or leaves the base host
    (for internal fetches)."""

    def __init__(self, check):
        super().__init__()
        self._check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe, reason = self._check(newurl)
        if not safe:
            raise urllib.error.URLError(
                f"redirect to unsafe URL refused: {reason}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener_for(url, external):
    if external:
        check = lambda u: is_safe_url(u)  # noqa: E731
    else:
        base_host = urllib.parse.urlsplit(_base_url).hostname

        def check(u):  # noqa: E731
            parts = urllib.parse.urlsplit(str(u))
            if parts.scheme != "https":
                return False, "only https:// URLs are fetched"
            if parts.hostname != base_host:
                return False, (
                    f"internal fetches are limited to the configured "
                    f"base_url host {base_host!r}"
                )
            return True, ""

    return urllib.request.build_opener(_SafeRedirectHandler(check))


def fetch_json(url, external=False):
    """Fetch and parse a JSON document. Raises OSError/ValueError on failure.

    external=False (default): only the configured base_url host, https.
    external=True: any URL that passes is_safe_url (https, public host),
    with redirects gated the same way. Caller-supplied URLs must use
    external=True; internal artifact fetches must not.
    """
    if external:
        safe, reason = is_safe_url(url)
        if not safe:
            raise ValueError(f"unsafe receipt_url refused: {reason}")
    else:
        parts = urllib.parse.urlsplit(str(url))
        base_host = urllib.parse.urlsplit(_base_url).hostname
        if parts.scheme != "https" or parts.hostname != base_host:
            raise ValueError(
                "internal fetches are limited to the configured base_url "
                f"host {base_host!r} over https"
            )
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with _opener_for(url, external).open(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def provenance_index_url():
    return f"{_base_url}/specs/provenance-index.json"


def live_snapshot_url():
    return f"{_base_url}/live.json"
