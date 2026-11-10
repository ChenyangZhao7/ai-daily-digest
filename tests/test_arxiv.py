from pathlib import Path

from src.sources import build_arxiv_url, parse_arxiv

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv.xml"


def test_parse_arxiv_normalizes_whitespace_and_entities():
    items = parse_arxiv(FIXTURE.read_text(encoding="utf-8"))
    first = items[0]
    assert "\n" not in first.title and "  " not in first.title
    assert "A & B" in first.summary
    assert "<3 layers" in first.summary
    assert first.kind == "paper" and first.source == "arxiv"


def test_parse_arxiv_keeps_primary_category_as_meta():
    items = parse_arxiv(FIXTURE.read_text(encoding="utf-8"))
    assert items[0].meta == "cs.LG"


def test_parse_arxiv_url_encodes_categories_and_window():
    url = build_arxiv_url(["cs.AI", "cs.LG"], since=None, until=None, max_results=20)
    assert "cat%3Acs.AI" in url or "cat:cs.AI" in url
    assert "max_results=20" in url
