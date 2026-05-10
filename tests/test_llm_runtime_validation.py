from pathlib import Path

import scripts.validate_runtime as validate_runtime


def _write_llm_config(root: Path) -> None:
    config_path = root / "configs" / "runtime"
    config_path.mkdir(parents=True, exist_ok=True)
    (config_path / "llm.yaml").write_text(
        """
llm:
  enabled: true
  provider: "openai"
  default_provider: "openai"
  providers:
    local_stub:
      enabled: true
    openai:
      enabled: true
      api_key_env: "OPENAI_API_KEY"
  development:
    allow_local_stub_if_openai_key_missing: true
  production:
    fail_if_enabled_provider_missing: true
    fail_if_openai_key_missing: true
""".strip(),
        encoding="utf-8",
    )


def test_validate_llm_configuration_warns_in_development_when_key_missing(tmp_path, monkeypatch):
    _write_llm_config(tmp_path)
    monkeypatch.setattr(validate_runtime, "ROOT", tmp_path)
    monkeypatch.setattr(validate_runtime, "_try_import", lambda module: True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    results = validate_runtime.validate_llm_configuration("development")
    env_result = next(item for item in results if item["name"] == "OPENAI_API_KEY")
    assert env_result["status"] == "WARN"


def test_validate_llm_configuration_fails_in_production_when_key_missing(tmp_path, monkeypatch):
    _write_llm_config(tmp_path)
    monkeypatch.setattr(validate_runtime, "ROOT", tmp_path)
    monkeypatch.setattr(validate_runtime, "_try_import", lambda module: True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    results = validate_runtime.validate_llm_configuration("production")
    env_result = next(item for item in results if item["name"] == "OPENAI_API_KEY")
    assert env_result["status"] == "FAIL"
