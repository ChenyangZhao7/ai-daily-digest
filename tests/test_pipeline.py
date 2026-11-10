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
