# AI Daily Digest

**English** | [中文](README.zh-CN.md)

Every morning at 08:30 Beijing time, the day's AI papers and news worth reading arrive in your inbox, each with a one-line Chinese summary.

- Papers: arXiv (cs.AI / cs.LG / cs.CL) and HuggingFace Daily Papers
- News: 量子位, 机器之心 and 36氪, filtered by AI keywords
- Scoring: DeepSeek; only items scoring 4 or above are kept, at most 6 papers + 8 news items
- Runs as a GitHub Actions schedule; you do not need a server

Design doc: `docs/superpowers/specs/2026-11-10-ai-daily-digest-design.md`
Implementation plan: `docs/superpowers/plans/2026-11-10-ai-daily-digest.md`

## Local development

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

All tests run offline and never touch the network.

## Deployment (about five minutes)

1. Create a repository on GitHub named `ai-daily-digest` (public or private; do not initialise it with a README or .gitignore).
2. Push from your machine:

   ```bash
   git remote add origin https://github.com/ChenyangZhao7/ai-daily-digest.git
   git branch -M main
   git push -u origin main
   ```

3. Repository Settings → Secrets and variables → Actions, add:
   - `DEEPSEEK_API_KEY`
   - `QQ_SMTP_AUTH_CODE`
   - `MAIL_TO`: the receiving address
   - `MAIL_FROM`: the sending address (must match the SMTP login account)
4. QQ Mail → Settings → Account → enable POP3/SMTP → generate a 16-character auth code and put it in `QQ_SMTP_AUTH_CODE`. This code is not your login password.
5. Actions → daily-digest → Run workflow, then confirm the mail arrives.

After that, change configuration by editing `config.yaml` and pushing.

## Configuration

`config.yaml`:

| Field | Meaning |
|---|---|
| `limits.max_papers` / `max_news` | Maximum papers / news items per email |
| `limits.score_threshold` | Cut-off score (default 4) |
| `sources.arxiv.categories` | arXiv categories to crawl |
| `sources.rss` | News sources; when `keywords` is non-empty, items are filtered by it |
| `llm.model` | DeepSeek model name |

## FAQ

**Very few papers on Saturday and Sunday?** arXiv publishes nothing at the weekend. The window is still 72 hours, but weekend emails are mostly news. Monday's run brings back Friday's papers automatically.

**No email one day?** Check in order: whether Actions is disabled (GitHub disables scheduled workflows after 60 days of inactivity; `keepalive.yml` commits once a month to prevent this), whether the Actions log reports an error, then the spam folder.

**Every source failed?** You get an alert email titled "今日抓取失败" listing the error for each source.

**Summaries failed?** The email is still sent; the score is simply empty and the subject says "未生成摘要".

## Security

- Keys live only in GitHub Secrets; nothing plaintext is in the repository or the logs.
- All external content in the email is HTML-escaped.

## License

MIT
