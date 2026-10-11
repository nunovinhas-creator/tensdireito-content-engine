"""Fornecedor de modelos de linguagem (AI_RULES.md §7; DEC-059).

`LLMProvider` é a interface usada pelo resto do sistema; `AnthropicProvider` é a
única implementação, com a biblioteca padrão (sem SDK). A configuração por tarefa
está em `config/llm.yaml`; a chave vem da variável `ANTHROPIC_API_KEY`. Sem chave
ou sem configuração, `load_provider` devolve `None` e o sistema usa só regras.
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
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
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


@dataclass(frozen=True, slots=True)
class AnthropicProvider:
    api_key: str
    name: str = "anthropic"
    url: str = ANTHROPIC_URL

    def complete(self, task: TaskConfig, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": task.model,
                "max_tokens": task.max_tokens,
                "temperature": task.temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMError(f"HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError(f"erro de ligação: {type(exc).__name__}") from None
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
    """Fornecedor e tarefas de `config/llm.yaml`, ou `None` sem chave ou sem ficheiro."""
    api_key = (environ.get(API_KEY_ENV) or "").strip()
    path = Path(config_dir) / LLM_FILENAME
    if not api_key or not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("provider") != "anthropic":
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
    return LoadedLLM(provider=AnthropicProvider(api_key=api_key), tasks=tasks)
