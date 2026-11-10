from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Item

SOURCE_PRIORITY = {"arxiv": 0, "hf": 1, "qbitai": 2, "jiqizhixin": 3, "36kr": 4}


def _norm_title(title: str) -> str:
    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def dedupe(items: list[Item]) -> list[Item]:
    kept: list[Item] = []
    for item in items:
        duplicate = None
        for existing in kept:
            if existing.kind != item.kind:
                continue
            if existing.id == item.id or SequenceMatcher(
                None, _norm_title(existing.title), _norm_title(item.title)
            ).ratio() > 0.9:
                duplicate = existing
                break
        if duplicate is None:
            kept.append(item)
        elif SOURCE_PRIORITY.get(item.source, 99) < SOURCE_PRIORITY.get(
            duplicate.source, 99
        ):
            kept[kept.index(duplicate)] = item
    return kept


def _quotas(cfg: dict) -> dict[str, int]:
    sources = cfg["sources"]
    quotas = {
        "arxiv": sources["arxiv"]["max_candidates"],
        "hf": sources["hf"]["max_candidates"],
    }
    for rss in sources["rss"]:
        quotas[rss["name"]] = rss["max_candidates"]
    return quotas


def select_candidates(items: list[Item], cfg: dict, now) -> list[Item]:
    windows = cfg["windows"]
    quotas = _quotas(cfg)
    grouped: dict[str, list[Item]] = {}
    for item in items:
        hours = windows["paper_hours"] if item.kind == "paper" else windows["news_hours"]
        age_seconds = (now - item.published).total_seconds()
        if age_seconds < 0 or age_seconds > hours * 3600:
            continue
        grouped.setdefault(item.source, []).append(item)

    chosen: list[Item] = []
    for source, group in grouped.items():
        group.sort(key=lambda i: i.published, reverse=True)
        chosen.extend(group[: quotas.get(source, 0)])

    chosen.sort(key=lambda i: i.published, reverse=True)
    return chosen[: cfg["limits"]["max_candidates"]]
