from src.config import load_config


def test_load_config_reads_yaml_and_applies_env_overrides(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text("limits:\n  max_papers: 6\n", encoding="utf-8")
    monkeypatch.setenv("MAIL_TO", "someone@example.com")
    cfg = load_config(str(p))
    assert cfg["limits"]["max_papers"] == 6
    assert cfg["email"]["to"] == "someone@example.com"


def test_default_config_contains_no_personal_email(tmp_path, monkeypatch):
    monkeypatch.delenv("MAIL_TO", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    p = tmp_path / "config.yaml"
    p.write_text("{}", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg["email"]["to"] == ""
    assert cfg["email"]["from"] == ""
