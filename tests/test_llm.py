"""Spec: .spec/AutoJobApply/shared-infra/llm-openrouter.md

Acceptance (unit level):
- model defaults from settings; per-role override honored
- Langfuse callback attached when env present, none when absent (no crash)
- structured() picks with_structured_output first; falls back to prompt+parse
- OPENROUTER base URL pinned; API key sourced from env
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from auto_job_apply.services import llm as svc


class FieldOut(BaseModel):
    full_name: str
    email: str


class TestModelResolution:
    def _fake_settings(self):
        values = {
            "LLM.model": "openai/gpt-4.1-mini",
            "LLM.planner_model": "anthropic/claude-sonnet-4",
            "LLM.temperature": 0.3,
        }
        fake = MagicMock()
        fake.get = values.get  # single source of truth
        return fake

    def test_default_role_uses_llm_model(self, monkeypatch):
        monkeypatch.setattr(svc, "settings", self._fake_settings())
        monkeypatch.delenv("AUTO_JOB_APPLY_LLM__DEFAULT_MODEL", raising=False)
        assert svc._model_for("default") == "openai/gpt-4.1-mini"

    def test_role_override_wins(self, monkeypatch):
        monkeypatch.setattr(svc, "settings", self._fake_settings())
        monkeypatch.delenv("AUTO_JOB_APPLY_LLM__PLANNER_MODEL", raising=False)
        assert svc._model_for("planner") == "anthropic/claude-sonnet-4"
        assert svc._model_for("default") == "openai/gpt-4.1-mini"

    def test_temperature_from_settings(self, monkeypatch):
        monkeypatch.setattr(svc, "settings", self._fake_settings())
        assert svc._temperature() == 0.3

    def test_temperature_default_zero(self, monkeypatch):
        fake = MagicMock()
        fake.get = lambda key, default=None: default
        monkeypatch.setattr(svc, "settings", fake)
        assert svc._temperature() == 0.0

    def test_role_override_via_nested_env(self, monkeypatch):
        """The parent runs this shape with nested env overrides; make sure
        our settings.get call surface handles it."""
        fake = self._fake_settings()
        fake.get = lambda key, default=None: {
            "LLM.planner_model": "anthropic/claude-sonnet-4",
            "LLM.model": "openai/gpt-4.1-mini",
        }.get(key, default)
        monkeypatch.setattr(svc, "settings", fake)
        assert svc._model_for("planner") == "anthropic/claude-sonnet-4"


class TestGetLlm:
    def test_openrouter_base_and_env_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        # Ensure no-langfuse / no-callbacks path doesn't crash on the real
        # service factory.
        monkeypatch.setattr(svc, "get_callback_handler", lambda: None)

        with patch("auto_job_apply.services.llm.ChatOpenAI") as chat:
            svc.get_llm("default")

        kwargs = chat.call_args.kwargs
        assert kwargs["base_url"] == svc.OPENROUTER_BASE_URL
        assert kwargs["api_key"] == "sk-or-test"

    def test_callbacks_attached_when_langfuse_ready(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        fake_handler = MagicMock(name="LangfuseHandler")
        monkeypatch.setattr(svc, "get_callback_handler", lambda: fake_handler)

        with patch("auto_job_apply.services.llm.ChatOpenAI") as chat:
            svc.get_llm("default")

        assert chat.call_args.kwargs["callbacks"] == [fake_handler]

    def test_callbacks_none_when_langfuse_absent(self, monkeypatch):
        monkeypatch.setattr(svc, "get_callback_handler", lambda: None)
        with patch("auto_job_apply.services.llm.ChatOpenAI") as chat:
            svc.get_llm("default")
        assert chat.call_args.kwargs["callbacks"] is None

    def test_role_model_passed_to_constructor(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.setattr(svc, "_model_for", lambda role: f"model-for-{role}")
        monkeypatch.setattr(svc, "get_callback_handler", lambda: None)
        with patch("auto_job_apply.services.llm.ChatOpenAI") as chat:
            svc.get_llm("planner")
        assert chat.call_args.kwargs["model"] == "model-for-planner"


class TestStructured:
    def test_prefers_with_structured_output(self):
        model = MagicMock()
        runnable = svc.structured(model, FieldOut)
        assert runnable is model.with_structured_output.return_value
        model.with_structured_output.assert_called_once_with(FieldOut)

    def test_falls_back_to_prompt_parse(self):
        model = MagicMock()
        model.with_structured_output.side_effect = Exception(
            "response_format not supported"
        )
        runnable = svc.structured(model, FieldOut)
        assert runnable is not None  # fallback chain returned

    def test_fallback_chain_binds_prompt_model_parser(self):
        """Fallback runnable composes prompt | model | parser via LCEL."""
        model = MagicMock()
        model.with_structured_output.side_effect = Exception("unsupported")

        sentinel = object()
        # Stub ChatPromptTemplate `|` chain: own first link returns sentinel
        # after combining model + parser; the LLM module doesn't care.
        prompt_stub = MagicMock()
        prompt_stub.__or__ = MagicMock(return_value=prompt_stub)
        # Under MagicMock duck typing, `prompt | model | parser` reduces to
        # successive calls of __or__, each returning same stub. We only need
        # the two-arity composition to be exercised.
        with patch("auto_job_apply.services.llm.ChatPromptTemplate") as tpl, \
                patch("auto_job_apply.services.llm.PydanticOutputParser") as parser:
            tpl.from_messages.return_value = prompt_stub
            svc.structured(model, FieldOut)
            tpl.from_messages.assert_called_once()
            prompt_stub.partial.assert_called_once()
            parser.assert_called_once_with(pydantic_object=FieldOut)


class TestLogUsage:
    def test_logs_tokens_and_cost_from_usage(self, caplog):
        response = MagicMock()
        response.response_metadata = {
            "usage": {"total_tokens": 321, "cost": 0.0004},
        }
        with caplog.at_level("INFO", logger="auto_job_apply.llm"):
            svc.log_usage(response)
        assert any("tokens=321" in r.message for r in caplog.records)

    def test_silent_when_no_usage(self, caplog):
        response = MagicMock()
        response.response_metadata = {}
        with caplog.at_level("INFO", logger="auto_job_apply.llm"):
            svc.log_usage(response)
        assert not caplog.records
