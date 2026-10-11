"""Fornecedores de modelos de linguagem (AI_RULES.md §7; DEC-059, DEC-062).

`LLMProvider` é a interface usada pelo resto do sistema. Implementações, só com a
biblioteca padrão (sem SDK):
- `OpenAICompatibleProvider`: qualquer API `chat/completions` compatível com OpenAI
  (Google Gemini e Groq têm planos gratuitos com chave própria);
- `AnthropicProvider`: API paga da Anthropic;
- `ChainProvider`: tenta os fornecedores por ordem; o primeiro que responder ganha.

`config/llm.yaml` lista os fornecedores, cada um com a variável de ambiente da chave.
Só entram na cadeia os que têm chave definida; sem nenhum, `load_provider` devolve
`None` e o sistema usa só regras.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from tensdireito_content_engine import __version__

# DEC-062: alguns fornecedores (p. ex. Groq, atrás da Cloudflare) recusam com 403 o
# User-Agent por defeito do urllib.
USER_AGENT = f"tensdireito-content-engine/{__version__}"
LLM_FILENAME = "llm.yaml"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT_SECONDS = 30.0


class LLMError(Exception):
    """Falha de chamada ao modelo; quem chama faz fallback para regras."""


@dataclass(frozen=True, slots=True)
class TaskConfig:
    temperature: float
    max_tokens: int
    prompt_id: str
    model: str = ""


class LLMProvider(Protocol):
    name: str

    def complete(self, task: TaskConfig, system: str, user: str) -> str: ...


def _post_json(url: str, headers: Mapping[str, str], payload: dict) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": USER_AGENT,
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise LLMError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMError(f"erro de ligação: {type(exc).__name__}") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise LLMError(f"resposta não é JSON (Content-Type: {content_type or '—'})") from None


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProvider:
    name: str
    url: str
    api_key: str
    model: str
    extra: Mapping[str, Any] = field(default_factory=dict)

    def complete(self, task: TaskConfig, system: str, user: str) -> str:
        body = _post_json(
            self.url,
            {"authorization": f"Bearer {self.api_key}"},
            {
                "model": self.model,
                "max_tokens": task.max_tokens,
                "temperature": task.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **self.extra,
            },
        )
        choices = body.get("choices") if isinstance(body, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise LLMError("resposta sem texto")
        return text


@dataclass(frozen=True, slots=True)
class AnthropicProvider:
    api_key: str
    model: str
    name: str = "anthropic"
    url: str = "https://api.anthropic.com/v1/messages"

    def complete(self, task: TaskConfig, system: str, user: str) -> str:
        body = _post_json(
            self.url,
            {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION},
            {
                "model": self.model,
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
class ChainProvider:
    """Tenta cada fornecedor por ordem; falha só se todos falharem."""

    providers: Sequence[LLMProvider]

    @property
    def name(self) -> str:
        return "+".join(provider.name for provider in self.providers)

    def complete(self, task: TaskConfig, system: str, user: str) -> str:
        errors = []
        for provider in self.providers:
            try:
                return provider.complete(task, system, user)
            except LLMError as exc:
                errors.append(f"{provider.name}: {exc}")
        raise LLMError("; ".join(errors) or "sem fornecedores")


@dataclass(frozen=True, slots=True)
class LoadedLLM:
    provider: LLMProvider
    tasks: Mapping[str, TaskConfig]


def load_provider(config_dir: Path, environ: Mapping[str, str]) -> LoadedLLM | None:
    """Cadeia dos fornecedores com chave definida, ou `None` se não houver nenhum."""
    path = Path(config_dir) / LLM_FILENAME
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    providers: list[LLMProvider] = []
    for entry in data.get("providers") or ():
        if not isinstance(entry, dict):
            continue
        key = (environ.get(str(entry.get("key_env", ""))) or "").strip()
        model = str(entry.get("model") or "")
        if not key or not model:
            continue
        kind = entry.get("type", "openai_compatible")
        if kind == "anthropic":
            providers.append(AnthropicProvider(api_key=key, model=model))
        elif kind == "openai_compatible" and str(entry.get("url", "")).startswith("https://"):
            providers.append(
                OpenAICompatibleProvider(
                    name=str(entry.get("name") or "openai_compatible"),
                    url=str(entry["url"]),
                    api_key=key,
                    model=model,
                    extra=dict(entry.get("extra") or {}),
                )
            )
    tasks = {
        str(name): TaskConfig(
            temperature=float(task.get("temperature", 0)),
            max_tokens=int(task.get("max_tokens", 512)),
            prompt_id=str(task.get("prompt_id", name)),
            model="/".join(getattr(p, "model", "") for p in providers),
        )
        for name, task in (data.get("tasks") or {}).items()
        if isinstance(task, dict)
    }
    if not providers or not tasks:
        return None
    provider = providers[0] if len(providers) == 1 else ChainProvider(tuple(providers))
    return LoadedLLM(provider=provider, tasks=tasks)
