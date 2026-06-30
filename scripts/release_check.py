"""Fresh-clone release check for source-manifest-trust-kit.

Runs the deterministic test suite, exercises the demo analysis pipeline in a
temporary output directory, and confirms the publishable package tree is not
left with unexpected generated files.

Usage:
    python scripts/release_check.py

No network access or API key is required.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Generated artifacts that must never be committed in the publishable tree.
# Generated output directories that should never be committed. Build/test
# caches (__pycache__, .pytest_cache) are produced by running this very check
# and are gitignore-managed, so they are not treated as fatal here; the fatal
# set targets analysis/runtime outputs and stale packaging metadata.
DISALLOWED_DIR_NAMES = {
    ".mypy_cache",
    ".ruff_cache",
    "workspace",
    "issues",
    "operator_package",
    "provider_template",
    "acquired_sources",
    "raw_acquired_sources",
}
DISALLOWED_DIR_PREFIXES = ("workspace",)
DISALLOWED_SUFFIXES = {".log", ".db", ".sqlite", ".sqlite3"}
DISALLOWED_EXACT = {".coverage"}


def _run(label: str, args: list[str], cwd: Path) -> None:
    print(f"[release-check] {label}: {' '.join(args)}")
    result = subprocess.run(args, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(f"[release-check] FAILED at: {label} (exit {result.returncode})")


def _scan_tree_for_generated_noise() -> list[str]:
    findings: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        rel = path.relative_to(REPO_ROOT)
        parts = rel.parts
        # Ignore a developer virtualenv if present; it is gitignored.
        if parts and parts[0] in {".venv", "venv", ".git", "build", "dist"}:
            continue
        if "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        if any(p.endswith(".egg-info") for p in parts):
            findings.append(str(rel))
            continue
        if path.is_dir():
            name = path.name
            if name in DISALLOWED_DIR_NAMES or name.startswith(DISALLOWED_DIR_PREFIXES):
                findings.append(str(rel) + "/")
        else:
            if path.suffix in DISALLOWED_SUFFIXES or path.name in DISALLOWED_EXACT:
                findings.append(str(rel))
    return sorted(set(findings))


def main() -> int:
    _run("tests", [sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT)

    with tempfile.TemporaryDirectory(prefix="smtk_release_") as tmp:
        out_root = Path(tmp) / "workspace"
        manifest = REPO_ROOT / "examples" / "synthetic_analysis_sources.json"
        _run(
            "demo analysis-package",
            [
                sys.executable,
                "-m",
                "source_manifest_kit",
                "analysis-package",
                "--source-manifest",
                str(manifest),
                "--output-root",
                str(out_root),
                "--excluded-detail-mode",
                "detailed",
            ],
            cwd=REPO_ROOT,
        )
        packet_dir = out_root / "operator_package"
        _run(
            "demo llm-review-packet",
            [
                sys.executable,
                "-m",
                "source_manifest_kit",
                "llm-review-packet",
                "--operator-package-dir",
                str(packet_dir),
            ],
            cwd=REPO_ROOT,
        )
        produced = list(out_root.rglob("*"))
        if not produced:
            raise SystemExit("[release-check] FAILED: demo pipeline produced no output")
        print(f"[release-check] demo produced {len(produced)} files in temp output root")

    noise = _scan_tree_for_generated_noise()
    if noise:
        print("[release-check] FAILED: unexpected generated files in package tree:")
        for item in noise:
            print(f"  - {item}")
        return 1

    print("[release-check] PASS: tests, demo pipeline, and clean-tree check all succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())