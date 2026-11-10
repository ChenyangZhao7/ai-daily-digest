from __future__ import annotations

import html
import os
import sys
from datetime import datetime, timezone

from .config import load_config
from .mailer import send_email
from .models import Item
from .render import render_email
from .select import dedupe, select_candidates
from .sources import fetch_all
from .summarize import score_items


def _pick(
    items: list[Item],
    scores: dict[str, dict] | None,
    kind: str,
    cfg: dict,
) -> list[Item]:
    limits = cfg["limits"]
    max_n = limits["max_papers"] if kind == "paper" else limits["max_news"]
    threshold = limits["score_threshold"]
    relax_score = limits["relax_score"]
    relax_min = limits["relax_min"]

    group = [item for item in items if item.kind == kind]
    if scores is None:
        group.sort(key=lambda i: i.published, reverse=True)
        return group[:max_n]

    primary: list[Item] = []
    relaxed: list[Item] = []
    for item in group:
        info = scores.get(item.id) or {"score": relax_score, "blurb": ""}
        (primary if info["score"] >= threshold else relaxed).append(item)

    primary.sort(key=lambda i: i.published, reverse=True)
    relaxed.sort(key=lambda i: i.published, reverse=True)
    chosen = primary[:max_n]
    if len(chosen) < relax_min:
        chosen.extend(relaxed[: relax_min - len(chosen)])
    return chosen[:max_n]


def _alert_html(errors: list[str]) -> str:
    rows = "".join(f"<li>{html.escape(err)}</li>" for err in errors)
    return (
        "<html><body>"
        "<h2>今日抓取全部失败</h2>"
        "<p>所有数据源都没有返回可用内容，请检查 Actions 日志。</p>"
        f"<ul>{rows}</ul>"
        "</body></html>"
    )


def run(
    cfg: dict,
    now: datetime | None = None,
    *,
    fetch_fn=None,
    score_fn=None,
    send_fn=None,
) -> int:
    fetch_fn = fetch_fn or fetch_all
    score_fn = score_fn or score_items
    now = now or datetime.now(timezone.utc)

    items, errors = fetch_fn(cfg, now)
    if not items:
        if send_fn is None:
            raise RuntimeError("no items and no send_fn")
        send_fn("[AI 日报] 今日抓取失败（全部来源）", _alert_html(errors))
        return 0

    items = select_candidates(dedupe(items), cfg, now)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    scores = score_fn(items, cfg, api_key) or None

    selected = _pick(items, scores, "paper", cfg) + _pick(items, scores, "news", cfg)
    subject, body = render_email(selected, scores, cfg, now)

    if send_fn is None:
        raise RuntimeError("no send_fn")
    try:
        send_fn(subject, body)
    except Exception as exc:  # noqa: BLE001
        print(f"send failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    cfg = load_config()
    return run(cfg, send_fn=lambda subject, body: send_email(subject, body, cfg))


if __name__ == "__main__":
    sys.exit(main())
