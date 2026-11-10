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


def _score_of(scores: dict[str, dict], item: Item, fallback: int) -> int:
    return (scores.get(item.id) or {"score": fallback})["score"]


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

    primary = [i for i in group if _score_of(scores, i, relax_score) >= threshold]
    relaxed = [
        i for i in group if _score_of(scores, i, relax_score) == relax_score
    ]
    order = lambda i: (  # noqa: E731
        -_score_of(scores, i, relax_score),
        -i.published.timestamp(),
    )
    primary.sort(key=order)
    relaxed.sort(key=order)

    chosen = primary[:max_n]
    if len(chosen) < relax_min:
        chosen.extend(relaxed[: relax_min - len(chosen)])
        chosen.sort(key=order)
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
    for err in errors:
        print(f"[warn] source failed: {err}", file=sys.stderr)

    if send_fn is None:
        raise RuntimeError("send_fn is required")

    if not items:
        try:
            send_fn("[AI 日报] 今日抓取失败（全部来源）", _alert_html(errors))
        except Exception as exc:  # noqa: BLE001
            print(f"send failed: {exc}", file=sys.stderr)
            return 1
        return 0

    items = select_candidates(dedupe(items), cfg, now)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("[warn] DEEPSEEK_API_KEY is empty; sending without summaries", file=sys.stderr)
    scores = score_fn(items, cfg, api_key) or None
    print(
        f"[info] candidates={len(items)} scored={len(scores or {})} "
        f"source_errors={len(errors)}",
        file=sys.stderr,
    )

    selected = _pick(items, scores, "paper", cfg) + _pick(items, scores, "news", cfg)
    if not selected:
        print("[warn] nothing met the score bar; sending plain list", file=sys.stderr)
        scores = None
        limits = cfg["limits"]
        selected = sorted(items, key=lambda i: i.published, reverse=True)[
            : limits["max_papers"] + limits["max_news"]
        ]

    subject, body = render_email(selected, scores, cfg, now)
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
