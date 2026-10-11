"""Redacção assistida por IA: validação, fallback e fornecedor (DEC-059)."""

import json
from pathlib import Path

import pytest

from tensdireito_content_engine.ai_draft import SYSTEM_PROMPT, write_whatsapp
from tensdireito_content_engine.llm import LLMError, LoadedLLM, TaskConfig, load_provider

TASK = TaskConfig(model="m", temperature=0.3, max_tokens=600, prompt_id="llm:test")
SOURCE = (
    "Os alunos do ensino secundário com Ação Social Escolar podem pedir a bolsa de mérito. "
    "O valor é de 1.342,83 euros e a candidatura termina a 30 de setembro."
)


class FakeProvider:
    name = "fake"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def complete(self, task, system, user):
        self.calls.append((task, system, user))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def llm(*answers):
    provider = FakeProvider(*answers)
    return provider, LoadedLLM(provider=provider, tasks={"whatsapp_draft": TASK})


def answer(**overrides):
    data = {
        "emoji": "🎓",
        "titulo": "Bolsa de mérito: há apoio para alunos com boas notas",
        "pontos": [
            "Para alunos do secundário com Ação Social Escolar",
            "Valor de 1.342,83 €; candidatura até 30 de setembro",
        ],
    } | overrides
    return json.dumps(data, ensure_ascii=False)


def test_valid_answer_becomes_the_draft():
    provider, loaded = llm(answer())
    draft = write_whatsapp(loaded, "Bolsa de mérito", SOURCE)
    assert draft.emoji == "🎓"
    assert draft.title.startswith("Bolsa de mérito")
    assert len(draft.key_points) == 2
    assert draft.prompt_id == "llm:test"
    _, system, user = provider.calls[0]
    assert system == SYSTEM_PROMPT
    assert user.startswith("<fonte>") and user.endswith("</fonte>")


def test_invented_number_is_rejected_then_retried():
    bad = answer(pontos=["Valor de 2.000 €", "Candidatura até 30 de setembro"])
    provider, loaded = llm(bad, answer())
    assert write_whatsapp(loaded, "Bolsa de mérito", SOURCE) is not None
    assert len(provider.calls) == 2


@pytest.mark.parametrize(
    "bad",
    [
        "isto não é JSON",
        answer(emoji="🚀"),
        answer(pontos=["só um ponto"]),
        answer(pontos=["a" * 161, "b"]),
        answer(titulo="x" * 91),
        answer(pontos=[]),
    ],
)
def test_two_invalid_answers_fall_back_to_rules(bad):
    provider, loaded = llm(bad, bad)
    assert write_whatsapp(loaded, "Bolsa de mérito", SOURCE) is None
    assert len(provider.calls) == 2


def test_provider_error_falls_back_without_retry():
    provider, loaded = llm(LLMError("HTTP 500"))
    assert write_whatsapp(loaded, "Bolsa", SOURCE) is None
    assert len(provider.calls) == 1


def test_no_provider_means_rules_only():
    assert write_whatsapp(None, "Bolsa", SOURCE) is None


def test_source_is_truncated_and_delimited():
    provider, loaded = llm(answer())
    write_whatsapp(loaded, "Bolsa", SOURCE + " x" * 5000)
    _, _, user = provider.calls[0]
    assert len(user) < 4100


def test_load_provider_uses_free_github_models_by_default(tmp_path):
    from tensdireito_content_engine.llm import AnthropicProvider, GitHubModelsProvider

    config = Path(__file__).resolve().parents[1] / "config"
    assert load_provider(config, {}) is None
    assert load_provider(tmp_path, {"GITHUB_TOKEN": "t"}) is None
    loaded = load_provider(config, {"GITHUB_TOKEN": "t"})
    assert isinstance(loaded.provider, GitHubModelsProvider)
    assert loaded.tasks["whatsapp_draft"].model == "openai/gpt-4.1-mini"

    (tmp_path / "llm.yaml").write_text(
        "provider: anthropic\ntasks:\n  whatsapp_draft:\n    model: claude-haiku-5-5\n",
        encoding="utf-8",
    )
    assert load_provider(tmp_path, {"GITHUB_TOKEN": "t"}) is None
    assert isinstance(
        load_provider(tmp_path, {"ANTHROPIC_API_KEY": "k"}).provider, AnthropicProvider
    )


def test_github_models_request_and_response(monkeypatch):
    from tensdireito_content_engine import llm as llm_module

    sent = {}

    def fake_post(url, headers, payload):
        sent.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": "olá"}}]}

    monkeypatch.setattr(llm_module, "_post_json", fake_post)
    provider = llm_module.GitHubModelsProvider(token="tok")
    assert provider.complete(TASK, "sistema", "utilizador") == "olá"
    assert sent["url"] == "https://models.github.ai/inference/chat/completions"
    assert sent["headers"]["authorization"] == "Bearer tok"
    assert [m["role"] for m in sent["payload"]["messages"]] == ["system", "user"]


def test_github_models_empty_answer_is_an_error(monkeypatch):
    from tensdireito_content_engine import llm as llm_module

    monkeypatch.setattr(llm_module, "_post_json", lambda *a: {"choices": []})
    with pytest.raises(LLMError):
        llm_module.GitHubModelsProvider(token="t").complete(TASK, "s", "u")


def test_llm_check_reports_disabled_ok_and_error(tmp_path, monkeypatch, capsys):
    from tensdireito_content_engine import cli
    from tensdireito_content_engine import llm as llm_module

    config = Path(__file__).resolve().parents[1] / "config"
    assert cli.llm_check(config, {})[0].startswith("llm: desactivado")

    monkeypatch.setattr(
        llm_module, "_post_json", lambda *a: {"choices": [{"message": {"content": "OK"}}]}
    )
    assert cli.llm_check(config, {"GITHUB_TOKEN": "t"}) == [
        "llm: OK — github_models openai/gpt-4.1-mini (whatsapp_draft)"
    ]

    def fail(*args):
        raise LLMError("HTTP 429")

    monkeypatch.setattr(llm_module, "_post_json", fail)
    assert cli.llm_check(config, {"GITHUB_TOKEN": "t"})[0].endswith("HTTP 429")
    monkeypatch.setattr(cli, "default_registry", lambda: None)
    assert cli.main(["--config", str(config), "llm", "check"]) == 0
    capsys.readouterr()
