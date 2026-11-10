from datetime import datetime, timezone

from src.sources import fetch_all

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)


def test_fetch_all_collects_errors_for_each_source():
    cfg = {
        "sources": {
            "arxiv": {"enabled": True, "categories": ["cs.AI"], "max_candidates": 20},
            "hf": {"enabled": True, "max_candidates": 10},
            "rss": [{"name": "qbitai", "url": "https://q", "enabled": True, "max_candidates": 5}],
        }
    }

    def boom(url, timeout=10):
        raise RuntimeError("timeout")

    items, errors = fetch_all(cfg, NOW, text=boom, js=boom)
    assert items == []
    assert len(errors) == 3
    assert errors[0].startswith("arxiv: ")
