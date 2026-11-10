import json
from pathlib import Path

from src.sources import parse_hf

FIXTURE = Path(__file__).parent / "fixtures" / "hf.json"


def test_parse_hf_maps_fields():
    items = parse_hf(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert items[0].source == "hf" and items[0].kind == "paper"
    assert items[0].url == "https://huggingface.co/papers/2511.00001"
    assert items[0].meta == "120 upvotes"


def test_parse_hf_skips_entries_without_paper_id():
    payload = [{"title": "no paper", "paper": {}}]
    assert parse_hf(payload) == []
