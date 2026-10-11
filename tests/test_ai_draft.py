"""Redacção assistida por IA: validação, fallback e fornecedor (DEC-059)."""

import json
from pathlib import Path

import pytest

from tensdireito_content_engine.ai_draft import SYSTEM_PROMPT, write_whatsapp
from tensdireito_content_engine.llm import LLMError, LoadedLLM, TaskConfig, load_provider

TASK = TaskConfig(temperature=0.3, max_tokens=600, prompt_id="llm:test", model="m")
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


CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_load_provider_uses_only_providers_with_keys(tmp_path):
    from tensdireito_content_engine.llm import ChainProvider, OpenAICompatibleProvider

    assert load_provider(CONFIG, {}) is None
    assert load_provider(tmp_path, {"GEMINI_API_KEY": "g"}) is None

    only_groq = load_provider(CONFIG, {"GROQ_API_KEY": "q"})
    assert isinstance(only_groq.provider, OpenAICompatibleProvider)
    assert only_groq.provider.name == "groq"
    assert only_groq.provider.url == "https://api.groq.com/openai/v1/chat/completions"

    both = load_provider(CONFIG, {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q"})
    assert isinstance(both.provider, ChainProvider)
    assert [p.name for p in both.provider.providers] == ["gemini", "groq"]
    assert both.tasks["whatsapp_draft"].max_tokens == 2000


def test_anthropic_provider_can_be_configured(tmp_path):
    from tensdireito_content_engine.llm import AnthropicProvider

    (tmp_path / "llm.yaml").write_text(
        "providers:\n  - name: anthropic\n    type: anthropic\n    key_env: K\n"
        "    model: claude-haiku-5-5\ntasks:\n  whatsapp_draft: {}\n",
        encoding="utf-8",
    )
    assert load_provider(tmp_path, {}) is None
    assert isinstance(load_provider(tmp_path, {"K": "k"}).provider, AnthropicProvider)


def test_openai_compatible_request_and_response(monkeypatch):
    from tensdireito_content_engine import llm as llm_module

    sent = {}

    def fake_post(url, headers, payload):
        sent.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": "olá"}}]}

    monkeypatch.setattr(llm_module, "_post_json", fake_post)
    provider = llm_module.OpenAICompatibleProvider(
        name="x",
        url="https://api.example/v1/chat/completions",
        api_key="tok",
        model="m1",
        extra={"reasoning_effort": "low"},
    )
    assert provider.complete(TASK, "sistema", "utilizador") == "olá"
    assert sent["headers"]["authorization"] == "Bearer tok"
    assert sent["payload"]["model"] == "m1"
    assert sent["payload"]["reasoning_effort"] == "low"
    assert [m["role"] for m in sent["payload"]["messages"]] == ["system", "user"]


def test_empty_answer_is_an_error(monkeypatch):
    from tensdireito_content_engine import llm as llm_module

    monkeypatch.setattr(llm_module, "_post_json", lambda *a: {"choices": []})
    provider = llm_module.OpenAICompatibleProvider(
        name="x", url="https://a", api_key="t", model="m"
    )
    with pytest.raises(LLMError):
        provider.complete(TASK, "s", "u")


def test_chain_falls_back_to_the_next_provider():
    from tensdireito_content_engine.llm import ChainProvider

    first, second = FakeProvider(LLMError("HTTP 429")), FakeProvider("resposta")
    first.name, second.name = "a", "b"
    assert ChainProvider((first, second)).complete(TASK, "s", "u") == "resposta"
    failing = ChainProvider((FakeProvider(LLMError("x")),))
    with pytest.raises(LLMError):
        failing.complete(TASK, "s", "u")


def test_llm_check_reports_each_provider(monkeypatch, capsys):
    from tensdireito_content_engine import cli
    from tensdireito_content_engine import llm as llm_module

    assert cli.llm_check(CONFIG, {})[0].startswith("llm: desactivado")

    def fake_post(url, headers, payload):
        if "groq" in url:
            raise LLMError("HTTP 429")
        return {"choices": [{"message": {"content": "OK"}}]}

    monkeypatch.setattr(llm_module, "_post_json", fake_post)
    lines = cli.llm_check(CONFIG, {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q"})
    assert lines == [
        "llm: OK — gemini gemini-3.5-flash-lite (whatsapp_draft)",
        "llm: ERRO — groq openai/gpt-oss-120b (whatsapp_draft): HTTP 429",
    ]
    assert cli.main(["--config", str(CONFIG), "llm", "check"]) == 0
    capsys.readouterr()
