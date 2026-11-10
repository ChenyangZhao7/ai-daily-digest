# AI 日报邮件 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天北京时间 08:30 由 GitHub Actions 抓取 AI 论文与资讯，用 DeepSeek 打分并生成一句中文说明，渲染成 HTML 邮件发到 `your-email@example.com`。

**Architecture:** 一个 Python 包 `src/`，流水线为 `fetch_all → dedupe → select_candidates → score_items → render_email → send_email`。抓取失败按源降级，LLM 失败降级为纯清单，全部源失败发告警邮件。调度与密钥都在 GitHub 侧。

**Tech Stack:** Python 3.12、requests、feedparser、PyYAML、pytest；GitHub Actions（cron + workflow_dispatch）；DeepSeek Chat Completions API；QQ SMTP over SSL。

**Spec:** `docs/superpowers/specs/2026-11-10-ai-daily-digest-design.md`

## Global Constraints

- Python 版本：3.12（Actions 与本地一致）。
- 运行时依赖仅 `requests`、`feedparser`、`PyYAML`；测试依赖 `pytest`。不引入其他框架。
- 所有外部 HTTP 调用：超时 10 秒，失败重试 1 次。
- LLM 调用超时 30 秒；模型固定 `deepseek-chat`；端点 `https://api.deepseek.com/chat/completions`。
- 密钥只从环境变量读取：`DEEPSEEK_API_KEY`、`QQ_SMTP_AUTH_CODE`；禁止打印到日志或写入任何文件。
- 时间：存储统一 UTC（tz-aware），展示与"今天"判定统一 `Asia/Shanghai`。
- 窗口：论文 72 小时，资讯 24 小时。
- 名额：arXiv 20、HF 10、量子位 5、机器之心 5、36氪 5；候选池上限 40。
- 条数：论文 ≤ 6，资讯 ≤ 8。
- 打分：只收 score ≥ 4；若 ≥ 4 分的不足 3 条，放宽到 score 3，最多补到 3 条。
- 邮件 HTML：宽度 600px，`table` 布局，禁止 `flex` / `grid`；所有抓取内容先转义。
- `MAIL_FROM` 必须等于 SMTP 认证账号（`your-email@example.com`）。
- cron：`30 0 * * *`（UTC）= 北京时间 08:30。
- 提交信息用 `feat:` / `test:` / `chore:` 前缀，每个任务一次提交。

## Review Focus

- **arXiv 的 `<summary>` 含换行、双空格和 HTML 实体**（`&amp;`、`&lt;`）：用户期望邮件里读到的是一段干净的中文/英文摘要，不是带 `<p>` 或断行的原文。
- **抓取内容里的 `<script>`、引号、`&`**：用户期望邮件正常显示这些字符本身，而不是把邮件版面弄坏或被邮箱客户端拦截。
- **LLM 返回被 ```json 包裹、被截断、或条目缺字段**：用户期望这种情况下仍然收到今天的邮件，而不是收到 GitHub Actions 的失败通知。
- **某个源超时或返回 502**：用户期望其余来源照常成信，而不是整封邮件消失。
- **运行时刻是 UTC 00:30，跨日边界**：用户期望看到的日期和 24h/72h 窗口按北京时间计算，不出现"昨天的新闻"或"日期差一天"。

---

### Task 1: 项目骨架、配置与 Item 模型

**Files:**
- Create: `.gitignore`, `requirements.txt`, `config.yaml`
- Create: `src/__init__.py`, `src/models.py`, `src/config.py`
- Test: `tests/test_models.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `src.models.Item`：`@dataclass`，字段 `id: str, title: str, url: str, source: str, kind: str, summary: str, published: datetime, meta: str = ""`
  - `src.models.normalize_url(url: str) -> str`
  - `src.models.make_id(url: str) -> str`（`sha1(normalize_url(url))[:12]`）
  - `src.models.to_utc(dt: datetime) -> datetime`
  - `src.config.load_config(path: str = "config.yaml") -> dict`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_models.py
from src.models import normalize_url, make_id


def test_normalize_url_strips_tracking_and_fragment():
    assert normalize_url("https://Example.com/a/?utm_source=x&id=7#frag") == "https://example.com/a?id=7"


def test_normalize_url_drops_trailing_slash():
    assert normalize_url("https://a.com/x/") == "https://a.com/x"


def test_make_id_is_stable_across_url_variants():
    assert make_id("https://a.com/x/?utm_medium=y") == make_id("https://a.com/x")
```

```python
# tests/test_config.py
from src.config import load_config


def test_load_config_reads_yaml_and_applies_env_overrides(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text("limits:\n  max_papers: 6\n", encoding="utf-8")
    monkeypatch.setenv("MAIL_TO", "someone@example.com")
    cfg = load_config(str(p))
    assert cfg["limits"]["max_papers"] == 6
    assert cfg["email"]["to"] == "someone@example.com"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_models.py tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src'`）

- [ ] **Step 3: 实现**

`git init` 后创建 `.gitignore`（`.env`、`*.local.yaml`、`__pycache__/`、`.pytest_cache/`、`tests/fixtures/raw/`）、`requirements.txt`（`requests`、`feedparser`、`PyYAML`、`pytest`）。

`src/models.py`：`normalize_url` 小写化 scheme/host、去掉 fragment、去除 `utm_*` 查询参数、去掉末尾 `/`；`make_id` 用 `hashlib.sha1`；`to_utc` 对 naive 时间按 UTC 处理。

`src/config.py`：`load_config` = 内置默认值 ← yaml 深合并 ← 环境变量覆盖 `email.to` / `email.from`（`MAIL_TO` / `MAIL_FROM`）。默认值包含 Global Constraints 里的所有数值，`email.to` 默认 `your-email@example.com`。

`config.yaml` 写出来（不含任何密钥）：

```yaml
timezone: Asia/Shanghai
limits:
  max_papers: 6
  max_news: 8
  max_candidates: 40
  score_threshold: 4
  relax_score: 3
  relax_min: 3
windows:
  paper_hours: 72
  news_hours: 24
sources:
  arxiv:
    enabled: true
    categories: [cs.AI, cs.LG, cs.CL]
    max_candidates: 20
  hf:
    enabled: true
    max_candidates: 10
  rss:
    - {name: qbitai, url: "https://www.qbitai.com/feed", enabled: true, max_candidates: 5}
    - {name: jiqizhixin, url: "https://www.jiqizhixin.com/rss", enabled: true, max_candidates: 5}
    - {name: 36kr, url: "https://www.36kr.com/feed", enabled: true, max_candidates: 5,
       keywords: [AI, 人工智能, 大模型, LLM, Agent, 智能体, 算力, GPU, 推理, 训练]}
llm:
  base_url: "https://api.deepseek.com"
  model: deepseek-chat
  timeout: 30
email:
  to: "your-email@example.com"
  from: "your-email@example.com"
  smtp_host: smtp.qq.com
  smtp_port: 465
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_models.py tests/test_config.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add .gitignore requirements.txt config.yaml src tests
git commit -m "chore: scaffold project, config loader, and Item model"
```

---

### Task 2: arXiv 解析

**Files:**
- Create: `src/sources.py`, `tests/fixtures/arxiv.xml`
- Test: `tests/test_arxiv.py`

**Interfaces:**
- Consumes: `Item`, `make_id`, `to_utc`
- Produces:
  - `src.sources.build_arxiv_url(categories: list[str], since: datetime | None, until: datetime | None, max_results: int) -> str`
  - `src.sources.parse_arxiv(xml_text: str) -> list[Item]`

- [ ] **Step 1: 写失败的测试**

fixture `tests/fixtures/arxiv.xml` 含 2 个 `entry`，其中一个标题带换行、摘要为 `We study A &amp; B, with &lt;3 layers.`、两个 `<category>`（第一个是 `cs.LG`），并带 `<published>2026-11-09T17:03:00Z</published>`。

```python
# tests/test_arxiv.py
from pathlib import Path

from src.sources import build_arxiv_url, parse_arxiv

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv.xml"


def test_parse_arxiv_normalizes_whitespace_and_entities():
    items = parse_arxiv(FIXTURE.read_text(encoding="utf-8"))
    first = items[0]
    assert "\n" not in first.title and "  " not in first.title
    assert "A & B" in first.summary
    assert "<3 layers" in first.summary
    assert first.kind == "paper" and first.source == "arxiv"


def test_parse_arxiv_keeps_primary_category_as_meta():
    items = parse_arxiv(FIXTURE.read_text(encoding="utf-8"))
    assert items[0].meta == "cs.LG"


def test_parse_arxiv_url_encodes_categories_and_window():
    url = build_arxiv_url(["cs.AI", "cs.LG"], since=None, until=None, max_results=20)
    assert "cat%3Acs.AI" in url or "cat:cs.AI" in url
    assert "max_results=20" in url
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_arxiv.py -v`
Expected: FAIL（`ImportError: cannot import name 'build_arxiv_url'`）

- [ ] **Step 3: 实现**

`parse_arxiv` 用 `xml.etree.ElementTree`，命名空间 `{http://www.w3.org/2005/Atom}`；标题/摘要用 `" ".join(text.split())` 归一化空白，并用 `html.unescape` 还原实体；`meta` 取第一个 `<arxiv:primary_category term>`，没有则取第一个 `category`；`published` 用 `to_utc` 解析 `%Y-%m-%dT%H:%M:%SZ`；`url` 取 `<id>`。

`build_arxiv_url` 拼接 `search_query=(cat:A OR cat:B) AND submittedDate:[YYYYMMDDHHMM TO YYYYMMDDHHMM]`（UTC），并带 `sortBy=submittedDate&sortOrder=descending&max_results=N`；`since`/`until` 为 `None` 时省略日期条件。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_arxiv.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/sources.py tests/fixtures/arxiv.xml tests/test_arxiv.py
git commit -m "feat: parse arXiv Atom feed"
```

---

### Task 3: HuggingFace Daily Papers 解析

**Files:**
- Modify: `src/sources.py`
- Create: `tests/fixtures/hf.json`
- Test: `tests/test_hf.py`

**Interfaces:**
- Consumes: `Item`, `make_id`, `to_utc`
- Produces: `src.sources.parse_hf(payload: list[dict]) -> list[Item]`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_hf.py
import json
from pathlib import Path

from src.sources import parse_hf

FIXTURE = Path(__file__).parent / "fixtures" / "hf.json"


def test_parse_hf_maps_fields():
    items = parse_hf(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert items[0].source == "hf" and items[0].kind == "paper"
    assert items[0].url == "https://huggingface.co/papers/2511.00001"
    assert items[0].meta == "120 upvotes"


def test_parse_hf_skips_entries_without_paper_id():
    payload = [{"title": "no paper", "paper": {}}]
    assert parse_hf(payload) == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_hf.py -v`
Expected: FAIL（`ImportError: cannot import name 'parse_hf'`）

- [ ] **Step 3: 实现**

`parse_hf` 遍历 payload，取 `entry["paper"]["id"]`、`entry["paper"]["title"]`、`entry["paper"]["summary"]`、`entry["paper"]["upvotes"]`、`entry.get("publishedAt")` 或 `entry["paper"].get("publishedAt")`；缺 id 或标题则跳过；`url = f"https://huggingface.co/papers/{paper_id}"`；`meta = f"{upvotes} upvotes"`（upvotes 缺失写 `"0 upvotes"`）。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_hf.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add src/sources.py tests/fixtures/hf.json tests/test_hf.py
git commit -m "feat: parse HuggingFace daily papers"
```

---

### Task 4: RSS 解析与 36氪 关键词过滤

**Files:**
- Modify: `src/sources.py`
- Create: `tests/fixtures/rss_qbitai.xml`, `tests/fixtures/rss_36kr.xml`
- Test: `tests/test_rss.py`

**Interfaces:**
- Consumes: `Item`, `make_id`, `to_utc`
- Produces: `src.sources.parse_rss(name: str, xml_text: str, keywords: list[str] | None = None) -> list[Item]`

- [ ] **Step 1: 写失败的测试**

fixture 中 `qbitai` 含 2 条带 `pubDate` 的条目；`36kr` 含 2 条，其中一条标题不含任何 AI 关键词。

```python
# tests/test_rss.py
from pathlib import Path

from src.sources import parse_rss

D = Path(__file__).parent / "fixtures"


def test_parse_rss_maps_news_items():
    items = parse_rss("qbitai", (D / "rss_qbitai.xml").read_text(encoding="utf-8"))
    assert len(items) == 2
    assert items[0].kind == "news" and items[0].source == "qbitai"
    assert items[0].published.tzinfo is not None


def test_parse_rss_filters_by_keywords():
    items = parse_rss("36kr", (D / "rss_36kr.xml").read_text(encoding="utf-8"), ["AI", "大模型"])
    assert [i.title for i in items] == ["大模型公司发布新架构"]


def test_parse_rss_skips_entries_without_date():
    xml = "<rss><channel><item><title>无日期</title><link>https://x.com/1</link></item></channel></rss>"
    assert parse_rss("x", xml) == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_rss.py -v`
Expected: FAIL（`ImportError: cannot import name 'parse_rss'`）

- [ ] **Step 3: 实现**

用 `feedparser.parse(xml_text)`；标题/摘要做 `" ".join(text.split())` 归一化并 `html.unescape`；优先 `entry.published_parsed`，退化到 `updated_parsed`，都没有则跳过；`kind="news"`、`source=name`、`summary` 取 `entry.summary` 或 `entry.description` 或空串；`keywords` 非空时，标题+摘要小写后需包含任一关键词（关键词也小写）。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_rss.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/sources.py tests/fixtures tests/test_rss.py
git commit -m "feat: parse RSS feeds with keyword filtering"
```

---

### Task 5: 抓取编排、去重与候选池筛选

**Files:**
- Modify: `src/sources.py`
- Create: `src/select.py`, `tests/test_select.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `parse_arxiv`, `parse_hf`, `parse_rss`, `build_arxiv_url`, `Item`
- Produces:
  - `src.sources.fetch_text(url: str, timeout: int = 10) -> str`（`requests.get`，1 次重试，失败抛 `RuntimeError`）
  - `src.sources.fetch_json(url: str, timeout: int = 10) -> list`
  - `src.sources.fetch_all(cfg: dict, now: datetime, *, text=None, js=None) -> tuple[list[Item], list[str]]`（返回条目与错误列表；`text`/`js` 可注入用于测试）
  - `src.select.dedupe(items: list[Item]) -> list[Item]`
  - `src.select.select_candidates(items: list[Item], cfg: dict, now: datetime) -> list[Item]`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_select.py
from datetime import datetime, timedelta, timezone

from src.models import Item, make_id
from src.select import dedupe, select_candidates

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)


def _item(title, url, *, kind="news", source="qbitai", hours_ago=1, summary=""):
    return Item(id=make_id(url), title=title, url=url, source=source, kind=kind,
                summary=summary, published=NOW - timedelta(hours=hours_ago))


def _cfg(**over):
    cfg = {
        "windows": {"paper_hours": 72, "news_hours": 24},
        "limits": {"max_candidates": 40},
        "sources": {
            "arxiv": {"enabled": True, "max_candidates": 20},
            "hf": {"enabled": True, "max_candidates": 10},
            "rss": [
                {"name": "qbitai", "enabled": True, "max_candidates": 5},
                {"name": "jiqizhixin", "enabled": True, "max_candidates": 5},
                {"name": "36kr", "enabled": True, "max_candidates": 5},
            ],
        },
    }
    cfg.update(over)
    return cfg


def test_dedupe_merges_same_url_with_tracking_params():
    a = _item("T", "https://a.com/x")
    b = _item("T", "https://a.com/x?utm_source=wechat")
    assert len(dedupe([a, b])) == 1


def test_dedupe_merges_near_identical_titles():
    a = _item("OpenAI releases GPT-6 model today", "https://a.com/1")
    b = _item("OpenAI releases GPT-6 model today!", "https://b.com/2")
    assert len(dedupe([a, b])) == 1


def test_news_older_than_24h_is_dropped():
    items = [_item("new", "https://a.com/1", hours_ago=1),
             _item("old", "https://a.com/2", hours_ago=30)]
    assert [i.title for i in select_candidates(items, _cfg(), NOW)] == ["new"]


def test_paper_window_is_72h_not_24h():
    items = [_item("fri", "https://a.com/3", kind="paper", source="arxiv", hours_ago=60)]
    assert len(select_candidates(items, _cfg(), NOW)) == 1


def test_each_source_respects_its_quota():
    items = [_item(f"q{i}", f"https://a.com/q{i}", hours_ago=1) for i in range(8)]
    assert len(select_candidates(items, _cfg(), NOW)) == 5


def test_total_candidates_capped_at_40():
    items = []
    items += [_item(f"a{i}", f"https://a.com/a{i}", kind="paper", source="arxiv", hours_ago=1) for i in range(30)]
    items += [_item(f"h{i}", f"https://a.com/h{i}", kind="paper", source="hf", hours_ago=1) for i in range(20)]
    items += [_item(f"q{i}", f"https://a.com/q{i}", hours_ago=1) for i in range(10)]
    items += [_item(f"j{i}", f"https://a.com/j{i}", source="jiqizhixin", hours_ago=1) for i in range(10)]
    items += [_item(f"k{i}", f"https://a.com/k{i}", source="36kr", hours_ago=1) for i in range(10)]
    # 每源名额 20+10+5+5+5 = 45，总体应截断到 40
    assert len(select_candidates(items, _cfg(), NOW)) == 40
```

```python
# tests/test_fetch.py
from datetime import datetime, timezone

from src.sources import fetch_all

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)


def test_fetch_all_collects_errors_for_each_source():
    cfg = {
        "sources": {
            "arxiv": {"enabled": True, "categories": ["cs.AI"], "max_candidates": 20},
            "hf": {"enabled": True, "max_candidates": 10},
            "rss": [{"name": "qbitai", "url": "https://q", "enabled": True, "max_candidates": 5}],
        }
    }

    def boom(url, timeout=10):
        raise RuntimeError("timeout")

    items, errors = fetch_all(cfg, NOW, text=boom, js=boom)
    assert items == []
    assert len(errors) == 3
    assert errors[0].startswith("arxiv: ")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_select.py tests/test_fetch.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.select'`）

- [ ] **Step 3: 实现**

`dedupe`：按 `id` 去重，保留先出现者；再对同 `kind` 的条目做标题归一化（小写、去标点）后用 `difflib.SequenceMatcher(None, a, b).ratio() > 0.9` 合并，保留来源优先级 `arxiv > hf > qbitai > jiqizhixin > 36kr` 更高者。

`select_candidates`：先按 `kind` 过滤时间窗（论文 72h、资讯 24h，基于 `now`），再按 `source` 分组、组内按 `published` 降序截断到该源 `max_candidates`，最后按 `published` 降序整体截断到 `limits.max_candidates`。

`fetch_text`/`fetch_json`：`requests.get(url, timeout=timeout, headers={"User-Agent": "ai-daily-digest/1.0"})`，非 2xx 或异常时 sleep 1 秒重试一次，仍失败抛 `RuntimeError`。

`fetch_all`：对启用的源逐个调用（arXiv 的 URL 用 `build_arxiv_url(categories, since=now-72h, until=now, max_results=config 值*3)`），捕获异常写入 `errors`（格式 `f"{name}: {exc}"`），继续下一个源。arXiv 的 `max_results` 取 `max_candidates * 3` 以保证有时间窗过滤后的余量，但本地截断仍用 20。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_select.py tests/test_fetch.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add src/sources.py src/select.py tests
git commit -m "feat: dedupe and select candidates with quotas and windows"
```

---

### Task 6: DeepSeek 打分与 JSON 容错

**Files:**
- Create: `src/summarize.py`
- Test: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `Item`
- Produces:
  - `src.summarize.build_messages(items: list[Item]) -> list[dict]`
  - `src.summarize.parse_llm_response(text: str, valid_ids: set[str]) -> dict[str, dict]`（值形如 `{"score": int, "blurb": str}`）
  - `src.summarize.score_items(items: list[Item], cfg: dict, api_key: str, session=None) -> dict[str, dict]`（任何失败返回 `{}`；`session` 仅测试注入）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_summarize.py
from datetime import datetime, timezone

import pytest

from src.models import Item, make_id
from src.summarize import build_messages, parse_llm_response, score_items

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
CFG = {"llm": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat", "timeout": 30}}

IDS = {"a", "b"}


def test_parse_plain_json():
    out = parse_llm_response('[{"id":"a","score":5,"blurb":"新架构"},{"id":"b","score":2,"blurb":"benchmark"}]', IDS)
    assert out["a"] == {"score": 5, "blurb": "新架构"}


def test_parse_fenced_json():
    text = '```json\n[{"id":"a","score":4,"blurb":"方法"}]\n```'
    assert parse_llm_response(text, IDS)["a"]["score"] == 4


def test_parse_truncated_json_returns_empty():
    assert parse_llm_response('[{"id":"a","score":5,"bl', IDS) == {}


def test_parse_ignores_unknown_ids_and_clamps_score():
    out = parse_llm_response('[{"id":"zzz","score":5,"blurb":"x"},{"id":"b","score":99,"blurb":"y"}]', IDS)
    assert "zzz" not in out and out["b"]["score"] == 5


def test_build_messages_truncates_summary_and_requires_json():
    item = Item(id="a", title="T", url="https://a.com", source="arxiv", kind="paper",
                summary="x" * 1000, published=NOW)
    messages = build_messages([item])
    assert "json" in messages[0]["content"].lower()
    assert len(messages[1]["content"]) < 1200


def test_score_items_swallows_http_errors(monkeypatch):
    class Boom:
        def post(self, *a, **k):
            raise RuntimeError("network down")

    assert score_items([], CFG, "key", session=Boom()) == {}
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_summarize.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.summarize'`）

- [ ] **Step 3: 实现**

`build_messages` 的 system 内容写入设计文档 5.3 的打分表原文（5 分定义、补充规则、禁止空话），并要求"只输出 JSON 数组，每条含 id/score/blurb"。user 内容为 `json.dumps` 的条目数组，每条的 `summary` 先截断到 300 字。

`parse_llm_response`：去掉 ``` 围栏，取第一个 `[` 到最后一个 `]`；`json.loads` 失败返回 `{}`；逐条校验 `id in valid_ids`、`score` 转 int 后 clamp 到 1–5、`blurb` 转 str 并截断 40 字；缺 id/score 的条目跳过。

`score_items(items, cfg, api_key, session=None)`：`items` 为空返回 `{}`；`session` 默认 `requests.Session()`；POST `{base_url}/chat/completions`，body 含 `model`、`messages`、`temperature=0.3`、`response_format={"type": "json_object"}`、`max_tokens=2000`；任何异常返回 `{}`，不抛出。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_summarize.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add src/summarize.py tests/test_summarize.py
git commit -m "feat: score items with DeepSeek and tolerate bad JSON"
```

---

### Task 7: HTML 邮件渲染

**Files:**
- Create: `src/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Item`, scores dict
- Produces: `src.render.render_email(items: list[Item], scores: dict[str, dict] | None, cfg: dict, now: datetime) -> tuple[str, str]`（返回 `(subject, html)`）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_render.py
from datetime import datetime, timezone

from src.models import Item, make_id
from src.render import render_email

NOW = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)
CFG = {"email": {"to": "a@b.com"}}


def _paper(title="T", summary="S", **kw):
    url = kw.pop("url", "https://a.com/1")
    return Item(id=make_id(url), title=title, url=url, source="arxiv", kind="paper",
                summary=summary, published=NOW)


def test_escapes_script_tags_and_ampersands():
    _, html = render_email([_paper(title='<script>alert(1)</script> A&B')], None, CFG, NOW)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "A&amp;B" in html


def test_subject_contains_counts_and_date():
    subject, _ = render_email([_paper()], None, CFG, NOW)
    assert "11-10" in subject and "论文 1 篇" in subject and "资讯 0 条" in subject


def test_html_uses_table_layout_without_flex_or_grid():
    _, html = render_email([_paper()], None, CFG, NOW)
    assert "display:flex" not in html and "display:grid" not in html
    assert "width:600px" in html


def test_score_five_gets_star_and_blurb_is_shown():
    item = _paper()
    scores = {item.id: {"score": 5, "blurb": "用稀疏注意力降本"}}
    _, html = render_email([item], scores, CFG, NOW)
    assert "⭐" in html and "用稀疏注意力降本" in html


def test_fallback_without_scores_marks_plain_list():
    subject, html = render_email([_paper()], None, CFG, NOW)
    assert "未生成摘要" in subject
    assert ">T<" in html


def test_each_entry_carries_item_class():
    _, html = render_email([_paper(), _paper(url="https://a.com/2")], None, CFG, NOW)
    assert html.count('class="item"') == 2


def test_subject_uses_beijing_date_across_utc_midnight():
    # UTC 2026-11-09 17:00 == 北京 2026-11-10 01:00
    utc_before_midnight = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)
    subject, _ = render_email([_paper()], None, CFG, utc_before_midnight)
    assert "11-10" in subject
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.render'`）

- [ ] **Step 3: 实现**

纯字符串模板，`html.escape(..., quote=True)` 处理标题、摘要、blurb。日期用 `ZoneInfo("Asia/Shanghai")` 转本地后格式化为 `MM-DD`。主题：`AI 日报 11-10｜论文 N 篇 · 资讯 M 条`，无 scores 时追加 `（未生成摘要）`。正文：外框 `<table width="600">`，论文区、资讯区各一个 `<h3>` + 逐条 `<div class="item">`，每条含标题链接、`meta`、blurb、score 5 时前置 ⭐。页脚写生成时间与各来源名。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_render.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add src/render.py tests/test_render.py
git commit -m "feat: render 600px table-based HTML email"
```

---

### Task 8: SMTP 发送

**Files:**
- Create: `src/mailer.py`
- Test: `tests/test_mailer.py`

**Interfaces:**
- Consumes: `cfg`、环境变量 `QQ_SMTP_AUTH_CODE`
- Produces: `src.mailer.send_email(subject: str, html: str, cfg: dict, password: str | None = None) -> None`（失败抛异常）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_mailer.py
import smtplib

import pytest

from src.mailer import send_email

CFG = {"email": {"to": "your-email@example.com", "from": "your-email@example.com",
                 "smtp_host": "smtp.qq.com", "smtp_port": 465}}


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.logged_in = None
        self.sent = None
        FakeSMTP.instances.append(self)

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_send_email_uses_ssl_qq_and_same_from_to(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    send_email("主题", "<p>hi</p>", CFG, "authcode")
    s = FakeSMTP.instances[0]
    assert (s.host, s.port) == ("smtp.qq.com", 465)
    assert s.logged_in == ("your-email@example.com", "authcode")
    assert s.sent["From"] == "your-email@example.com"
    assert s.sent["To"] == "your-email@example.com"


def test_send_email_raises_when_login_fails(monkeypatch):
    class Bad(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad auth")

    monkeypatch.setattr(smtplib, "SMTP_SSL", Bad)
    with pytest.raises(smtplib.SMTPAuthenticationError):
        send_email("s", "<p>x</p>", CFG, "wrong")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_mailer.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.mailer'`）

- [ ] **Step 3: 实现**

`send_email` 读 `password or os.environ["QQ_SMTP_AUTH_CODE"]`（缺失抛 `RuntimeError`），组装 `EmailMessage`（`Subject` 用 `Header(subject, "utf-8")`，`From`/`To` 取自 cfg），`set_content(html, subtype="html")`，`with smtplib.SMTP_SSL(host, port, timeout=20) as s: s.login(user, password); s.send_message(msg)`。异常不吞。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_mailer.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add src/mailer.py tests/test_mailer.py
git commit -m "feat: send HTML email over QQ SMTP SSL"
```

---

### Task 9: 流水线串联与降级

**Files:**
- Create: `src/main.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `load_config`、`fetch_all`、`dedupe`、`select_candidates`、`score_items`、`render_email`、`send_email`
- Produces:
  - `src.main.run(cfg: dict, now: datetime | None = None, *, fetch_fn=None, score_fn=None, send_fn=None) -> int`
  - `src.main.main() -> int`（读环境变量、调用 `run`、返回退出码）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_pipeline.py
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.main'`）

- [ ] **Step 3: 实现**

`run` 顺序：
1. `items, errors = fetch_fn(cfg, now)`。
2. 若 `items` 为空：构造告警邮件（主题 `[AI 日报] 今日抓取全部失败`，正文列出 `errors`），`send_fn` 发送，返回 0。
3. `dedupe → select_candidates`。
4. `scores = score_fn(items, cfg, key)`；`key` 在 `run` 内从 `os.environ.get("DEEPSEEK_API_KEY", "")` 取，测试可通过不传 `score_fn` 走真实实现，但默认注入的函数签名是 `(items, cfg, key)`。`scores` 为空 → `scores_for_render = None`。
5. 选条：论文取 `kind=="paper"` 且 `score >= threshold`，最多 `max_papers`；不足 `relax_min` 时用 `score == relax_score` 的补齐到 `relax_min`；资讯同理（阈值同样适用）。`scores` 中缺失的条目按 `score=3, blurb=""` 处理（只可能出现在放宽阶段，不会挤掉高分条目）。`scores is None` 时按 `published` 降序直接截断。
6. `subject, html = render_email(selected, scores, cfg, now)`；`send_fn(subject, html)`。
7. 返回 0；`send_fn` 抛异常时返回 1。

`main()`：`load_config()`、`run(cfg, send_fn=lambda s, h: send_email(s, h, cfg))`、`sys.exit(code)`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 全量测试 + 提交**

Run: `python -m pytest -q`
Expected: PASS（全部）

```bash
git add src/main.py tests/test_pipeline.py
git commit -m "feat: wire pipeline with degradation paths"
```

---

### Task 10: GitHub Actions、README 与部署文件

**Files:**
- Create: `.github/workflows/daily.yml`, `.github/workflows/snapshot.yml`, `.github/workflows/keepalive.yml`
- Create: `README.md`
- Test: `tests/test_workflows.py`

**Interfaces:**
- Consumes: `python -m src.main`
- Produces: 可手动触发与每日定时运行的 workflow

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_workflows.py
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def _on(wf):
    # PyYAML 1.1 会把裸 on: 解析成 True
    return wf.get("on", wf.get(True))


def test_daily_cron_is_0830_beijing():
    cron = _on(_load("daily.yml"))["schedule"][0]["cron"]
    assert cron == "30 0 * * *"
    utc_run = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)
    assert utc_run.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%H:%M") == "08:30"


def test_daily_passes_secrets_as_env():
    steps = _load("daily.yml")["jobs"]["send"]["steps"]
    env = [s["env"] for s in steps if "env" in s][-1]
    assert env["DEEPSEEK_API_KEY"].endswith("secrets.DEEPSEEK_API_KEY }}")
    assert env["QQ_SMTP_AUTH_CODE"].endswith("secrets.QQ_SMTP_AUTH_CODE }}")


def test_keepalive_has_write_permission_and_monthly_cron():
    wf = _load("keepalive.yml")
    assert wf["permissions"]["contents"] == "write"
    assert _on(wf)["schedule"][0]["cron"] == "0 0 1 * *"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_workflows.py -v`
Expected: FAIL（`FileNotFoundError`）

- [ ] **Step 3: 实现**

`daily.yml`：`on: {schedule: [{cron: "30 0 * * *"}], workflow_dispatch: {}}`；`permissions: {contents: read}`；job `send`，`timeout-minutes: 10`；步骤 checkout@v4 → setup-python@v5（3.12，`cache: pip`）→ `pip install -r requirements.txt` → `python -m src.main`，env 注入 4 个 Secret 与 `TZ: Asia/Shanghai`。

`snapshot.yml`：仅 `workflow_dispatch`，用 `curl` 把 5 个端点原始响应写到 `tests/fixtures/raw/`，然后 `upload-artifact@v4`（路径 `tests/fixtures/raw/`，保留 7 天）。只用于取真实样本，不参与日常发送。

`keepalive.yml`：`schedule` 为 `0 0 1 * *`，`contents: write`，checkout 后 `echo $(date -u +%F) > .keepalive && git commit -am "chore: keepalive" && git push`。

`README.md`：写清 5 步部署（建私有仓库、push、加 2 个 Secrets、QQ 邮箱开 SMTP 拿授权码、手动 Run workflow）、本地跑测试的方式、如何改源和条数、常见问题（为什么周六论文少、为什么某天没收到）。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_workflows.py -v && python -m pytest -q`
Expected: PASS（3 passed，随后全量 PASS）

- [ ] **Step 5: 提交**

```bash
git add .github README.md tests/test_workflows.py
git commit -m "ci: add daily, snapshot, and keepalive workflows"
```

---

### Task 11: 首次实跑（由用户在 GitHub 上执行）

**Files:** 无

- [ ] **Step 1:** 在 GitHub 新建私有仓库 `ai-daily-digest`（不勾 README）。
- [ ] **Step 2:** 本地 `git remote add origin <repo-url> && git branch -M main && git push -u origin main`。
- [ ] **Step 3:** Settings → Secrets and variables → Actions：添加 `DEEPSEEK_API_KEY`、`QQ_SMTP_AUTH_CODE`。
- [ ] **Step 4:** QQ 邮箱 → 设置 → 账户 → 开启 SMTP → 生成 16 位授权码 → 填入 Step 3。
- [ ] **Step 5:** Actions → daily-digest → Run workflow；确认 1 分钟内收到邮件，且邮件正文里的链接可点、中文正常。
- [ ] **Step 6:** 当晚不用管，次日 08:30 后确认自动触发（Actions 显示由 `schedule` 触发，而非手动）。
- [ ] **Step 7:** 去 DeepSeek 后台重新生成一次 API key（旧 key 已在对话中暴露），更新 Secret。

**验收标准：** 连续 2 天自动收到邮件；某天故意把 Secret 改错时应收到 GitHub 的失败通知；周末邮件仍能收到（资讯为主，论文可能为 0）。
