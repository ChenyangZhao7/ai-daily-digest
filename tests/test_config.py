from src.config import load_config


def test_load_config_reads_yaml_and_applies_env_overrides(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text("limits:\n  max_papers: 6\n", encoding="utf-8")
    monkeypatch.setenv("MAIL_TO", "someone@example.com")
    cfg = load_config(str(p))
    assert cfg["limits"]["max_papers"] == 6
    assert cfg["email"]["to"] == "someone@example.com"
