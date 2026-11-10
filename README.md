# AI 日报

每天早上 08:30（北京时间）把当天值得看的 AI 论文与资讯，加上一句中文说明，发到邮箱。

- 论文来源：arXiv（cs.AI / cs.LG / cs.CL）、HuggingFace Daily Papers
- 资讯来源：量子位、机器之心、36氪（AI 关键词过滤）
- 打分：DeepSeek，只收 4 分以上，最多 6 篇论文 + 8 条资讯
- 运行：GitHub Actions 定时任务，不需要自己的服务器

设计文档：`docs/superpowers/specs/2026-11-10-ai-daily-digest-design.md`
实施计划：`docs/superpowers/plans/2026-11-10-ai-daily-digest.md`

## 本地开发

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

测试全部离线，不访问网络。

## 部署（约 5 分钟）

1. 在 GitHub 新建**私有**仓库 `ai-daily-digest`（不要勾选 README / .gitignore）。
2. 本地推送：

   ```bash
   git remote add origin https://github.com/ChenyangZhao7/ai-daily-digest.git
   git branch -M main
   git push -u origin main
   ```

3. 仓库 Settings → Secrets and variables → Actions，添加：
   - `DEEPSEEK_API_KEY`
   - `QQ_SMTP_AUTH_CODE`

   可选：`MAIL_TO`、`MAIL_FROM`（默认都是 `your-email@example.com`）。
4. QQ 邮箱 → 设置 → 账户 → 开启「POP3/SMTP 服务」→ 生成 16 位授权码，填入 `QQ_SMTP_AUTH_CODE`。授权码不是登录密码。
5. Actions → daily-digest → Run workflow，确认收到邮件。

之后再改配置只需改 `config.yaml` 并 push。

## 配置

`config.yaml`：

| 字段 | 含义 |
|---|---|
| `limits.max_papers` / `max_news` | 每封邮件最多几篇论文 / 几条资讯 |
| `limits.score_threshold` | 入选分数线（默认 4） |
| `sources.arxiv.categories` | 要抓的 arXiv 分类 |
| `sources.rss` | 资讯源列表；`keywords` 非空时按关键词过滤 |
| `llm.model` | DeepSeek 模型名 |

## 常见问题

**周六/周日论文很少？** arXiv 周末不发布新论文，窗口虽是 72 小时，但周末的邮件基本只有资讯。周一会自动带回周五的论文。

**某天没收到邮件？** 依次看：Actions 是否被禁用（仓库 60 天无活动会被 GitHub 停用，`keepalive.yml` 每月会提交一次来避免）；Actions 运行日志是否报错；垃圾邮件箱。

**抓取全部失败怎么办？** 会收到一封标题含「今日抓取失败」的告警邮件，里面列出每个源的错误。

**摘要出错了？** 邮件仍会发出，只是打分为空，标题会标注「未生成摘要」。

## 安全

- 密钥只存在 GitHub Secrets，仓库与日志里没有明文。
- 邮件里所有外部内容都做了 HTML 转义。
