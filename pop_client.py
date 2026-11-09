"""pop_client.py — read-only fetching of ASIN-HHC public artifacts.

Fetches JSON documents from the ASIN-HHC public artifacts base
(GitHub Pages). GET only, no credentials, no writes, short timeout so
unattended runs fail cleanly instead of hanging.

URL safety (catalog review, 2026-11-05 + 2026-11-09): the model must never be able to
make this plugin fetch an arbitrary URL. Internal fetches (provenance
index, live board snapshot) go only to the configured base_url host over
https. A caller-supplied receipt_url is fetched only if it passes
is_safe_url: https scheme, a public (global) host, no userinfo, and no
redirect — at any hop — to an unsafe target. The host is judged by form
AND by DNS: the name is resolved with socket.getaddrinfo and every
answer must be a global address (fail closed on a lookup error), so a
public-looking name that resolves to a private address (DNS rebinding)
is refused. When Hermes' tools.url_safety.is_safe_url imports, it is
used for the resolution step instead — it resolves too, and Hermes'
proxy fallback covers sandboxed environments that answer DNS with
synthetic addresses. The check is otherwise stdlib-only
(urllib.parse + ipaddress + socket), so the plugin keeps no Hermes
dependency when that module is absent.
"""

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

try:
    from tools.url_safety import is_safe_url as _hermes_is_safe_url
except Exception:  # Hermes not installed / module unavailable
    _hermes_is_safe_url = None

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
    """True only for a public host, judged from the hostname as written.

    This is the FORM check only — it never looks anything up. Literal IPs
    must be global (private, loopback, link-local, reserved, multicast
    and unspecified all fail). Hostnames must be fully qualified public
    names: not localhost, not *.local, not single-label (intranet) names.
    A dotted hostname that passes here still has to survive DNS
    resolution in is_safe_url before anything is fetched.
    """
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


def _resolve_addresses(host):
    """DNS answers for host as a sorted list of address strings.

    Separate seam so tests can stub DNS answers without touching the
    network (the live environment resolves for real here).
    """
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _resolved_host_is_global(host):
    """True only if the host resolves and EVERY answer is global.

    Literal IPs are judged directly, with no lookup. Hostnames are
    resolved with getaddrinfo; the check fails closed on a lookup error
    or an empty answer, and on any non-global answer (a public-looking
    name that resolves to 127.0.0.1, 10.x, 169.254.169.254, or any other
    private address is a DNS-rebinding attempt and is refused).
    """
    host = (host or "").rstrip(".").lower()
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass  # hostname: resolve it below
    try:
        addresses = _resolve_addresses(host)
    except (socket.gaierror, OSError):
        return False
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(a).is_global for a in addresses)
    except ValueError:
        return False


def is_safe_url(url):
    """Public-https-only URL gate for caller-supplied URLs.

    Returns (safe: bool, reason: str). Safe means: https scheme, no
    userinfo, a host present, that host is public by form (see
    _host_is_global), AND the host resolves to global addresses only
    (see _resolved_host_is_global). When Hermes'
    tools.url_safety.is_safe_url imports, the resolution step delegates
    to it — it resolves DNS and blocks non-global answers, the same
    policy this gate implements with getaddrinfo; if that call fails,
    this gate's own resolution check runs instead. A fetch after the
    check could in principle resolve differently (DNS rebinding between
    check and connect), so the gate is a policy check on the requested
    URL at check time, not a guarantee about the network path.
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
    if _hermes_is_safe_url is not None:
        try:
            verdict = _hermes_is_safe_url(url)
        except Exception:
            verdict = None
        if verdict is not None:
            if isinstance(verdict, tuple):
                return bool(verdict[0]), (
                    str(verdict[1]) if len(verdict) > 1 else ""
                )
            return bool(verdict), (
                "" if verdict
                else "refused by Hermes tools.url_safety.is_safe_url"
            )
    if not _resolved_host_is_global(parts.hostname):
        return False, (
            f"host {parts.hostname!r} does not resolve to global "
            "addresses only"
        )
    return True, ""


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect whose target fails the same safety check as
    the original URL (for external fetches) or leaves the base host
    (for internal fetches). External redirect targets go through
    is_safe_url, so every hop is resolved and checked, not just the
    first URL."""

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
    external=True: any URL that passes is_safe_url (https, public host
    resolved to global addresses only), with redirects gated the same
    way at every hop. Caller-supplied URLs must use external=True;
    internal artifact fetches must not.
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
