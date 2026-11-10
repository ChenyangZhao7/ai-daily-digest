# AI 日报邮件 · 设计文档

日期：2026-11-10
状态：待确认

## 1. 意图（为什么做）

每天自动给一个人（`your-email@example.com`）发一封邮件，内容是当天值得看的 **AI 论文 + AI 资讯**，每条附一句中文说明，按重要性排序。

核心痛点不是"找不到信息"，而是"信息太多、懒得筛"。所以这个产品的价值在 **筛选和解释**，不在搬运。判断成功的标准：每天早上打开邮件，30 秒内能决定"今天要不要点开某一篇"；一个月后仍然每天在看，而不是直接归档。

## 2. 目标 / 非目标 / 反目标

**目标**
- 每天北京时间 8:30 一封邮件，自动送达，不需要人参与。
- 论文 3–6 条、资讯 5–8 条，总条数 ≤ 15（用户明确接受的上限 15 以内）。
- 每条都有：标题、来源、链接、一句中文说明（≤40 字）、重要性标记。
- 零服务器、零常开设备；运行成本每月 < 1 元。

**非目标**
- 不做网页、小程序、App 前端。
- 不做历史归档站点、搜索、订阅管理界面。
- 不做个性化推荐学习（没有用户行为数据）。
- 不做多人订阅、不做付费墙内容抓取。
- 不做中英文对照全文翻译。

**反目标（即使技术跑通也算失败）**
- 邮件超过 20 条，或需要滚动两屏以上 → 又变成信息过载。
- 摘要需要用户自己读原文才能理解 → 说明没说清"为什么值得看"。
- 依赖用户本机开机 / 挂代理才能送达。
- 出现"今天没发"且用户不知道原因（静默失败）。

## 3. 约束

| 约束 | 影响 |
|---|---|
| 开发机（Windows）直连 arXiv、HuggingFace、Google 全部超时；仅国内源与 GitHub 可通 | 抓取逻辑必须在 GitHub Actions（海外）验证；本地只能用离线 fixture 做单测 |
| 用户要求"轻量化" | 单仓库、单次定时任务、无数据库、无服务端 |
| 用户已提供 DeepSeek API key 与 QQ 邮箱 | 摘要用 DeepSeek；发信走 smtp.qq.com |
| QQ 邮箱要求授权码而非密码 | 授权码由用户生成，仅存 GitHub Secrets |
| arXiv 周末不发布新论文 | 统一用 72 小时窗口，否则周一邮件内容为空 |
| 用户接受论文重复，但同一篇最多出现 5 次 | 72h 窗口下同一篇最多出现 3 次（周二/周三/周四），天然满足，无需状态文件 |

## 4. 方案比较（已在对话中由用户选定）

**方案 1 · GitHub Actions（选定）**
仓库 + cron 触发 + Python 脚本。Actions 免费额度：公开仓库免费，私有仓库 2000 分钟/月；本任务每天 1–2 分钟。海外 runner 直连 arXiv/HF。密钥存 GitHub Secrets。代价：需要一次性配置 10 分钟；cron 可能有几分钟延迟。

**方案 2 · 本机 Windows 任务计划**
不需要 GitHub，但电脑必须常开、arXiv 必须挂代理。用户本机当前代理未运行，arXiv 不可达 → 排除。

**方案 3 · 云函数（阿里云 FC / 腾讯云 SCF）**
无需本机，但国内节点访问 arXiv/HF 同样不稳，且要实名开账号、调试链路更长。对"轻量化"为负分 → 排除。

**选择理由**：方案 1 同时解决"定时""海外网络""免费"三件事，唯一成本是一次性配置。

## 5. 架构

```
GitHub Actions (cron 30 0 * * *)
        │
        ▼
   main.py ──► sources（并发抓取，可失败）
        │        ├── arXiv Atom API（cs.AI / cs.LG / cs.CL）
        │        ├── HuggingFace Daily Papers
        │        ├── 量子位 RSS
        │        ├── 机器之心 RSS
        │        └── 36氪 RSS（AI 关键词过滤）
        ▼
   标准化 Item + 去重 + 时间窗过滤
        ▼
   summarize.py ──► DeepSeek（单次批量调用，返回 JSON）
        │            打分 1–5 + 一句中文说明
        ▼
   排序截断（论文 ≤6，资讯 ≤8）
        ▼
   render.py ──► 600px 宽、table 布局的 HTML
        ▼
   mailer.py ──► smtp.qq.com:465 (SSL) ──► 用户邮箱
```

### 5.1 数据源细节

| 源 | 端点 | 取什么 | 窗口 |
|---|---|---|---|
| arXiv | `https://export.arxiv.org/api/query` | 单次查询 `(cat:cs.AI OR cat:cs.LG OR cat:cs.CL) AND submittedDate:[window]`，`sortBy=submittedDate`，`max_results=60` | 固定 72h |
| HF Daily Papers | `https://huggingface.co/api/daily_papers?limit=50` | 当日榜单，按 upvotes 取前 10 进候选 | 当日 |
| 量子位 | `https://www.qbitai.com/feed` | RSS 全部条目 | 最近 24h |
| 机器之心 | `https://www.jiqizhixin.com/rss` | RSS 全部条目 | 最近 24h |
| 36氪 | `https://www.36kr.com/feed` | 标题/摘要命中 AI 关键词才收（关键词表放 config） | 最近 24h |

arXiv 只发 1 个请求（用 OR 合并分类），避免触发 3 秒/次的限速要求。

### 5.2 候选池预筛（确定性规则，在 LLM 之前）

- 先合并去重：URL 规范化后相同则合并；标题相似度 > 0.9 视为重复（`difflib.SequenceMatcher`），保留来源优先级更高的一条。
- 名额分配（保证不被单一大源挤占）：arXiv 按 `submittedDate` 取最新 **20** 条；HF Daily Papers 按 upvotes 取 **10** 条；量子位 / 机器之心 / 36氪各取 **5** 条（36氪先过 AI 关键词过滤）。
- 合计上限 40 条（20+10+5+5+5 = 45，超出时从最旧的非 arXiv 条目开始丢弃）。
- 每条标题 + 摘要截断到 300 字，保证单次 LLM 调用约 8k tokens。

### 5.3 打分标准（用户偏好：LLM/Agent 为主、架构为主、高度技术化）

LLM 按以下顺序判断，输出 score 1–5：

| 分值 | 含义 |
|---|---|
| 5 | 大模型 / Agent 方向，且涉及**架构、训练或推理系统**层面的实质贡献（如新架构、高效注意力、长上下文、MoE、RL 训练方法、Agent 编排/记忆/工具使用框架、推理加速） |
| 4 | 同方向的方法类工作，但增量较小；或非 LLM 方向的强系统类工作 |
| 3 | 有技术含量但偏应用 / 偏实验分析 / 可迁移价值一般 |
| 2 | 纯 benchmark、纯 survey、小改进、应用层调参 |
| 1 | 与用户关注方向无关（推荐系统、传统 CV/NLP 应用、教育/医疗应用等） |

补充规则：
- **高度技术化**：一句说明必须落到机制或结论上（"用 X 解决 Y，在 Z 上提升 N%"），禁止"提出了一种新方法""效果显著"这类空话。
- Agent / 推理系统 / 训练效率 相关条目在 score 相同时优先。
- 理论、具身智能、推荐系统不额外加分也不直接排除，按上表自然落分。
- 一次调用完成全部打分，返回 JSON 数组：`{id, score, blurb(≤40字中文)}`。按 score 降序、同分按发布时间降序。

### 5.4 截断与重复

- 论文最多 6 条，资讯最多 8 条。
- 只收 score ≥ 4；若 score ≥ 4 的不足 3 条，放宽到 score 3，最多补到 3 条。不为了凑数降低标准。
- 总数不足 5 条时照发，不报错。
- 同一篇论文可能连续出现（固定 72h 窗口），**上限 3 次**（周二/周三/周四），满足用户"最多 5 次"的要求，实现上不需要状态文件。

### 5.5 邮件形态

- 主题：`AI 日报 11-10｜论文 6 篇 · 资讯 8 条`
- 正文：顶部日期 + 一句今日总览（LLM 生成，≤60 字）；论文区；资讯区；页脚（各来源、生成时间、"改配置请见仓库 README"）。
- HTML 用 table + 内联样式，宽度 600px。**不用 flex/grid**，保证 QQ 邮箱 / 手机客户端正常渲染。
- 所有抓取内容做 HTML 转义后输出。
- 重要性标记：score 5 → ⭐️，score 4 → 无标记，score ≤3 一般不入选。

正文字数控制在 1.5 屏以内。

### 5.6 失败与降级

| 情况 | 行为 |
|---|---|
| 单个源抓取失败/超时（10s） | 跳过该源，日志记录，继续 |
| 全部源失败 | 发一封"今日抓取全部失败"告警邮件（含各源错误摘要），避免静默 |
| DeepSeek 超时/报错/返回非法 JSON | 降级为纯清单：不打分、不写说明，按时间排序，标题加注"今日未生成摘要" |
| LLM 返回条目不完整 | 缺失的条目按 score=3 处理，仍进邮件 |
| SMTP 发送失败 | 脚本退出码非 0，GitHub Actions 标红，GitHub 自动发失败邮件 |

所有外部调用带超时与 1 次重试。

## 6. 仓库结构

```
ai-daily-digest\
├─ .github/workflows/daily.yml     # cron + workflow_dispatch
├─ .github/workflows/snapshot.yml  # 手动抓真实响应，产出 fixture
├─ .github/workflows/keepalive.yml # 每月提交一次，防止定时任务被停用
├─ config.yaml                     # 源开关、条数、模型名、关键词
├─ requirements.txt                # requests, feedparser, pyyaml, pytest
├─ src/
│  ├─ main.py                      # 串联：抓取→处理→摘要→渲染→发送
│  ├─ sources.py                   # 五个源 → 统一 Item 结构
│  ├─ summarize.py                 # DeepSeek 调用 + JSON 容错 + 降级
│  ├─ render.py                    # HTML 渲染
│  └─ mailer.py                    # SMTP 发送
├─ tests/
│  ├─ fixtures/                    # 录制的 arXiv XML / HF JSON / RSS 样本
│  └─ test_*.py
└─ docs/superpowers/specs/         # 本文件
```

预估 400–500 行 Python。

## 7. 配置与密钥

**GitHub Secrets（唯一存放密钥的地方）**
- `DEEPSEEK_API_KEY`
- `QQ_SMTP_AUTH_CODE`
- `MAIL_TO`（默认 `your-email@example.com`，可不设）
- `MAIL_FROM` 固定等于发件 QQ 邮箱。QQ SMTP 要求认证账号与 From 一致，因此不支持换发件身份。

**config.yaml（可提交 Git，不含密钥）**
源开关、每类条数上限、LLM 模型名（`deepseek-chat`）、36氪关键词、cron 之外的展示文案。

`.gitignore` 排除 `.env`、`*.local.yaml`、`tests/fixtures/**/raw/`。

## 8. 时区与调度

- cron：`30 0 * * *`（UTC）= 北京时间 08:30。
- 脚本内统一用 `Asia/Shanghai` 计算"今天"，避免 runner 时区（UTC）导致日期错位。
- 同时提供 `workflow_dispatch` 手动触发，用于首次联调和排错。
- **保活**：GitHub 会在仓库 60 天无活动后自动停用定时 workflow，且不报警。加一个 `keepalive.yml`，每月 1 号提交一次时间戳到 `.keepalive` 文件（1 行、1 次提交/月），避免静默断更。

## 9. 测试策略

本机无法访问外网，测试全部离线：

1. 先按官方 API/RSS 格式手写 fixture（本机取不到真实响应）；随后加一个 `snapshot.yml`（`workflow_dispatch` 手动触发），在 Actions 上抓一次真实响应存成 artifact，下载后替换 `tests/fixtures/`，保证解析逻辑贴着真实格式。
2. 必测项：
   - arXiv XML 解析（标题/摘要中的换行、HTML 实体、多分类）
   - 时间窗过滤（含周一 72h 边界、周末无论文）
   - 去重（同 URL 不同参数、标题近似）
   - LLM 返回：合法 JSON / 带 ```json 包裹 / 缺字段 / 完全非法 → 四种都不得抛异常
   - HTML 渲染：内容中的 `<script>`、引号、中文均被正确转义
   - 降级路径：LLM 失败时仍生成可发送的 HTML
3. 真实链路：推送后在 Actions 页面点 `Run workflow`，确认收到邮件；再观察连续 2 天自动触发。

## 10. 成本与限制

- GitHub Actions：每天 1–2 分钟，月耗 < 60 分钟（公开仓库免费；私有仓库 2000 分钟/月）。
- DeepSeek：每天 1–2 次调用，约 8k 输入 / 1k 输出，**每天 0.01–0.03 元**，每月 < 1 元。
- 仓库：< 1 MB。
- 已知限制：cron 触发可能延迟数分钟；arXiv 偶发 5xx 需靠重试；HF Daily Papers 榜单每天更新一次，可能与 arXiv 论文重复（已由去重处理）。

## 11. 已由用户决定的事

1. 推送渠道：邮件（不是小程序/网页）。
2. 内容深度：清单 + 一句中文说明 + 排序（方案 B），不是纯清单。
3. 运行方式：GitHub Actions（方案 1）。
4. 摘要模型：DeepSeek（用户提供 key），模型 `deepseek-chat`。
5. 邮箱：QQ 邮箱，发件与收件同为 `your-email@example.com`。
6. 内容偏好：**大模型 / Agent 为主，架构为主，高度技术化**（打分标准见 5.3）。
7. 重复：接受重复，同一篇最多 5 次；72h 窗口下实际上限 3 次，不做状态文件。
8. GitHub 账号：`ChenyangZhao7`；仓库由用户本人创建，密钥由用户填入 Secrets。

## 12. 执行分工（部署）

代码、测试、workflow 文件在本地完成并 `git init`；以下步骤由用户执行（约 5 分钟，我会给出逐条命令）：

1. 在 GitHub 新建仓库 `ai-daily-digest`（不要勾选 README）。
2. 本地添加 remote 并 `git push`。
3. 在 Settings → Secrets and variables → Actions 添加 `DEEPSEEK_API_KEY`、`QQ_SMTP_AUTH_CODE`。
4. 去 QQ 邮箱设置 → 账户 → 开启 SMTP 服务，生成授权码（16 位），填入上一步。
5. Actions 页面手动 `Run workflow`，确认收到邮件。

## 13. 留给实现者的判断

- HTML 模板的具体样式细节（配色、字号、间距）。
- 日志格式与输出详细程度。
- 重试次数与退避策略的具体数值（当前约定 1 次重试、10s 超时）。
- 是否额外加入 Hacker News 作为第 4 个资讯源（默认不加，保持轻量）。
- 是否按星期调整内容量（默认不调）。

