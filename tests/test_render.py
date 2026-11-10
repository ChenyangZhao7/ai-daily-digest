from datetime import datetime, timezone

from src.models import Item, make_id
from src.render import render_email

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)
CFG = {"email": {"to": "a@b.com"}}


def _paper(title="T", summary="S", **kw):
    url = kw.pop("url", "https://a.com/1")
    return Item(id=make_id(url), title=title, url=url, source="arxiv", kind="paper",
                summary=summary, published=NOW)


def test_escapes_script_tags_and_ampersands():
    _, html = render_email([_paper(title='<script>alert(1)</script> A&B')], None, CFG, NOW)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "A&amp;B" in html


def test_subject_contains_counts_and_date():
    subject, _ = render_email([_paper()], None, CFG, NOW)
    assert "11-10" in subject and "论文 1 篇" in subject and "资讯 0 条" in subject


def test_html_uses_table_layout_without_flex_or_grid():
    _, html = render_email([_paper()], None, CFG, NOW)
    assert "display:flex" not in html and "display:grid" not in html
    assert "width:600px" in html


def test_score_five_gets_star_and_blurb_is_shown():
    item = _paper()
    scores = {item.id: {"score": 5, "blurb": "用稀疏注意力降本"}}
    _, html = render_email([item], scores, CFG, NOW)
    assert "⭐" in html and "用稀疏注意力降本" in html


def test_fallback_without_scores_marks_plain_list():
    subject, html = render_email([_paper()], None, CFG, NOW)
    assert "未生成摘要" in subject
    assert ">T<" in html


def test_each_entry_carries_item_class():
    _, html = render_email([_paper(), _paper(url="https://a.com/2")], None, CFG, NOW)
    assert html.count('class="item"') == 2


def test_subject_uses_beijing_date_across_utc_midnight():
    # UTC 2026-11-09 17:00 == 北京 2026-11-10 01:00
    utc_before_midnight = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)
    subject, _ = render_email([_paper()], None, CFG, utc_before_midnight)
    assert "11-10" in subject
