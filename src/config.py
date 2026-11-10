from __future__ import annotations

import copy
import os
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "timezone": "Asia/Shanghai",
    "limits": {
        "max_papers": 6,
        "max_news": 8,
        "max_candidates": 40,
        "score_threshold": 4,
        "relax_score": 3,
        "relax_min": 3,
    },
    "windows": {"paper_hours": 72, "news_hours": 24},
    "sources": {
        "arxiv": {
            "enabled": True,
            "categories": ["cs.AI", "cs.LG", "cs.CL"],
            "max_candidates": 20,
        },
        "hf": {"enabled": True, "max_candidates": 10},
        "rss": [
            {
                "name": "qbitai",
                "url": "https://www.qbitai.com/feed",
                "enabled": True,
                "max_candidates": 5,
            },
            {
                "name": "jiqizhixin",
                "url": "https://www.jiqizhixin.com/rss",
                "enabled": True,
                "max_candidates": 5,
            },
            {
                "name": "36kr",
                "url": "https://www.36kr.com/feed",
                "enabled": True,
                "max_candidates": 5,
                "keywords": [
                    "AI",
                    "人工智能",
                    "大模型",
                    "LLM",
                    "Agent",
                    "智能体",
                    "算力",
                    "GPU",
                    "推理",
                    "训练",
                ],
            },
        ],
    },
    "llm": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "timeout": 30,
    },
    "email": {
        "to": "",
        "from": "",
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    cfg = _deep_merge(DEFAULTS, data)
    if os.environ.get("MAIL_TO"):
        cfg["email"]["to"] = os.environ["MAIL_TO"]
    if os.environ.get("MAIL_FROM"):
        cfg["email"]["from"] = os.environ["MAIL_FROM"]
    return cfg
