from datetime import datetime, timedelta, timezone

from src.main import run
from src.models import Item, make_id

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)
CFG = {
    "limits": {"max_papers": 6, "max_news": 8, "max_candidates": 40,
               "score_threshold": 4, "relax_score": 3, "relax_min": 3},
    "windows": {"paper_hours": 72, "news_hours": 24},
    "sources": {
        "arxiv": {"enabled": True, "max_candidates": 20},
        "hf": {"enabled": True, "max_candidates": 10},
        "rss": [
            {"name": "qbitai", "enabled": True, "max_candidates": 5},
            {"name": "jiqizhixin", "enabled": True, "max_candidates": 5},
            {"name": "36kr", "enabled": True, "max_candidates": 5},
        ],
    },
    "email": {"to": "a@b.com", "from": "a@b.com"},
}


def _paper(i):
    url = f"https://a.com/{i}"
    return Item(id=make_id(url), title=f"p{i}", url=url, source="arxiv", kind="paper",
                summary="s", published=NOW - timedelta(hours=1))


def test_all_sources_failed_sends_alert_email():
    sent = []
    code = run(CFG, NOW,
               fetch_fn=lambda cfg, now: ([], ["arxiv: timeout", "hf: timeout"]),
               score_fn=lambda items, cfg, key: {},
               send_fn=lambda subject, html: sent.append(subject))
    assert code == 0 and len(sent) == 1 and "抓取失败" in sent[0]


def test_partial_source_failure_still_sends_digest():
    sent = []
    run(CFG, NOW,
        fetch_fn=lambda cfg, now: ([_paper(1)], ["hf: 502"]),
        score_fn=lambda items, cfg, key: {_paper(1).id: {"score": 5, "blurb": "x"}},
        send_fn=lambda subject, html: sent.append(subject))
    assert "论文 1 篇" in sent[0]


def test_llm_failure_falls_back_to_plain_list():
    sent = []
    run(CFG, NOW,
        fetch_fn=lambda cfg, now: ([_paper(1)], []),
        score_fn=lambda items, cfg, key: {},
        send_fn=lambda subject, html: sent.append(subject))
    assert "未生成摘要" in sent[0]


def test_selection_respects_max_limits():
    captured = {}
    def send(subject, html):
        captured["html"] = html
    run(CFG, NOW,
        fetch_fn=lambda cfg, now: ([_paper(i) for i in range(10)], []),
        score_fn=lambda items, cfg, key: {_paper(i).id: {"score": 5, "blurb": "x"} for i in range(10)},
        send_fn=send)
    assert captured["html"].count('class="item"') == 6


def _paper_at(i, hours_ago):
    url = f"https://a.com/{i}"
    return Item(id=make_id(url), title=f"p{i}", url=url, source="arxiv", kind="paper",
                summary="s", published=NOW - timedelta(hours=hours_ago))


def test_relaxation_adds_only_score_three():
    items = [_paper_at(0, 1), _paper_at(1, 2), _paper_at(2, 3), _paper_at(3, 0)]
    scores = {
        items[0].id: {"score": 5, "blurb": "x"},
        items[1].id: {"score": 4, "blurb": "x"},
        items[2].id: {"score": 3, "blurb": "x"},
        items[3].id: {"score": 1, "blurb": "x"},
    }
    captured = {}
    run(CFG, NOW, fetch_fn=lambda cfg, now: (items, []),
        score_fn=lambda i, c, k: scores, send_fn=lambda s, h: captured.setdefault("html", h))
    assert "p2" in captured["html"]
    assert "p3" not in captured["html"]


def test_primary_orders_by_score_then_recency():
    high_old = _paper_at(0, 10)
    low_new = _paper_at(1, 1)
    cfg = dict(CFG)
    cfg["limits"] = dict(CFG["limits"], max_papers=1)
    scores = {high_old.id: {"score": 5, "blurb": "x"}, low_new.id: {"score": 4, "blurb": "x"}}
    captured = {}
    run(cfg, NOW, fetch_fn=lambda c, now: ([high_old, low_new], []),
        score_fn=lambda i, c, k: scores, send_fn=lambda s, h: captured.setdefault("html", h))
    assert "p0" in captured["html"] and "p1" not in captured["html"]


def test_nothing_qualifies_falls_back_to_plain_list():
    items = [_paper_at(0, 1), _paper_at(1, 2)]
    scores = {i.id: {"score": 2, "blurb": "x"} for i in items}
    sent = []
    run(CFG, NOW, fetch_fn=lambda c, now: (items, []),
        score_fn=lambda i, c, k: scores, send_fn=lambda s, h: sent.append(s))
    assert "未生成摘要" in sent[0]


def test_partial_failure_is_logged_to_stderr(capsys):
    run(CFG, NOW, fetch_fn=lambda c, now: ([_paper(1)], ["hf: 502"]),
        score_fn=lambda i, c, k: {}, send_fn=lambda s, h: None)
    assert "hf: 502" in capsys.readouterr().err


def test_alert_send_failure_returns_one():
    def boom(subject, html):
        raise RuntimeError("smtp down")
    code = run(CFG, NOW, fetch_fn=lambda c, now: ([], ["arxiv: timeout"]),
               score_fn=lambda i, c, k: {}, send_fn=boom)
    assert code == 1
