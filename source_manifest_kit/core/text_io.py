"""Shared operator-source text reading with an actionable encoding error.

Operator source files arrive from mixed origins (Windows editors, exported
transcripts, scraped artifacts), so a non-UTF-8 file is an ordinary intake
mistake rather than a rare edge case. Python's bare ``UnicodeDecodeError``
message ("'utf-8' codec can't decode byte 0xff in position 0") names neither the
file nor the requirement, which leaves the operator guessing which of their
sources is at fault.

``UnicodeDecodeError`` is already a ``ValueError`` subclass, so the CLI's handler
in ``cli.py`` catches it and exits ``2`` without a traceback. Only the message
text is unhelpful, so this wrapper preserves the class hierarchy and exit code
while naming the file, the offending byte, and the fix.
"""

from __future__ import annotations

from pathlib import Path


# utf-8-sig strips a leading UTF-8 BOM (common when operator source files are
# saved with Windows Notepad) so it never gets glued onto the first claim.
SOURCE_TEXT_ENCODING = "utf-8-sig"


def read_source_text(path: str | Path, *, label: str | None = None) -> str:
    """Read an operator source file as UTF-8, reporting decode failures usefully.

    ``label`` identifies the input in operator terms when the caller knows it,
    e.g. ``"sources[2]"`` for a manifest entry. Raises ``ValueError`` (via
    ``UnicodeDecodeError``'s own base) so existing CLI error handling is unchanged.
    """
    source_path = Path(path)
    try:
        return source_path.read_text(encoding=SOURCE_TEXT_ENCODING)
    except UnicodeDecodeError as exc:
        prefix = f"{label} " if label else ""
        raise ValueError(
            f"{prefix}source file is not valid UTF-8: {source_path}. "
            f"Decoding failed at byte {exc.start} (0x{exc.object[exc.start]:02x}). "
            "Local .txt/.md sources must be UTF-8 (a leading BOM is accepted). "
            "Re-save the file as UTF-8 and retry."
        ) from exc
