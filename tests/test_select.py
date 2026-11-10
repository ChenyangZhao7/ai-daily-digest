from datetime import datetime, timedelta, timezone

from src.models import Item, make_id
from src.select import dedupe, select_candidates

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)


def _item(title, url, *, kind="news", source="qbitai", hours_ago=1, summary=""):
    return Item(id=make_id(url), title=title, url=url, source=source, kind=kind,
                summary=summary, published=NOW - timedelta(hours=hours_ago))


def _cfg(**over):
    cfg = {
        "windows": {"paper_hours": 72, "news_hours": 24},
        "limits": {"max_candidates": 40},
        "sources": {
            "arxiv": {"enabled": True, "max_candidates": 20},
            "hf": {"enabled": True, "max_candidates": 10},
            "rss": [
                {"name": "qbitai", "enabled": True, "max_candidates": 5},
                {"name": "jiqizhixin", "enabled": True, "max_candidates": 5},
                {"name": "36kr", "enabled": True, "max_candidates": 5},
            ],
        },
    }
    cfg.update(over)
    return cfg


def test_dedupe_merges_same_url_with_tracking_params():
    a = _item("T", "https://a.com/x")
    b = _item("T", "https://a.com/x?utm_source=wechat")
    assert len(dedupe([a, b])) == 1


def test_dedupe_merges_near_identical_titles():
    a = _item("OpenAI releases GPT-6 model today", "https://a.com/1")
    b = _item("OpenAI releases GPT-6 model today!", "https://b.com/2")
    assert len(dedupe([a, b])) == 1


def test_news_older_than_24h_is_dropped():
    items = [_item("new", "https://a.com/1", hours_ago=1),
             _item("old", "https://a.com/2", hours_ago=30)]
    assert [i.title for i in select_candidates(items, _cfg(), NOW)] == ["new"]


def test_paper_window_is_72h_not_24h():
    items = [_item("fri", "https://a.com/3", kind="paper", source="arxiv", hours_ago=60)]
    assert len(select_candidates(items, _cfg(), NOW)) == 1


def test_each_source_respects_its_quota():
    items = [_item(f"q{i}", f"https://a.com/q{i}", hours_ago=1) for i in range(8)]
    assert len(select_candidates(items, _cfg(), NOW)) == 5


def test_total_candidates_capped_at_40():
    items = []
    items += [_item(f"a{i}", f"https://a.com/a{i}", kind="paper", source="arxiv", hours_ago=1) for i in range(30)]
    items += [_item(f"h{i}", f"https://a.com/h{i}", kind="paper", source="hf", hours_ago=1) for i in range(20)]
    items += [_item(f"q{i}", f"https://a.com/q{i}", hours_ago=1) for i in range(10)]
    items += [_item(f"j{i}", f"https://a.com/j{i}", source="jiqizhixin", hours_ago=1) for i in range(10)]
    items += [_item(f"k{i}", f"https://a.com/k{i}", source="36kr", hours_ago=1) for i in range(10)]
    # 每源名额 20+10+5+5+5 = 45，总体应截断到 40
    assert len(select_candidates(items, _cfg(), NOW)) == 40
