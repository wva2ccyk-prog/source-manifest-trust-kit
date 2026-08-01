from __future__ import annotations

import functools
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .analysis_package import OPTIONAL_SOURCE_FIELDS, _normalize_source_type, _safe_markdown_inline, _safe_metadata, _safe_slug
from .core.schema import MODES
from .ledger.jsonl import write_json


ACQUISITION_LOG_FILENAME = "acquisition_log.json"
ACQUISITION_INDEX_FILENAME = "acquisition_source_index.md"
NORMALIZED_ACQUISITION_MANIFEST_FILENAME = "acquisition_manifest.normalized.json"
DIRECT_URL_ACQUISITION_METHOD = "direct_url_acquisition"

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_BYTE_CAP = 1_048_576
MAX_SOURCES_PER_RUN = 20
NONCANONICAL_IPV4_RE = re.compile(r"^(?:0x[0-9a-fA-F]+|0[0-7]+|\d+)(?:\.(?:0x[0-9a-fA-F]+|0[0-7]+|\d+)){0,3}$")
TEXT_CONTENT_TYPES = {
    "application/json",
    "application/xhtml+xml",
    "application/xml",
    "text/markdown",
    "text/xml",
}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
HTML_EXTRACTORS = {"builtin", "trafilatura", "readability"}
HTML_SKIP_TAGS = {
    "button",
    "footer",
    "form",
    "head",
    "header",
    "input",
    "nav",
    "noscript",
    "option",
    "script",
    "select",
    "style",
    "svg",
    "textarea",
}
HTML_VOID_SKIP_TAGS = {"input"}
HTML_BLOCK_TAGS = {
    "article",
    "br",
    "dd",
    "div",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "main",
    "p",
    "section",
    "td",
    "th",
    "tr",
}
HTML_BOILERPLATE_ATTR_MARKERS = (
    "ambox",
    "catlinks",
    "infobox",
    "metadata",
    "mw-editsection",
    "mw-table-of-contents",
    "navbox",
    "sidebar",
    "toccolours",
    "vector-main-menu",
    "vector-toc",
)
HTML_CONTENT_CONTAINER_TAGS = {"article", "body", "html", "main"}


class AcquisitionError(ValueError):
    """Raised when a direct-URL acquisition input or artifact is invalid."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_mode(value: Any, *, index: int) -> str:
    mode = str(value or "").strip().lower()
    if mode not in MODES:
        raise AcquisitionError(f"sources[{index}] mode must be one of: {', '.join(sorted(MODES))}")
    return mode


def _normalize_positive_int(value: Any, *, label: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError(f"{label} must be a positive integer.") from exc
    if normalized <= 0:
        raise AcquisitionError(f"{label} must be a positive integer.")
    return normalized


def _unwrap_ip_address(ip: Any) -> Any:
    """Unwrap IPv4-mapped / IPv4-compatible IPv6 literals to their embedded IPv4.

    ``ipaddress.IPv6Address.is_global`` already special-cases IPv4-MAPPED
    addresses (``::ffff:a.b.c.d``). It does NOT special-case the older
    IPv4-COMPATIBLE form (``::a.b.c.d``): a literal such as ``::127.0.0.1``
    or ``::10.0.0.1`` is classified purely as an ordinary IPv6 address and
    reports ``is_global`` True even though it targets an embedded
    private/loopback IPv4 host. The stdlib's own ``ipv4_compatible`` property
    was removed (RFC 4291 deprecated the form), so this parses the packed
    representation directly: an IPv4-compatible literal has its first 96 bits
    zero and is not the IPv4-mapped prefix (``::ffff:0:0/96``, already
    unwrapped above). The all-zero (``::``) and loopback (``::1``) addresses
    are excluded since those are meaningful IPv6 addresses in their own
    right and are already classified correctly as IPv6.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return mapped
    if isinstance(ip, ipaddress.IPv6Address) and int(ip) not in (0, 1):
        packed = ip.packed
        if packed[:12] == b"\x00" * 12:
            return ipaddress.IPv4Address(packed[12:])
    return ip


def _is_public_ip_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return _unwrap_ip_address(ip).is_global


def _is_literal_ip_address(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return True


# Wildcard-DNS providers whose hostnames resolve to an IPv4 address embedded
# directly in the hostname labels (e.g. "127.0.0.1.nip.io" -> 127.0.0.1).
# These hostnames are not literal IP addresses, so without this check they
# would pass the validate-only preflight even though they target an internal
# host once actually resolved.
_WILDCARD_DNS_PRIVATE_IP_SUFFIXES = (".nip.io", ".sslip.io")


def _extract_wildcard_dns_embedded_ip(hostname: str) -> str | None:
    lowered = hostname.casefold()
    for suffix in _WILDCARD_DNS_PRIVATE_IP_SUFFIXES:
        if not lowered.endswith(suffix):
            continue
        remainder = lowered[: -len(suffix)]
        for candidate in (remainder, remainder.replace("-", ".")):
            try:
                return str(ipaddress.IPv4Address(candidate))
            except ValueError:
                continue
    return None


def _normalize_hostname_for_network_check(hostname: str, *, index: int) -> str:
    normalized = hostname.strip().strip("[]").rstrip(".")
    if not normalized:
        raise AcquisitionError(f"sources[{index}] url must include a hostname.")
    try:
        ascii_hostname = normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise AcquisitionError(f"sources[{index}] url hostname must be valid IDNA.") from exc
    if any(ord(ch) > 127 for ch in normalized):
        raise AcquisitionError(
            f"sources[{index}] url hostname must be supplied in normalized ASCII/IDNA form to avoid visual-confusable hosts."
        )
    return ascii_hostname.casefold()


def _looks_like_noncanonical_ipv4(hostname: str) -> bool:
    if _is_literal_ip_address(hostname):
        return False
    if not NONCANONICAL_IPV4_RE.fullmatch(hostname):
        return False
    return hostname.count(".") != 3 or any(part.startswith(("0", "0x", "0X")) and part not in {"0"} for part in hostname.split("."))


def _assert_public_http_url(url: str, *, index: int, resolve_dns: bool) -> list[str]:
    """Validate a direct http(s) URL.

    When ``resolve_dns`` is True (the fetch path) this resolves the hostname once
    and returns the list of validated public addresses so the caller can PIN the
    actual connection to one of them, closing the DNS-rebinding TOCTOU gap. For
    literal-IP and validate-only paths an empty list is returned (nothing to pin;
    urllib will connect to the already-validated literal directly).
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise AcquisitionError(f"sources[{index}] url must be a direct http(s) URL.")
    if parsed.username or parsed.password:
        raise AcquisitionError(f"sources[{index}] url must not include embedded credentials.")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise AcquisitionError(f"sources[{index}] url has an invalid port.") from exc
    hostname = _normalize_hostname_for_network_check(parsed.hostname or "", index=index)
    lowered = hostname.casefold()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        raise AcquisitionError(f"sources[{index}] url resolves to a private or local network host.")
    if not _is_literal_ip_address(hostname):
        embedded_ip = _extract_wildcard_dns_embedded_ip(hostname)
        if embedded_ip is not None and not _is_public_ip_address(embedded_ip):
            raise AcquisitionError(f"sources[{index}] url resolves to a private or local network host.")
    if _looks_like_noncanonical_ipv4(hostname):
        raise AcquisitionError(f"sources[{index}] url uses a non-canonical IPv4 host form.")

    if _is_literal_ip_address(hostname):
        if not _is_public_ip_address(hostname):
            raise AcquisitionError(f"sources[{index}] url resolves to a private or local network host.")
        return []
    if not resolve_dns:
        return []

    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AcquisitionError(f"sources[{index}] url hostname could not be resolved before fetch.") from exc
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise AcquisitionError(f"sources[{index}] url hostname could not be resolved before fetch.")
    blocked = [address for address in addresses if not _is_public_ip_address(address)]
    if blocked:
        raise AcquisitionError(f"sources[{index}] url resolves to a private or local network host.")
    return addresses


def _validate_direct_url(value: Any, *, index: int, resolve_dns: bool = False) -> str:
    url = str(value or "").strip()
    _assert_public_http_url(url, index=index, resolve_dns=resolve_dns)
    return url


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(newurl, code, "redirects are not followed by direct acquisition", headers, fp)


def _reassert_pinned_public(address: str) -> None:
    """Re-validate the pinned IP is public immediately before connecting.

    Raised as OSError so urllib's do_open wraps it into a URLError (handled by the
    fetch loop as a normal fetch error) instead of escaping as an uncaught type.
    """
    if not _is_public_ip_address(address):
        raise OSError(f"pinned acquisition address {address!r} failed public re-validation")


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that dials a pre-validated pinned IP while keeping the
    original hostname for the ``Host:`` header (self.host is unchanged)."""

    def __init__(self, host, *args, pinned_ip: str, **kwargs) -> None:
        super().__init__(host, *args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:  # type: ignore[override]
        _reassert_pinned_public(self._pinned_ip)
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        if getattr(self, "_tunnel_host", None):
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that dials a pre-validated pinned IP but performs the TLS
    handshake (SNI + certificate verification) against the ORIGINAL hostname."""

    def __init__(self, host, *args, pinned_ip: str, **kwargs) -> None:
        super().__init__(host, *args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:  # type: ignore[override]
        _reassert_pinned_public(self._pinned_ip)
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        # server_hostname is the ORIGINAL host, so SNI and certificate hostname
        # verification use the real hostname, not the pinned IP. self._context is
        # a verifying ssl.create_default_context (see _PinnedHTTPSHandler).
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip

    def http_open(self, req):  # type: ignore[override]
        return self.do_open(functools.partial(_PinnedHTTPConnection, pinned_ip=self._pinned_ip), req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: str) -> None:
        super().__init__(context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def https_open(self, req):  # type: ignore[override]
        # Mirror urllib's own HTTPSHandler.https_open: pass only `context=`.
        # `self._context` (ssl.create_default_context()) already carries
        # check_hostname=True / verify_mode=CERT_REQUIRED, so certificate and
        # hostname verification stay on without needing a separate
        # check_hostname kwarg (which newer CPython versions no longer store
        # as a handler attribute).
        return self.do_open(
            functools.partial(_PinnedHTTPSConnection, pinned_ip=self._pinned_ip),
            req,
            context=self._context,
        )


def _safe_urlopen(request: urllib.request.Request, *, timeout: int):
    handlers: list[Any] = [urllib.request.ProxyHandler({}), _NoRedirectHandler]
    pinned = getattr(request, "_pinned_address", None)
    if pinned:
        handlers.append(_PinnedHTTPHandler(pinned))
        handlers.append(_PinnedHTTPSHandler(pinned))
    opener = urllib.request.build_opener(*handlers)
    return opener.open(request, timeout=timeout)


def _content_type(headers: Any) -> str | None:
    if hasattr(headers, "get_content_type"):
        return str(headers.get_content_type() or "").strip().lower() or None
    raw = str(headers.get("Content-Type") or "").split(";", maxsplit=1)[0].strip().lower()
    return raw or None


def _is_text_like_content_type(content_type: str | None) -> bool:
    return bool(content_type and (content_type.startswith("text/") or content_type in TEXT_CONTENT_TYPES))


def _decode_content(content: bytes, headers: Any) -> str:
    encoding = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
    return content.decode(encoding or "utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


class _VisibleHTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in HTML_VOID_SKIP_TAGS:
            return
        if normalized in HTML_SKIP_TAGS or (normalized not in HTML_CONTENT_CONTAINER_TAGS and self._is_boilerplate_element(attrs)):
            self._skip_stack.append(normalized)
            return
        if not self._skip_stack and normalized in HTML_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if self._skip_stack:
            if self._skip_stack[-1] == normalized:
                self._skip_stack.pop()
            return
        if normalized in HTML_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        stripped = " ".join(data.split())
        if stripped:
            self._parts.append(stripped)

    def _is_boilerplate_element(self, attrs: list[tuple[str, str | None]]) -> bool:
        attr_text = " ".join(str(value or "").lower() for key, value in attrs if key.lower() in {"class", "id", "role"})
        return any(marker in attr_text for marker in HTML_BOILERPLATE_ATTR_MARKERS)

    def text(self) -> str:
        combined = html.unescape(" ".join(self._parts))
        lines = [" ".join(line.split()) for line in combined.splitlines()]
        return "\n".join(line for line in lines if line).strip() + "\n"


def _extract_visible_html_text(decoded_html: str) -> str:
    parser = _VisibleHTMLTextExtractor()
    parser.feed(decoded_html)
    parser.close()
    return parser.text()


def _package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def _extract_html_text(decoded_html: str, *, extractor: str) -> tuple[str, dict[str, Any]]:
    normalized = str(extractor or "builtin").strip().lower()
    if normalized not in HTML_EXTRACTORS:
        raise AcquisitionError(f"html_extractor must be one of: {', '.join(sorted(HTML_EXTRACTORS))}")

    if normalized == "builtin":
        return _extract_visible_html_text(decoded_html), {
            "html_extractor": "builtin",
            "html_extractor_version": None,
            "html_extractor_fallback_used": False,
        }

    if normalized == "trafilatura":
        try:
            import trafilatura  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise AcquisitionError("trafilatura extractor requires the optional html extra.") from exc
        extracted = trafilatura.extract(decoded_html, include_comments=False, include_tables=True) or ""
        if extracted.strip():
            return extracted.strip() + "\n", {
                "html_extractor": "trafilatura",
                "html_extractor_version": _package_version("trafilatura"),
                "html_extractor_fallback_used": False,
            }
        fallback = _extract_visible_html_text(decoded_html)
        return fallback, {
            "html_extractor": "builtin",
            "html_extractor_requested": "trafilatura",
            "html_extractor_version": _package_version("trafilatura"),
            "html_extractor_fallback_used": True,
        }

    try:
        from readability import Document  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise AcquisitionError("readability extractor requires the optional html extra.") from exc
    document = Document(decoded_html)
    summary_html = document.summary(html_partial=True)
    extracted = _extract_visible_html_text(summary_html)
    if not extracted.strip():
        extracted = _extract_visible_html_text(decoded_html)
        return extracted, {
            "html_extractor": "builtin",
            "html_extractor_requested": "readability",
            "html_extractor_version": _package_version("readability-lxml"),
            "html_extractor_fallback_used": True,
        }
    return extracted, {
        "html_extractor": "readability",
        "html_extractor_version": _package_version("readability-lxml"),
        "html_extractor_fallback_used": False,
    }


def _safe_filename(index: int, source_name: str) -> str:
    return f"{index:03d}_{_safe_slug(source_name)}.txt"


def load_acquisition_manifest(manifest_file: str | Path, *, resolve_dns: bool = False) -> dict:
    manifest_path = Path(manifest_file)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AcquisitionError("Acquisition manifest must be a JSON object.")

    issue_id = str(data.get("issue_id") or "").strip()
    if not issue_id:
        raise AcquisitionError("Acquisition manifest requires a non-empty issue_id.")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise AcquisitionError("Acquisition manifest requires a non-empty sources list.")
    if len(sources) > MAX_SOURCES_PER_RUN:
        raise AcquisitionError(f"Acquisition manifest exceeds the per-run source cap of {MAX_SOURCES_PER_RUN}.")

    normalized_sources: list[dict] = []
    seen_names: set[str] = set()
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise AcquisitionError(f"sources[{index}] must be an object.")
        missing = sorted({"source_name", "source_type", "mode", "url"} - set(source))
        if missing:
            raise AcquisitionError(f"sources[{index}] missing fields: {', '.join(missing)}")
        source_name = str(source.get("source_name") or "").strip()
        if not source_name:
            raise AcquisitionError(f"sources[{index}] source_name must be non-empty.")
        name_key = source_name.casefold()
        if name_key in seen_names:
            raise AcquisitionError(f"sources[{index}] duplicate source_name: {source_name}")
        seen_names.add(name_key)

        mode = _normalize_mode(source.get("mode"), index=index)
        normalized = {
            "source_name": source_name,
            "source_type": _normalize_source_type(source.get("source_type")),
            "mode": mode,
            "url": _validate_direct_url(source.get("url"), index=index, resolve_dns=resolve_dns),
        }
        for field in sorted(OPTIONAL_SOURCE_FIELDS - {"source_url", "captured_at", "acquisition_method"}):
            value = source.get(field)
            if value is not None and str(value).strip():
                normalized[field] = _safe_metadata(value, mode=mode)
        normalized_sources.append(normalized)

    normalized_manifest = {
        "issue_id": issue_id,
        "acquisition_boundary": {
            "lane": "pre_runtime_direct_url_acquisition",
            "operator_authored_urls_only": True,
            "analysis_runtime_fetching": False,
            "source_truth_verified": False,
            "private_network_fetch_blocked": True,
            "redirects_followed": False,
            "dns_checked_when_requested": bool(resolve_dns),
            "dns_rebinding_not_fully_eliminated": True,
        },
        "sources": normalized_sources,
    }
    analysis_request = str(data.get("analysis_request") or "").strip()
    if analysis_request:
        normalized_manifest["analysis_request"] = _safe_metadata(analysis_request, mode="finance")
    return normalized_manifest


def write_acquisition_source_index(*, acquisition_log: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Direct URL Acquisition Index",
        "",
        f"- Issue ID: {_safe_markdown_inline(acquisition_log.get('issue_id'))}",
        "- Status: ACQUISITION ONLY - NOT VERIFIED.",
        "- Boundary: direct operator-provided HTTP(S) URLs are fetched before the local analysis runtime.",
        "- Review gate: inspect frozen artifacts and warnings before converting fetched records to `analysis_sources.json`.",
        "- Fetching content does not verify source truth, claim truth, or finance conclusions.",
        "",
        "## Source Records",
    ]
    records = acquisition_log.get("records") or []
    if not records:
        lines.append("- None")
    for index, record in enumerate(records, start=1):
        mode = record.get("mode") or "general"
        lines.extend(
            [
                "",
                f"### {index}. {_safe_metadata(record.get('source_name'), mode=mode)}",
                "",
                f"- Source type: {_safe_markdown_inline(record.get('source_type'))}",
                f"- Mode: {_safe_markdown_inline(mode)}",
                f"- Source URL: {_safe_markdown_inline(record.get('source_url'))}",
                f"- Fetch status: {_safe_markdown_inline(record.get('status'))}",
                f"- Fetched at: {_safe_markdown_inline(record.get('fetched_at'))}",
                f"- HTTP status: {_safe_markdown_inline(record.get('http_status') or 'not available')}",
                f"- Response content type: {_safe_markdown_inline(record.get('content_type') or 'not available')}",
            ]
        )
        if record.get("file_path"):
            lines.append(f"- Frozen local file: `{record.get('file_path')}`")
        if record.get("content_hash_sha256"):
            lines.append(f"- Content SHA-256: `{record.get('content_hash_sha256')}`")
        if record.get("content_length_bytes") is not None:
            lines.append(f"- Content length: {record.get('content_length_bytes')} bytes")
        for label, field in [
            ("Title", "title"),
            ("Publisher", "publisher"),
            ("Published at", "published_at"),
            ("Citation note", "citation_note"),
        ]:
            if record.get(field):
                lines.append(f"- {label}: {_safe_metadata(record.get(field), mode=mode)}")
        warnings = record.get("warnings") or []
        if warnings:
            lines.append(f"- Warnings: {', '.join(_safe_markdown_inline(warning) for warning in warnings)}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def fetch_acquisition_manifest(
    *,
    manifest_file: str | Path,
    output_root: str | Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    byte_cap: int = DEFAULT_BYTE_CAP,
    html_extractor: str = "builtin",
) -> Path:
    timeout = _normalize_positive_int(timeout_seconds, label="timeout_seconds")
    max_bytes = _normalize_positive_int(byte_cap, label="byte_cap")
    extractor_name = str(html_extractor or "builtin").strip().lower()
    if extractor_name not in HTML_EXTRACTORS:
        raise AcquisitionError(f"html_extractor must be one of: {', '.join(sorted(HTML_EXTRACTORS))}")
    normalized_manifest = load_acquisition_manifest(manifest_file)
    # The loader is called WITHOUT resolve_dns (a second resolution per source
    # would only add DNS traffic; the authoritative resolve happens per-source in
    # the fetch loop below, which pins the connection to a validated address).
    # Record the boundary from what this path actually does, otherwise the frozen
    # operator-facing audit artifact understates the control that ran.
    normalized_manifest["acquisition_boundary"]["dns_checked_when_requested"] = True
    normalized_manifest["acquisition_boundary"]["fetch_connection_pinned_to_validated_ip"] = True

    root = Path(output_root).resolve()
    source_dir = root / "acquired_sources" / _safe_slug(normalized_manifest["issue_id"])
    raw_source_dir = root / "raw_acquired_sources" / _safe_slug(normalized_manifest["issue_id"])
    source_dir.mkdir(parents=True, exist_ok=True)
    write_json(root / NORMALIZED_ACQUISITION_MANIFEST_FILENAME, normalized_manifest)

    records: list[dict] = []
    for index, source in enumerate(normalized_manifest["sources"], start=1):
        record: dict[str, Any] = {
            "issue_id": normalized_manifest["issue_id"],
            "source_name": source["source_name"],
            "source_type": source["source_type"],
            "mode": source["mode"],
            "source_url": source["url"],
            "fetched_at": _now_iso(),
            "acquisition_method": DIRECT_URL_ACQUISITION_METHOD,
            "review_required": True,
            "status": "fetch_error",
            "warnings": [],
            "http_status": None,
            "content_type": None,
            "content_hash_sha256": None,
            "content_length_bytes": None,
        }
        for field in sorted(OPTIONAL_SOURCE_FIELDS - {"source_url", "captured_at", "acquisition_method"}):
            if source.get(field):
                record[field] = source[field]

        try:
            pinned_addresses = _assert_public_http_url(source["url"], index=index, resolve_dns=True)
        except AcquisitionError as exc:
            record["status"] = "blocked_private_network"
            record["warnings"].append(str(exc))
            records.append(record)
            continue

        request = urllib.request.Request(source["url"], headers={"User-Agent": "InformationFinanceTrustOS-Acquisition/0.8B"})
        if pinned_addresses:
            # Pin the actual connection to a validated public IP so the fetch cannot
            # be re-pointed at a private address by a second DNS resolution
            # (DNS-rebinding TOCTOU between validate and connect).
            setattr(request, "_pinned_address", pinned_addresses[0])
        try:
            with _safe_urlopen(request, timeout=timeout) as response:
                record["http_status"] = getattr(response, "status", response.getcode())
                record["content_type"] = _content_type(response.headers)
                if not _is_text_like_content_type(record["content_type"]):
                    record["status"] = "rejected_content_type"
                    record["warnings"].append("content_type_not_text_like")
                else:
                    content = response.read(max_bytes + 1)
                    if len(content) > max_bytes:
                        record["status"] = "size_limit_exceeded"
                        record["warnings"].append("byte_cap_exceeded_no_frozen_file")
                        record["content_length_bytes"] = len(content)
                    else:
                        decoded = _decode_content(content, response.headers)
                        if record["content_type"] in HTML_CONTENT_TYPES:
                            raw_file_path = raw_source_dir / f"{index:03d}_{_safe_slug(source['source_name'])}.html"
                            raw_file_path.parent.mkdir(parents=True, exist_ok=True)
                            raw_file_path.write_text(decoded, encoding="utf-8")
                            record["raw_file_path"] = str(raw_file_path)
                            record["warnings"].append("html_extracted_to_visible_text_raw_preserved")
                            downstream_text, extractor_metadata = _extract_html_text(decoded, extractor=extractor_name)
                            record.update(extractor_metadata)
                            if extractor_metadata.get("html_extractor_fallback_used"):
                                record["warnings"].append("html_extractor_fallback_used")
                            record["extracted_text_length_chars"] = len(downstream_text)
                        else:
                            downstream_text = decoded
                        file_path = source_dir / _safe_filename(index, source["source_name"])
                        file_path.write_text(downstream_text, encoding="utf-8")
                        record["file_path"] = str(file_path)
                        record["content_hash_sha256"] = _hash_bytes(content)
                        record["content_length_bytes"] = len(content)
                        record["status"] = "fetched"
        except urllib.error.HTTPError as exc:
            record["http_status"] = exc.code
            if 300 <= int(exc.code) < 400:
                record["status"] = "redirect_blocked"
                record["warnings"].append("redirect_not_followed")
            else:
                record["status"] = "http_error"
                record["warnings"].append("http_error")
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            record["status"] = "fetch_error"
            record["warnings"].append("url_or_timeout_error")
        records.append(record)

    acquisition_log = {
        "issue_id": normalized_manifest["issue_id"],
        "acquisition_boundary": normalized_manifest["acquisition_boundary"],
        "limits": {
            "timeout_seconds": timeout,
            "byte_cap": max_bytes,
            "source_cap": MAX_SOURCES_PER_RUN,
        },
        "records": records,
    }
    log_path = root / ACQUISITION_LOG_FILENAME
    write_json(log_path, acquisition_log)
    write_acquisition_source_index(acquisition_log=acquisition_log, output_path=root / ACQUISITION_INDEX_FILENAME)
    return log_path


ABSOLUTE_PATH_WARNING = "absolute_path_requires_allow_absolute_flag"


def _manifest_relative_file_path(file_path: str, *, manifest_dir: Path) -> tuple[str, list[str]]:
    """Relativize a fetched artifact path against the analysis manifest directory.

    The analysis-package loader rejects absolute ``file_path`` entries by default
    (opt-in via ``--allow-absolute-source-paths``), so emit a manifest-relative
    path whenever the artifact sits under the manifest's parent directory. Files
    outside that tree (or on another drive, where ``os.path.relpath`` raises)
    keep the absolute path unchanged and carry a warning so the operator knows
    the analysis-package opt-in flag will be required.
    """
    try:
        relative = os.path.relpath(file_path, manifest_dir)
    except ValueError:
        # Different drive on Windows: no relative form exists.
        return file_path, [ABSOLUTE_PATH_WARNING]
    if relative == ".." or relative.startswith(".." + os.sep) or relative.startswith("../"):
        # Outside the manifest directory tree: the downstream traversal guard
        # rejects "..", so the relative form would be unusable.
        return file_path, [ABSOLUTE_PATH_WARNING]
    return relative.replace(os.sep, "/"), []


def acquisition_log_to_analysis_manifest(
    *,
    acquisition_log_file: str | Path,
    output_path: str | Path,
    confirm_reviewed: bool,
) -> Path:
    if not confirm_reviewed:
        raise AcquisitionError("Operator review confirmation is required before analysis manifest conversion.")
    acquisition_log = json.loads(Path(acquisition_log_file).read_text(encoding="utf-8"))
    if not isinstance(acquisition_log, dict):
        raise AcquisitionError("Acquisition log must be a JSON object.")
    issue_id = str(acquisition_log.get("issue_id") or "").strip()
    records = acquisition_log.get("records")
    if not issue_id or not isinstance(records, list):
        raise AcquisitionError("Acquisition log requires issue_id and records.")

    successful_records = [
        record
        for record in records
        if record.get("status") == "fetched" and str(record.get("file_path") or "").strip()
    ]
    if not successful_records:
        raise AcquisitionError("Acquisition log has no fetched records eligible for analysis manifest conversion.")

    output = Path(output_path)
    manifest_dir = output.resolve().parent
    sources: list[dict] = []
    for record in sorted(successful_records, key=lambda item: (str(item.get("source_name") or "").casefold(), str(item.get("file_path") or ""))):
        manifest_file_path, path_warnings = _manifest_relative_file_path(str(record["file_path"]), manifest_dir=manifest_dir)
        source = {
            "source_name": record["source_name"],
            "source_type": record["source_type"],
            "mode": record["mode"],
            "file_path": manifest_file_path,
            "source_url": record["source_url"],
            "captured_at": record["fetched_at"],
            "acquisition_method": DIRECT_URL_ACQUISITION_METHOD,
            "citation_note": "Direct URL acquisition artifact reviewed before local analysis manifest conversion. Acquisition does not verify source truth.",
        }
        for field in sorted(OPTIONAL_SOURCE_FIELDS - {"source_url", "captured_at", "acquisition_method", "citation_note"}):
            if record.get(field):
                source[field] = record[field]
        if record.get("citation_note"):
            source["citation_note"] = f"{record['citation_note']} | {source['citation_note']}"
        if path_warnings:
            source["warnings"] = path_warnings
        sources.append(source)

    manifest = {
        "issue_id": issue_id,
        "analysis_request": "Analyze reviewed local artifacts produced by the direct URL acquisition lane. Acquisition metadata is not source-truth verification.",
        "sources": sources,
    }
    write_json(output, manifest)
    return output
