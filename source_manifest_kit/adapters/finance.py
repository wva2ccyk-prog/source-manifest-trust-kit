from __future__ import annotations

from source_manifest_kit.core.classification import classify_claim
from source_manifest_kit.core.schema import ClaimRecord, SourceRecord


def classify(text: str, source: SourceRecord) -> ClaimRecord:
    return classify_claim(text, source, "finance")
