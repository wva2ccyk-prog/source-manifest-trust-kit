"""A non-UTF-8 source file must name the source, the byte, and the fix.

Operator source files arrive from mixed origins, so a mis-encoded file is an
ordinary intake mistake. The bare `UnicodeDecodeError` message identified neither
the offending source nor the requirement, which left the operator to guess which
entry in their manifest was at fault.

`UnicodeDecodeError` is already a `ValueError`, so exit code 2 and traceback
suppression were never broken; these tests pin the message quality and keep the
documented exit-code contract from regressing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from source_manifest_kit.core.text_io import read_source_text


REPO_ROOT = Path(__file__).resolve().parents[1]
# 0xff is never a valid UTF-8 lead byte; this is a UTF-16LE BOM + text, a common
# real-world mis-save from Windows editors.
NOT_UTF8_BYTES = b"\xff\xfe\x00b\x00a\x00d"


def _write_manifest(tmp_path: Path, source_path: Path, *, source_name: str = "bad_encoding_source") -> Path:
    manifest_path = tmp_path / "analysis_sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "encoding_issue",
                "sources": [
                    {
                        "source_name": source_name,
                        "source_type": "news",
                        "mode": "general",
                        "file_path": source_path.name,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_read_source_text_names_file_byte_and_remedy(tmp_path):
    bad = tmp_path / "mis_encoded.txt"
    bad.write_bytes(NOT_UTF8_BYTES)

    with pytest.raises(ValueError) as excinfo:
        read_source_text(bad, label="sources[1]")

    message = str(excinfo.value)
    assert "sources[1]" in message
    assert "mis_encoded.txt" in message
    assert "not valid UTF-8" in message
    assert "0xff" in message
    assert "Re-save the file as UTF-8" in message


def test_read_source_text_still_accepts_a_utf8_bom(tmp_path):
    """A leading BOM must keep being stripped, not treated as an error."""
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbfOfficials confirmed the schedule.")

    text = read_source_text(path)

    assert text.startswith("Officials")
    assert "\ufeff" not in text


def test_analysis_package_cli_reports_the_offending_source(tmp_path):
    source = tmp_path / "a.txt"
    source.write_bytes(NOT_UTF8_BYTES)
    manifest = _write_manifest(tmp_path, source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "analysis-package",
            "--source-manifest",
            str(manifest),
            "--output-root",
            str(tmp_path / "out"),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )

    # Documented CLI contract: validation/input errors exit 2 with no traceback.
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "bad_encoding_source" in result.stderr
    assert "not valid UTF-8" in result.stderr
    # The raw codec phrasing must not be what the operator sees.
    assert "codec can't decode" not in result.stderr
