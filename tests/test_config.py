import logging
import subprocess
import sys
from pathlib import Path

from auto_job_apply import config
from auto_job_apply.config import (
    SUBSYSTEM_ENV_KEYS,
    ensure_data_dir,
    missing_env_keys,
    settings,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestDefaults:
    def test_data_dir_default(self) -> None:
        assert settings.get("DATA.dir") == "data"

    def test_llm_defaults(self) -> None:
        assert settings.get("LLM.model") == "openai/gpt-4.1-mini"
        assert settings.get("LLM.temperature") == 0

    def test_filler_defaults(self) -> None:
        assert settings.get("FILLER.headless") is True
        assert settings.get("FILLER.timeout_ms") == 45000
        assert settings.get("FILLER.screenshots") is True

    def test_email_defaults(self) -> None:
        assert settings.get("EMAIL.poll_interval_seconds") == 300
        assert settings.get("EMAIL.account") == "taylor.wong@agentmail.to"

    def test_evals_default(self) -> None:
        assert settings.get("EVALS.mock_base_url") == "http://localhost:5173"

    def test_api_local_override(self) -> None:
        # settings.local.json.example intentionally overrides API.host to
        # 127.0.0.1 so host binding is loopback-safe by default in dev.
        # settings.json (committed) still specifies the container-facing default.
        assert settings.get("API.host") == "127.0.0.1"
        assert settings.get("API.port") == 8000


class TestDataDir:
    def test_ensure_data_dir_creates(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "csv-root"
        created = ensure_data_dir(target)
        assert created == target
        assert target.is_dir()

    def test_import_created_repo_data_dir(self) -> None:
        # Import-time validate() must have created the default data dir.
        assert (REPO_ROOT / "data").is_dir()


class TestEnvOverrides:
    def test_nested_env_override(self) -> None:
        # Fresh interpreter: AUTO_JOB_APPLY_LLM__MODEL must beat settings.json.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from auto_job_apply.config import settings; print(settings.LLM.model)",
            ],
            cwd=REPO_ROOT,
            env={"PATH": "/usr/bin:/bin", "AUTO_JOB_APPLY_LLM__MODEL": "test/override-model"},
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "test/override-model"


class TestMissingSecretsWarnOnly:
    def test_missing_env_keys_grouped(self, monkeypatch) -> None:
        for keys in SUBSYSTEM_ENV_KEYS.values():
            for key in keys:
                monkeypatch.delenv(key, raising=False)
        missing = missing_env_keys()
        assert set(missing) == {"llm", "browser", "email", "langfuse"}
        assert missing["llm"] == ["OPENROUTER_API_KEY"]

    def test_missing_env_keys_subset(self, monkeypatch) -> None:
        monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        missing = missing_env_keys(["llm", "email"])
        assert missing["llm"] == []
        assert missing["email"] == ["AGENTMAIL_API_KEY"]

    def test_validate_warns_and_does_not_raise(self, monkeypatch, caplog, tmp_path) -> None:
        for keys in SUBSYSTEM_ENV_KEYS.values():
            for key in keys:
                monkeypatch.delenv(key, raising=False)
        with caplog.at_level(logging.WARNING, logger=config.logger.name):
            missing = validate(["email"])
        assert missing == {"email": ["AGENTMAIL_API_KEY"]}
        assert any("AGENTMAIL_API_KEY" in r.message for r in caplog.records)

    def test_validate_silent_when_keys_present(self, monkeypatch, caplog) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        with caplog.at_level(logging.WARNING, logger=config.logger.name):
            missing = validate(["llm"])
        assert missing == {}
        assert not caplog.records
