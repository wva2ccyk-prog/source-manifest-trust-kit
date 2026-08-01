import json
import subprocess
import sys
from email.message import Message
from pathlib import Path

import pytest

from source_manifest_kit.acquisition import (
    ACQUISITION_INDEX_FILENAME,
    ACQUISITION_LOG_FILENAME,
    AcquisitionError,
    acquisition_log_to_analysis_manifest,
    fetch_acquisition_manifest,
    load_acquisition_manifest,
)
from source_manifest_kit.analysis_package import build_analysis_package_from_manifest


class _FakeResponse:
    def __init__(self, body: bytes, *, content_type: str = "text/plain", status: int = 200):
        self.body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, _size: int) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _write_manifest(path: Path, sources: list[dict], *, issue_id: str = "acquisition_issue") -> Path:
    path.write_text(json.dumps({"issue_id": issue_id, "sources": sources}), encoding="utf-8")
    return path


def _source(**overrides) -> dict:
    source = {
        "source_name": "official_note",
        "source_type": "official",
        "mode": "general",
        "url": "https://example.invalid/status",
    }
    source.update(overrides)
    return source


def _allow_example_invalid_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        assert host.endswith("example.invalid")
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("source_manifest_kit.acquisition.socket.getaddrinfo", _fake_getaddrinfo)


def test_acquisition_manifest_rejects_non_http_urls_duplicates_and_source_cap(tmp_path):
    bad_scheme = _write_manifest(tmp_path / "bad_scheme.json", [_source(url="file:///tmp/source.txt")])
    with pytest.raises(AcquisitionError, match="direct http\\(s\\) URL"):
        load_acquisition_manifest(bad_scheme)

    duplicate = _write_manifest(tmp_path / "duplicate.json", [_source(), _source(url="https://example.invalid/two")])
    with pytest.raises(AcquisitionError, match="duplicate source_name"):
        load_acquisition_manifest(duplicate)

    too_many = _write_manifest(
        tmp_path / "too_many.json",
        [_source(source_name=f"source_{index}", url=f"https://example.invalid/{index}") for index in range(21)],
    )
    with pytest.raises(AcquisitionError, match="per-run source cap"):
        load_acquisition_manifest(too_many)



def test_acquisition_manifest_rejects_private_literal_urls(tmp_path):
    manifest = _write_manifest(tmp_path / "private.json", [_source(url="http://127.0.0.1/status")])
    with pytest.raises(AcquisitionError, match="private or local network"):
        load_acquisition_manifest(manifest)


def test_acquisition_fetch_writes_frozen_log_index_and_review_gated_analysis_manifest(tmp_path, monkeypatch):
    _allow_example_invalid_dns(monkeypatch)
    manifest = _write_manifest(
        tmp_path / "manifest.json",
        [
            _source(title="Official status note"),
            _source(
                source_name="finance_commentary",
                source_type="analyst",
                mode="finance",
                url="https://example.invalid/finance",
                citation_note="Buy now with a 70 percent chance of a profitable trade this month.",
            ),
        ],
    )
    bodies = {
        "https://example.invalid/status": b"The agency said the review is scheduled for June.",
        "https://example.invalid/finance": b"Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.",
    }

    def _urlopen(request, timeout):
        assert timeout == 20
        return _FakeResponse(bodies[request.full_url])

    monkeypatch.setattr("source_manifest_kit.acquisition._safe_urlopen", _urlopen)
    log_path = fetch_acquisition_manifest(manifest_file=manifest, output_root=tmp_path / "acquired")
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert log_path.name == ACQUISITION_LOG_FILENAME
    assert [record["status"] for record in log["records"]] == ["fetched", "fetched"]
    assert all(Path(record["file_path"]).exists() for record in log["records"])
    assert log["records"][0]["content_hash_sha256"]
    index = (tmp_path / "acquired" / ACQUISITION_INDEX_FILENAME).read_text(encoding="utf-8")
    assert "ACQUISITION ONLY - NOT VERIFIED" in index
    assert "review gate" in index.lower()
    assert "70 percent chance" not in log_path.read_text(encoding="utf-8").lower()

    with pytest.raises(AcquisitionError, match="review confirmation"):
        acquisition_log_to_analysis_manifest(
            acquisition_log_file=log_path,
            output_path=tmp_path / "analysis_sources.json",
            confirm_reviewed=False,
        )
    analysis_manifest = acquisition_log_to_analysis_manifest(
        acquisition_log_file=log_path,
        output_path=tmp_path / "analysis_sources.json",
        confirm_reviewed=True,
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=analysis_manifest, output_root=tmp_path / "package")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    operator_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in [
            package_dir / "final_operator_package.md",
            Path(package_index["analysis_source_index"]),
            Path(package_index["bundle_summary"]),
            Path(package_index["verification_packet"]).with_suffix(".md"),
        ]
    )
    assert "[excluded-unsafe-finance-claim]" in operator_text
    assert "buy now" not in operator_text
    assert "target price is higher" not in operator_text
    assert "70 percent chance" not in operator_text


def test_acquisition_fetch_rejects_non_text_and_size_limited_records_from_conversion(tmp_path, monkeypatch):
    _allow_example_invalid_dns(monkeypatch)
    manifest = _write_manifest(
        tmp_path / "manifest.json",
        [
            _source(source_name="binary", url="https://example.invalid/binary"),
            _source(source_name="large", url="https://example.invalid/large"),
        ],
    )

    def _urlopen(request, timeout):
        if request.full_url.endswith("/binary"):
            return _FakeResponse(b"\x89PNG", content_type="image/png")
        return _FakeResponse(b"abcdef", content_type="text/plain")

    monkeypatch.setattr("source_manifest_kit.acquisition._safe_urlopen", _urlopen)
    log_path = fetch_acquisition_manifest(manifest_file=manifest, output_root=tmp_path / "acquired", byte_cap=4)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert [record["status"] for record in log["records"]] == ["rejected_content_type", "size_limit_exceeded"]
    assert all("file_path" not in record for record in log["records"])
    with pytest.raises(AcquisitionError, match="no fetched records"):
        acquisition_log_to_analysis_manifest(
            acquisition_log_file=log_path,
            output_path=tmp_path / "analysis_sources.json",
            confirm_reviewed=True,
        )


def test_acquisition_log_to_analysis_manifest_emits_relative_file_paths(tmp_path, monkeypatch):
    _allow_example_invalid_dns(monkeypatch)
    manifest = _write_manifest(tmp_path / "manifest.json", [_source()])

    def _urlopen(request, timeout):
        return _FakeResponse(b"The exchange posted a notice.", content_type="text/plain")

    monkeypatch.setattr("source_manifest_kit.acquisition._safe_urlopen", _urlopen)
    log_path = fetch_acquisition_manifest(manifest_file=manifest, output_root=tmp_path / "acquired")
    analysis_manifest_path = acquisition_log_to_analysis_manifest(
        acquisition_log_file=log_path,
        output_path=tmp_path / "analysis_sources.json",
        confirm_reviewed=True,
    )
    analysis_manifest = json.loads(analysis_manifest_path.read_text(encoding="utf-8"))
    source = analysis_manifest["sources"][0]
    assert not Path(source["file_path"]).is_absolute()
    assert "warnings" not in source
    # analysis-package must consume the relative path without any absolute-path opt-in.
    package_dir = build_analysis_package_from_manifest(source_manifest=analysis_manifest_path, output_root=tmp_path / "package")
    assert (package_dir / "final_operator_package.md").exists()


def test_acquisition_fetch_extracts_html_visible_text_and_preserves_raw_html(tmp_path, monkeypatch):
    _allow_example_invalid_dns(monkeypatch)
    manifest = _write_manifest(tmp_path / "manifest.json", [_source(source_name="html_page", url="https://example.invalid/html")])
    html = b"""
    <html>
      <head><title>Ignored title shell</title><style>.hidden{}</style></head>
      <body>
        <header>Global header navigation</header>
        <nav>Menu item one</nav>
        <input type="checkbox" value="void tag should not hide the page">
        <table class="navbox"><tr><td>Boilerplate taxonomy should be hidden</td></tr></table>
        <main>
          <h1>Agency statement</h1>
          <p>The agency said the review is scheduled for June.</p>
          <script>alert('ignore me')</script>
        </main>
        <footer>Footer links</footer>
      </body>
    </html>
    """

    def _urlopen(request, timeout):
        return _FakeResponse(html, content_type="text/html; charset=utf-8")

    monkeypatch.setattr("source_manifest_kit.acquisition._safe_urlopen", _urlopen)
    log_path = fetch_acquisition_manifest(manifest_file=manifest, output_root=tmp_path / "acquired")
    record = json.loads(log_path.read_text(encoding="utf-8"))["records"][0]
    downstream_text = Path(record["file_path"]).read_text(encoding="utf-8")
    raw_text = Path(record["raw_file_path"]).read_text(encoding="utf-8")
    assert "Agency statement" in downstream_text
    assert "The agency said the review is scheduled for June." in downstream_text
    assert "<nav>" not in downstream_text
    assert "Menu item one" not in downstream_text
    assert "Boilerplate taxonomy" not in downstream_text
    assert "alert" not in downstream_text
    assert "<nav>Menu item one</nav>" in raw_text
    assert "html_extracted_to_visible_text_raw_preserved" in record["warnings"]
    assert record["extracted_text_length_chars"] == len(downstream_text)


def test_cli_acquisition_validate_fetch_and_convert_smoke(tmp_path, monkeypatch):
    _allow_example_invalid_dns(monkeypatch)
    manifest = _write_manifest(tmp_path / "manifest.json", [_source()])

    def _urlopen(request, timeout):
        return _FakeResponse(b"The exchange posted a notice.", content_type="text/plain")

    monkeypatch.setattr("source_manifest_kit.acquisition._safe_urlopen", _urlopen)
    direct_log = fetch_acquisition_manifest(manifest_file=manifest, output_root=tmp_path / "acquired")
    validate_result = subprocess.run(
        [sys.executable, "-m", "source_manifest_kit", "acquisition-validate", "--manifest", str(manifest)],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert validate_result.returncode == 0, validate_result.stderr
    convert_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "acquisition-to-analysis-manifest",
            "--acquisition-log",
            str(direct_log),
            "--output",
            str(tmp_path / "analysis_sources.json"),
            "--confirm-reviewed",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert convert_result.returncode == 0, convert_result.stderr
    assert (tmp_path / "analysis_sources.json").exists()


def test_acquisition_manifest_rejects_invalid_port_noncanonical_ip_and_unicode_host(tmp_path):
    invalid_port = _write_manifest(tmp_path / "invalid_port.json", [_source(url="http://example.com:bad/path")])
    with pytest.raises(AcquisitionError, match="invalid port"):
        load_acquisition_manifest(invalid_port)

    integer_ipv4 = _write_manifest(tmp_path / "integer_ipv4.json", [_source(url="http://2130706433/status")])
    with pytest.raises(AcquisitionError, match="non-canonical IPv4"):
        load_acquisition_manifest(integer_ipv4)

    short_ipv4 = _write_manifest(tmp_path / "short_ipv4.json", [_source(url="http://127.1/status")])
    with pytest.raises(AcquisitionError, match="non-canonical IPv4"):
        load_acquisition_manifest(short_ipv4)

    unicode_host = _write_manifest(tmp_path / "unicode_host.json", [_source(url="http://ｅxample.com/status")])
    with pytest.raises(AcquisitionError, match="ASCII/IDNA"):
        load_acquisition_manifest(unicode_host)


def test_acquisition_validate_resolve_dns_blocks_private_resolution(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path / "manifest.json", [_source(url="https://example.invalid/status")])

    def _private_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", ("10.0.0.1", port))]

    monkeypatch.setattr("source_manifest_kit.acquisition.socket.getaddrinfo", _private_getaddrinfo)
    with pytest.raises(AcquisitionError, match="private or local network"):
        load_acquisition_manifest(manifest, resolve_dns=True)


def test_cli_acquisition_invalid_port_returns_clean_error(tmp_path):
    manifest = _write_manifest(tmp_path / "invalid_port.json", [_source(url="http://example.com:bad/path")])
    result = subprocess.run(
        [sys.executable, "-m", "source_manifest_kit", "acquisition-validate", "--manifest", str(manifest)],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "invalid port" in result.stderr
    assert "Traceback" not in result.stderr


def test_acquisition_manifest_rejects_wildcard_dns_embedded_private_ip(tmp_path):
    nip_io = _write_manifest(tmp_path / "nip_io.json", [_source(url="http://127.0.0.1.nip.io/status")])
    with pytest.raises(AcquisitionError, match="private or local network"):
        load_acquisition_manifest(nip_io)

    sslip_io_dashed = _write_manifest(tmp_path / "sslip_io.json", [_source(url="http://10-0-0-1.sslip.io/status")])
    with pytest.raises(AcquisitionError, match="private or local network"):
        load_acquisition_manifest(sslip_io_dashed)

    # A wildcard-DNS host whose embedded address is public is not blocked by this check.
    public_nip_io = _write_manifest(tmp_path / "public_nip_io.json", [_source(url="http://93.184.216.34.nip.io/status")])
    load_acquisition_manifest(public_nip_io)


def test_acquisition_manifest_rejects_ipv4_compatible_ipv6_loopback(tmp_path):
    manifest = _write_manifest(tmp_path / "ipv4_compatible.json", [_source(url="http://[::127.0.0.1]/status")])
    with pytest.raises(AcquisitionError, match="private or local network"):
        load_acquisition_manifest(manifest)


def test_acquisition_manifest_still_validates_ordinary_public_url(tmp_path):
    manifest = _write_manifest(tmp_path / "public.json", [_source(url="https://example.com/article")])
    normalized = load_acquisition_manifest(manifest)
    assert normalized["sources"][0]["url"] == "https://example.com/article"


def test_acquisition_fetch_pins_connection_to_validated_address(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path / "manifest.json", [_source(url="https://example.invalid/status")])

    getaddrinfo_calls = []

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        getaddrinfo_calls.append((host, port))
        assert host.endswith("example.invalid")
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("source_manifest_kit.acquisition.socket.getaddrinfo", _fake_getaddrinfo)

    connect_calls = []

    def _fake_create_connection(address, *args, **kwargs):
        connect_calls.append(address)
        raise OSError("no real network access in test")

    monkeypatch.setattr("source_manifest_kit.acquisition.socket.create_connection", _fake_create_connection)

    log_path = fetch_acquisition_manifest(manifest_file=manifest, output_root=tmp_path / "acquired")
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert log["records"][0]["status"] == "fetch_error"
    # The connection dialed the address resolved during the pre-flight check, not a
    # fresh hostname resolution performed by urllib/http.client at connect time -
    # a second resolution there would reopen the DNS-rebinding TOCTOU window.
    assert connect_calls == [("93.184.216.34", 443)]
    assert len(getaddrinfo_calls) == 1


def test_acquisition_fetch_boundary_records_the_dns_check_it_performed(tmp_path, monkeypatch):
    """The frozen boundary artifact must not understate the control that ran.

    The fetch path resolves each source and pins the connection to a validated
    public address, so `dns_checked_when_requested` has to be true here. It
    previously reported false because the manifest was loaded without
    `resolve_dns`, which made the operator-facing audit trail describe a weaker
    boundary than the one actually enforced.
    """
    manifest = _write_manifest(tmp_path / "boundary.json", [_source(url="https://example.invalid/status")])

    monkeypatch.setattr(
        "source_manifest_kit.acquisition.socket.getaddrinfo",
        lambda host, port, *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    def _fake_create_connection(address, *args, **kwargs):
        raise OSError("no real network access in test")

    monkeypatch.setattr("source_manifest_kit.acquisition.socket.create_connection", _fake_create_connection)

    output_root = tmp_path / "acquired"
    log_path = fetch_acquisition_manifest(manifest_file=manifest, output_root=output_root)

    normalized = json.loads((output_root / "acquisition_manifest.normalized.json").read_text(encoding="utf-8"))
    boundary = normalized["acquisition_boundary"]
    assert boundary["dns_checked_when_requested"] is True
    assert boundary["fetch_connection_pinned_to_validated_ip"] is True
    # Residual risk must stay disclosed: pinning narrows the rebinding window but
    # does not eliminate platform resolver behavior.
    assert boundary["dns_rebinding_not_fully_eliminated"] is True

    # The acquisition log embeds the same boundary block operators review.
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert log["acquisition_boundary"]["dns_checked_when_requested"] is True


def test_validate_only_path_does_not_claim_a_dns_check(tmp_path):
    """`load_acquisition_manifest` without resolve_dns must still report false."""
    manifest = _write_manifest(tmp_path / "validate_only.json", [_source(url="https://example.com/article")])
    normalized = load_acquisition_manifest(manifest)
    assert normalized["acquisition_boundary"]["dns_checked_when_requested"] is False
