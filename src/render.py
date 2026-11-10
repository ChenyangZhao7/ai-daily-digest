from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import Item

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _entry(item: Item, score_info: dict | None) -> str:
    star = ""
    blurb = ""
    if score_info:
        if score_info.get("score") == 5:
            star = "⭐ "
        text = score_info.get("blurb") or ""
        if text:
            blurb = (
                '<div style="color:#444;font-size:13px;margin-top:3px;">'
                f"{_esc(text)}</div>"
            )
    meta = f'<span style="color:#888;font-size:12px;">{_esc(item.source)}</span>'
    if item.meta:
        meta += f'<span style="color:#888;font-size:12px;"> · {_esc(item.meta)}</span>'
    return (
        '<div class="item" style="margin:0 0 14px 0;">'
        '<div style="font-size:15px;font-weight:600;line-height:1.4;">'
        f'{star}<a href="{_esc(item.url)}" style="color:#1a5fb4;text-decoration:none;">'
        f"{_esc(item.title)}</a></div>"
        f'<div style="margin-top:3px;">{meta}</div>'
        f"{blurb}</div>"
    )


def render_email(
    items: list[Item],
    scores: dict[str, dict] | None,
    cfg: dict,
    now: datetime,
) -> tuple[str, str]:
    local = now.astimezone(SHANGHAI)
    date_label = local.strftime("%m-%d")
    papers = [i for i in items if i.kind == "paper"]
    news = [i for i in items if i.kind == "news"]

    subject = f"AI 日报 {date_label}｜论文 {len(papers)} 篇 · 资讯 {len(news)} 条"
    if scores is None:
        subject += "（未生成摘要）"

    papers_html = "".join(_entry(i, (scores or {}).get(i.id)) for i in papers)
    news_html = "".join(_entry(i, (scores or {}).get(i.id)) for i in news)
    empty = '<div style="color:#999;font-size:13px;margin-bottom:14px;">今日没有符合条件的条目</div>'

    sources = "、".join(sorted({i.source for i in items})) or "-"
    generated = local.strftime("%Y-%m-%d %H:%M")

    body = (
        '<html><body style="margin:0;padding:0;background:#f6f6f6;">'
        '<table width="600" cellpadding="0" cellspacing="0" border="0" '
        'style="width:600px;margin:0 auto;background:#ffffff;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;\">"
        '<tr><td style="padding:24px 24px 6px 24px;">'
        f'<div style="font-size:20px;font-weight:700;">AI 日报 · {date_label}</div>'
        "</td></tr>"
        '<tr><td style="padding:6px 24px 24px 24px;">'
        '<h3 style="font-size:15px;margin:18px 0 10px 0;color:#111;">论文</h3>'
        f"{papers_html or empty}"
        '<h3 style="font-size:15px;margin:18px 0 10px 0;color:#111;">资讯</h3>'
        f"{news_html or empty}"
        '<hr style="border:none;border-top:1px solid #eee;margin:20px 0 10px 0;">'
        '<div style="color:#888;font-size:12px;line-height:1.6;">'
        f"生成于 {generated}（北京时间）<br>来源：{_esc(sources)}</div>"
        "</td></tr></table></body></html>"
    )
    return subject, body
