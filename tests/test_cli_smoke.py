from __future__ import annotations

import pytest

from source_manifest_kit.cli import main


def test_cli_help_imports_and_renders(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "Source Manifest Trust Kit" in output
    assert "analyze-file" in output
    assert "search-candidates-validate" in output
