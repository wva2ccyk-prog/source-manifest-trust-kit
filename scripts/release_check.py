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
# caches (__pycache__, .pytest_cache) and packaging metadata (*.egg-info) are
# produced by running this very check plus the documented editable install, and
# are all gitignore-managed, so they are not treated as fatal here; the fatal
# set targets analysis/runtime outputs that would leak operator data.
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

# Tool-generated paths that the documented workflow itself creates. Each is
# gitignored, so flagging them makes the gate unpassable from a fresh clone that
# followed README's own install step (`pip install -e '.[dev]'`).
IGNORED_PATH_PARTS = {"__pycache__", ".pytest_cache"}
IGNORED_PART_SUFFIXES = (".egg-info",)


def _run(label: str, args: list[str], cwd: Path) -> None:
    print(f"[release-check] {label}: {' '.join(args)}")
    result = subprocess.run(args, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(f"[release-check] FAILED at: {label} (exit {result.returncode})")


def _is_tool_generated(parts: tuple[str, ...]) -> bool:
    """True for gitignore-managed build/test/packaging output.

    Verified against `git check-ignore` when git is available (see
    ``_assert_ignored_set_matches_git``); the static set keeps the gate working in
    a source archive with no git metadata.
    """
    for part in parts:
        if part in IGNORED_PATH_PARTS or part.endswith(IGNORED_PART_SUFFIXES):
            return True
    return False


def _scan_tree_for_generated_noise() -> list[str]:
    findings: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        rel = path.relative_to(REPO_ROOT)
        parts = rel.parts
        # Ignore a developer virtualenv if present; it is gitignored.
        if parts and parts[0] in {".venv", "venv", ".git", "build", "dist"}:
            continue
        if _is_tool_generated(parts):
            continue
        if path.is_dir():
            name = path.name
            if name in DISALLOWED_DIR_NAMES or name.startswith(DISALLOWED_DIR_PREFIXES):
                findings.append(str(rel) + "/")
        else:
            if path.suffix in DISALLOWED_SUFFIXES or path.name in DISALLOWED_EXACT:
                findings.append(str(rel))
    return sorted(set(findings))


def _assert_ignored_set_matches_git() -> None:
    """Fail loudly if anything exempted above is NOT actually gitignored.

    The exemptions are justified only by those paths being gitignore-managed. If
    that stops being true, the gate would be silently waving through a file that
    could really be committed, so confirm it rather than assume it.
    """
    # Pass real repo-relative paths: `git check-ignore` matches a pattern such as
    # `__pycache__/` against an actual path, not against a bare directory name.
    present: set[str] = set()
    for path in REPO_ROOT.rglob("*"):
        rel = path.relative_to(REPO_ROOT)
        if rel.parts and rel.parts[0] in {".venv", "venv", ".git", "build", "dist"}:
            continue
        if _is_tool_generated(rel.parts):
            # Record the shallowest generated ancestor, e.g. `pkg/__pycache__`.
            for depth in range(1, len(rel.parts) + 1):
                head = rel.parts[:depth]
                if _is_tool_generated(head):
                    present.add(Path(*head).as_posix())
                    break
    if not present:
        return
    targets = sorted(present)
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "check-ignore",
                "--no-index",
                *targets,
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("[release-check] note: git unavailable; skipped gitignore cross-check")
        return
    if result.returncode not in (0, 1):
        print("[release-check] note: git check-ignore unavailable; skipped cross-check")
        return
    ignored = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    unexpected = [name for name in targets if name not in ignored]
    if unexpected:
        raise SystemExit(
            "[release-check] FAILED: exempted path(s) are not gitignored, so they "
            "could be committed: " + ", ".join(unexpected)
        )


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

    _assert_ignored_set_matches_git()

    print("[release-check] PASS: tests, demo pipeline, and clean-tree check all succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
