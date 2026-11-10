from __future__ import annotations

import json

import requests

from .models import Item

SYSTEM_PROMPT = """你是 AI 研究助理，为一个关注大模型与 Agent、偏好架构与系统的读者筛选每日内容。

对每个条目按以下标准打 1-5 分：
- 5 分：大模型 / Agent 方向，且涉及架构、训练或推理系统层面的实质贡献（新架构、高效注意力、长上下文、MoE、RL 训练方法、Agent 编排/记忆/工具使用框架、推理加速）。
- 4 分：同方向的方法类工作但增量较小；或非 LLM 方向的强系统类工作。
- 3 分：有技术含量但偏应用、偏实验分析、可迁移价值一般。
- 2 分：纯 benchmark、纯 survey、小改进、应用层调参。
- 1 分：与上述方向无关（推荐系统、传统 CV/NLP 应用、教育/医疗应用等）。

补充规则：
- 说明必须落到机制或结论上（例如"用稀疏注意力把长上下文成本降低一半"），禁止"提出了一种新方法""效果显著"这类空话。
- 说明不超过 40 个汉字。
- Agent / 推理系统 / 训练效率相关条目在分数相同时优先。

只输出 JSON 数组，不要任何解释或 Markdown。每个元素形如：
{"id": "<原样返回>", "score": <1-5 的整数>, "blurb": "<不超过 40 字的中文说明>"}
"""


def build_messages(items: list[Item]) -> list[dict]:
    payload = [
        {
            "id": item.id,
            "title": item.title,
            "source": item.source,
            "summary": item.summary[:300],
        }
        for item in items
    ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def parse_llm_response(text: str, valid_ids: set[str]) -> dict[str, dict]:
    cleaned = text.replace("```json", "").replace("```", "")
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, dict] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        if item_id not in valid_ids:
            continue
        try:
            score = int(entry["score"])
        except (KeyError, TypeError, ValueError):
            continue
        out[item_id] = {
            "score": max(1, min(5, score)),
            "blurb": str(entry.get("blurb") or "")[:40],
        }
    return out


def score_items(
    items: list[Item], cfg: dict, api_key: str, session=None
) -> dict[str, dict]:
    if not items:
        return {}
    client = session or requests.Session()
    llm = cfg["llm"]
    try:
        resp = client.post(
            f"{llm['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": llm["model"],
                "messages": build_messages(items),
                "temperature": 0.3,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"},
            },
            timeout=llm.get("timeout", 30),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return {}
    return parse_llm_response(content, {item.id for item in items})
