from pathlib import Path

from src.sources import parse_rss

D = Path(__file__).parent / "fixtures"


def test_parse_rss_maps_news_items():
    items = parse_rss("qbitai", (D / "rss_qbitai.xml").read_text(encoding="utf-8"))
    assert len(items) == 2
    assert items[0].kind == "news" and items[0].source == "qbitai"
    assert items[0].published.tzinfo is not None


def test_parse_rss_filters_by_keywords():
    items = parse_rss("36kr", (D / "rss_36kr.xml").read_text(encoding="utf-8"), ["AI", "大模型"])
    assert [i.title for i in items] == ["大模型公司发布新架构"]


def test_parse_rss_skips_entries_without_date():
    xml = "<rss><channel><item><title>无日期</title><link>https://x.com/1</link></item></channel></rss>"
    assert parse_rss("x", xml) == []
