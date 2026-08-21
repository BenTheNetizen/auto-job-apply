import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from auto_job_apply.services import learning, profile


def _tmp_path(tmp_path: Path) -> Path:
    return tmp_path / "p.csv"


class TestAliasHit:
    def test_alias_hit_returns_key_no_llm(self, tmp_path: Path) -> None:
        # Patch the lazy LLM import to a sentinel that would explode on touch.
        with patch.object(learning, "_canonicalize_via_llm") as llm_mock:
            assert learning.canonicalize("veteran") == "veteran_status"
            llm_mock.assert_not_called()

    def test_case_insensitive(self) -> None:
        assert learning.canonicalize("VETERAN") == "veteran_status"
        assert learning.canonicalize("Are You A Protected Veteran?") == "veteran_status"

    def test_alias_hit_normalizes_punctuation(self) -> None:
        assert learning.canonicalize("protected-veteran!") == "veteran_status"

    def test_alias_some_values(self) -> None:
        assert learning.canonicalize("disability") == "disability_status"
        assert learning.canonicalize("Will You Now Or In The Future Require Sponsorship") == "visa_sponsorship"
        assert learning.canonicalize("gender") == "gender_identity"


class TestLlmFallback:
    def test_llm_path_mocks_structured_and_returns_key(self) -> None:
        fake_llm = ModuleType("auto_job_apply.services.llm")

        class _Result:
            def __init__(self, key: str) -> None:
                self.canonical_key = key

        runnable = MagicMock()
        runnable.invoke.return_value = _Result("veteran_status")
        structured = MagicMock(return_value=runnable)
        fake_llm.structured = structured  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"auto_job_apply.services.llm": fake_llm}):
            assert learning.canonicalize("veteran-unmapped-input") == "veteran_status"
            structured.assert_called_once()
            runnable.invoke.assert_called_once()

    def test_llm_path_returns_none_when_llm_module_missing(self) -> None:
        # Drop cached alias table, remove the module from sys.modules.
        with patch.dict(sys.modules, {"auto_job_apply.services.llm": None}):
            assert learning.canonicalize("veteran-unmapped-input") is None


class TestLearn:
    def test_learn_writes_authoritative(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        learning.learn("veteran", "no", path=p)
        assert profile.get_authoritative("veteran_status", p) == "no"

    def test_learn_llm_draft_non_authoritative(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        learning.learn("veteran", "no", source="llm_draft", path=p)
        assert profile.get_authoritative("veteran_status", p) is None
        assert profile.get("veteran_status", p) == ""

    def test_unmapped_label_falls_back_to_normalized(self, tmp_path: Path) -> None:
        with patch.object(learning, "_canonicalize_via_llm", return_value=None):
            p = _tmp_path(tmp_path)
            learning.learn("Some Brand New Question", "1", path=p)
            assert profile.get("some_brand_new_question", p) == "1"


class TestSuggest:
    def test_suggest_returns_authoritative(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        learning.learn("veteran", "yes", path=p)
        assert learning.suggest("protected veteran", p) == "yes"

    def test_suggest_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert learning.suggest("veteran", _tmp_path(tmp_path)) is None
