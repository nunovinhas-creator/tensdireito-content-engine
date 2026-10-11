"""Fornecedor de modelos de linguagem (AI_RULES.md §7; DEC-059, DEC-060).

`LLMProvider` é a interface usada pelo resto do sistema. Implementações, só com a
biblioteca padrão (sem SDK):
- `GitHubModelsProvider` (por defeito, gratuito): API compatível com OpenAI em
  models.github.ai, autenticada com o `GITHUB_TOKEN` do workflow (`models: read`);
- `AnthropicProvider`: API paga da Anthropic, com `ANTHROPIC_API_KEY`.
A configuração por tarefa está em `config/llm.yaml`. Sem token/chave ou sem
configuração, `load_provider` devolve `None` e o sistema usa só regras.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

LLM_FILENAME = "llm.yaml"
API_KEY_ENV = "ANTHROPIC_API_KEY"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT_SECONDS = 30.0


class LLMError(Exception):
    """Falha de chamada ao modelo; quem chama faz fallback para regras."""


@dataclass(frozen=True, slots=True)
class TaskConfig:
    model: str
    temperature: float
    max_tokens: int
    prompt_id: str


class LLMProvider(Protocol):
    name: str

    def complete(self, task: TaskConfig, system: str, user: str) -> str: ...


def _post_json(url: str, headers: Mapping[str, str], payload: dict) -> object:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise LLMError(f"erro de ligação: {type(exc).__name__}") from None


@dataclass(frozen=True, slots=True)
class GitHubModelsProvider:
    token: str
    name: str = "github_models"
    url: str = GITHUB_MODELS_URL

    def complete(self, task: TaskConfig, system: str, user: str) -> str:
        body = _post_json(
            self.url,
            {"authorization": f"Bearer {self.token}", "accept": "application/json"},
            {
                "model": task.model,
                "max_tokens": task.max_tokens,
                "temperature": task.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        choices = body.get("choices") if isinstance(body, dict) else None
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise LLMError("resposta sem texto")
        return text


@dataclass(frozen=True, slots=True)
class AnthropicProvider:
    api_key: str
    name: str = "anthropic"
    url: str = ANTHROPIC_URL

    def complete(self, task: TaskConfig, system: str, user: str) -> str:
        body = _post_json(
            self.url,
            {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION},
            {
                "model": task.model,
                "max_tokens": task.max_tokens,
                "temperature": task.temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        blocks = body.get("content") if isinstance(body, dict) else None
        text = "".join(
            block.get("text", "")
            for block in blocks or ()
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if not text.strip():
            raise LLMError("resposta sem texto")
        return text


@dataclass(frozen=True, slots=True)
class LoadedLLM:
    provider: LLMProvider
    tasks: Mapping[str, TaskConfig]


def load_provider(config_dir: Path, environ: Mapping[str, str]) -> LoadedLLM | None:
    """Fornecedor e tarefas de `config/llm.yaml`, ou `None` sem credencial ou ficheiro."""
    path = Path(config_dir) / LLM_FILENAME
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    provider: LLMProvider
    if data.get("provider") == "github_models":
        token = (environ.get(GITHUB_TOKEN_ENV) or "").strip()
        if not token:
            return None
        provider = GitHubModelsProvider(token=token)
    elif data.get("provider") == "anthropic":
        api_key = (environ.get(API_KEY_ENV) or "").strip()
        if not api_key:
            return None
        provider = AnthropicProvider(api_key=api_key)
    else:
        return None
    tasks = {
        str(name): TaskConfig(
            model=str(task["model"]),
            temperature=float(task.get("temperature", 0)),
            max_tokens=int(task.get("max_tokens", 512)),
            prompt_id=str(task.get("prompt_id", name)),
        )
        for name, task in (data.get("tasks") or {}).items()
        if isinstance(task, dict) and task.get("model")
    }
    if not tasks:
        return None
    return LoadedLLM(provider=provider, tasks=tasks)
