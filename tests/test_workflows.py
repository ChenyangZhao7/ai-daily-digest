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
