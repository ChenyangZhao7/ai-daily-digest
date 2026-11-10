from __future__ import annotations

import feedparser  # noqa: E402
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode

from .models import Item, make_id, to_utc

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def _text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    return (child.text or "") if child is not None else ""


def _clean(text: str) -> str:
    return " ".join(html.unescape(text or "").split())


def build_arxiv_url(
    categories: list[str],
    since: datetime | None,
    until: datetime | None,
    max_results: int,
) -> str:
    query = "(" + " OR ".join(f"cat:{c}" for c in categories) + ")"
    if since is not None and until is not None:
        fmt = "%Y%m%d%H%M"
        start = since.astimezone(timezone.utc).strftime(fmt)
        end = until.astimezone(timezone.utc).strftime(fmt)
        query += f" AND submittedDate:[{start} TO {end}]"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    return "https://export.arxiv.org/api/query?" + urlencode(params)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def parse_hf(payload: list[dict]) -> list[Item]:
    items: list[Item] = []
    for entry in payload:
        paper = entry.get("paper") or {}
        paper_id = str(paper.get("id") or "").strip()
        title = _clean(str(paper.get("title") or entry.get("title") or ""))
        if not paper_id or not title:
            continue
        published = _parse_iso(str(entry.get("publishedAt") or paper.get("publishedAt") or ""))
        if published is None:
            continue
        upvotes = paper.get("upvotes")
        url = f"https://huggingface.co/papers/{paper_id}"
        items.append(
            Item(
                id=make_id(url),
                title=title,
                url=url,
                source="hf",
                kind="paper",
                summary=_clean(str(paper.get("summary") or "")),
                published=published,
                meta=f"{upvotes if upvotes is not None else 0} upvotes",
            )
        )
    return items


def parse_arxiv(xml_text: str) -> list[Item]:
    root = ET.fromstring(xml_text)
    items: list[Item] = []
    for entry in root.findall(f"{ATOM}entry"):
        url = _text(entry, f"{ATOM}id").strip()
        if not url:
            continue
        published_raw = _text(entry, f"{ATOM}published").strip()
        try:
            published = to_utc(datetime.strptime(published_raw, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            continue
        primary = entry.find(f"{ARXIV}primary_category")
        if primary is not None and primary.get("term"):
            meta = primary.get("term") or ""
        else:
            category = entry.find(f"{ATOM}category")
            meta = (category.get("term") if category is not None else "") or ""
        items.append(
            Item(
                id=make_id(url),
                title=_clean(_text(entry, f"{ATOM}title")),
                url=url,
                source="arxiv",
                kind="paper",
                summary=_clean(_text(entry, f"{ATOM}summary")),
                published=published,
                meta=meta,
            )
        )
    return items


def parse_rss(
    name: str, xml_text: str, keywords: list[str] | None = None
) -> list[Item]:
    feed = feedparser.parse(xml_text)
    needles = [k.lower() for k in (keywords or [])]
    items: list[Item] = []
    for entry in feed.entries:
        title = _clean(str(entry.get("title") or ""))
        link = str(entry.get("link") or "").strip()
        if not title or not link:
            continue
        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if not struct:
            continue
        published = to_utc(datetime(*struct[:6], tzinfo=timezone.utc))
        summary = _clean(str(entry.get("summary") or entry.get("description") or ""))
        if needles:
            haystack = f"{title} {summary}".lower()
            if not any(needle in haystack for needle in needles):
                continue
        items.append(
            Item(
                id=make_id(link),
                title=title,
                url=link,
                source=name,
                kind="news",
                summary=summary,
                published=published,
            )
        )
    return items
