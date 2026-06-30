from source_manifest_kit.core.schema import SourceRecord, utc_now
from source_manifest_kit.ledger.jsonl import read_jsonl, write_jsonl


def test_jsonl_write_read_source(tmp_path):
    source = SourceRecord("src_001", "run", "news", "demo", None, None, None, utc_now(), "observable", "input/source_001.txt")
    path = tmp_path / "sources.jsonl"
    write_jsonl(path, [source.to_dict()])
    rows = read_jsonl(path)
    assert rows[0]["source_type"] == "news"
