"""Version floors for the vendored browser assets in `frontend/`.

The static viewer renders operator package Markdown that embeds claim text from
untrusted source documents (`docs/THREAT_MODEL.md` lists both "frontend-loaded
JSON artifacts" and "source text itself" as untrusted). DOMPurify is the second
defense layer behind `escape_markdown_inline`, so a stale sanitizer is a real
regression rather than mere hygiene.

CI's `supply-chain` job runs pip-audit/CycloneDX over the *Python* environment
only, so nothing there can see these files. Without this module a re-vendor could
silently reintroduce a known-vulnerable sanitizer with a fully green pipeline —
which is exactly how DOMPurify 3.0.9 (CVE-2024-47875, fixed in 3.1.3) survived.

Stdlib only, offline: the version is parsed from the banner each upstream bundle
already ships.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# Floors, not pins. Raise when re-vendoring; never lower to make a test pass.
#
# dompurify: 3.1.3 is the 3.x fix for CVE-2024-47875 (nesting-based mXSS).
# marked: no known advisory for the 15.x line, so the floor is hygiene — it keeps
# the parser moving on the same cadence as the sanitizer.
MIN_DOMPURIFY_VERSION = (3, 1, 3)
MIN_MARKED_VERSION = (15, 0, 12)

DOMPURIFY_BANNER = re.compile(r"DOMPurify\s+(\d+)\.(\d+)\.(\d+)")
MARKED_BANNER = re.compile(r"marked\s+v(\d+)\.(\d+)\.(\d+)")


def _vendored_version(filename: str, pattern: re.Pattern[str]) -> tuple[int, int, int]:
    path = FRONTEND / filename
    assert path.is_file(), f"vendored asset is missing: {filename}"
    # The banner is the first comment block; reading a small head keeps this cheap
    # and avoids matching a version-like string deep inside minified code.
    head = path.read_text(encoding="utf-8")[:2048]
    match = pattern.search(head)
    assert match is not None, (
        f"{filename} has no parseable upstream version banner. "
        "Vendored assets must keep their upstream license/version header so the "
        "version floor stays enforceable."
    )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _format(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


@pytest.mark.parametrize(
    ("filename", "pattern", "minimum", "reason"),
    [
        (
            "purify.min.js",
            DOMPURIFY_BANNER,
            MIN_DOMPURIFY_VERSION,
            "DOMPurify < 3.1.3 is affected by CVE-2024-47875 (nesting-based mXSS)",
        ),
        (
            "marked.min.js",
            MARKED_BANNER,
            MIN_MARKED_VERSION,
            "marked below the recorded floor has not been reviewed for this viewer",
        ),
    ],
)
def test_vendored_asset_meets_version_floor(
    filename: str, pattern: re.Pattern[str], minimum: tuple[int, int, int], reason: str
) -> None:
    version = _vendored_version(filename, pattern)
    assert version >= minimum, (
        f"vendored {filename} is {_format(version)}, below the required "
        f"{_format(minimum)}: {reason}. Re-vendor from the upstream release and "
        "update THIRD_PARTY_LICENSES.md."
    )


def test_third_party_licenses_records_the_vendored_versions() -> None:
    """The license notice must name the versions actually shipped.

    `THIRD_PARTY_LICENSES.md` quoting a different version than the bundle is how
    an audit reaches the wrong conclusion about exposure, so tie them together.
    """
    notices = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")

    dompurify = _format(_vendored_version("purify.min.js", DOMPURIFY_BANNER))
    marked = _format(_vendored_version("marked.min.js", MARKED_BANNER))

    assert dompurify in notices, (
        f"THIRD_PARTY_LICENSES.md does not mention vendored DOMPurify {dompurify}"
    )
    assert marked in notices, (
        f"THIRD_PARTY_LICENSES.md does not mention vendored marked {marked}"
    )


def test_vendored_assets_keep_upstream_license_headers() -> None:
    """Minified bundles must retain their upstream attribution header."""
    purify_head = (FRONTEND / "purify.min.js").read_text(encoding="utf-8")[:2048]
    marked_head = (FRONTEND / "marked.min.js").read_text(encoding="utf-8")[:2048]

    assert "Cure53" in purify_head
    assert "Apache license 2.0" in purify_head or "Apache License 2.0" in purify_head
    assert "markedjs/marked" in marked_head
    assert "MIT" in marked_head
