from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass
class Item:
    id: str
    title: str
    url: str
    source: str
    kind: str
    summary: str
    published: datetime
    meta: str = ""


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(query),
            "",
        )
    )


def make_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:12]


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
