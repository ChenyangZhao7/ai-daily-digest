from datetime import datetime, timezone

from src.models import Item
from src.summarize import build_messages, parse_llm_response, score_items

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
CFG = {"llm": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat", "timeout": 30}}

IDS = {"a", "b"}


def test_parse_plain_json():
    out = parse_llm_response('[{"id":"a","score":5,"blurb":"新架构"},{"id":"b","score":2,"blurb":"benchmark"}]', IDS)
    assert out["a"] == {"score": 5, "blurb": "新架构"}


def test_parse_fenced_json():
    text = '```json\n[{"id":"a","score":4,"blurb":"方法"}]\n```'
    assert parse_llm_response(text, IDS)["a"]["score"] == 4


def test_parse_truncated_json_returns_empty():
    assert parse_llm_response('[{"id":"a","score":5,"bl', IDS) == {}


def test_parse_ignores_unknown_ids_and_clamps_score():
    out = parse_llm_response('[{"id":"zzz","score":5,"blurb":"x"},{"id":"b","score":99,"blurb":"y"}]', IDS)
    assert "zzz" not in out and out["b"]["score"] == 5


def test_build_messages_truncates_summary_and_requires_json():
    item = Item(id="a", title="T", url="https://a.com", source="arxiv", kind="paper",
                summary="x" * 1000, published=NOW)
    messages = build_messages([item])
    assert "json" in messages[0]["content"].lower()
    assert len(messages[1]["content"]) < 1200


def test_score_items_swallows_http_errors():
    item = Item(id="a", title="T", url="https://a.com", source="arxiv", kind="paper",
                summary="s", published=NOW)

    class Boom:
        def post(self, *a, **k):
            raise RuntimeError("network down")

    assert score_items([item], CFG, "key", session=Boom()) == {}
