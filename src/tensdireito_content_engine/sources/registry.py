"""Registo de fontes `config/sources.yaml` → `SourceRegistry` e `SourceEndpoint` (M2.5).

O YAML é a fonte de verdade (DATA_MODEL.md §2.1); o formato é o de SOURCES.md §4.
Regras aplicadas — só as documentadas:

- esquema fechado (DEC-023): raiz em lista; cada fonte e cada endpoint é um mapeamento
  só com as chaves do formato, campos obrigatórios presentes e tipos YAML correctos;
- IDs únicos (fontes entre si; endpoints entre si, em todo o registo);
- tiers e restantes enumerações válidos;
- invariantes de domínio do M2.2 (ex.: fonte `CANDIDATE` sem `domains`; `VALIDATED` e
  `ACTIVE` com `validated_at` e `validated_by`);
- endpoints `ACTIVE` exigem `url` e `validated_at` (SOURCES.md §4);
- endpoints `ACTIVE` exigem fonte `VALIDATED` (DEC-035), avaliado só quando o
  `registry_status` da fonte foi lido sem erro.

Representação das enumerações (DEC-024): a do formato documentado. Estados em maiúsculas
(`CANDIDATE`), convertidos para o valor interno em minúsculas (DATA_MODEL.md, convenção
de nomes); `entity_type`, `endpoint_type` e `tier` tal como o valor interno.

`validated_at` só é aceite como data/hora ISO 8601 com fuso explícito, convertida para
UTC; nenhum fuso é assumido. `fetch` é verificado como mapeamento, mas não tem
correspondência nos modelos de domínio do M2.2 e não é convertido.

Apenas leitura local: sem rede, sem verificação de URLs e sem escrita.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from tensdireito_content_engine.domain import (
    DomainValidationError,
    EndpointStatus,
    EndpointType,
    EntityType,
    RegistryStatus,
    SourceEndpoint,
    SourceRegistry,
    SourceTier,
)
from tensdireito_content_engine.sources.yaml_loader import YamlLoadError, load_yaml

SOURCE_REQUIRED = ("id", "name", "entity_type", "tier")
SOURCE_OPTIONAL = (
    "categories",
    "domains",
    "registry_status",
    "validated_at",
    "validated_by",
    "notes",
    "endpoints",
)
ENDPOINT_REQUIRED = ("id", "endpoint_type")
ENDPOINT_OPTIONAL = (
    "url",
    "endpoint_status",
    "fetch",
    "validated_at",
    "validated_by",
    "redirect_hosts",
    "redirect_is_throttle",
)


class SourceRegistryError(ValueError):
    """O registo de fontes não é válido. `errors` lista todos os problemas encontrados."""

    def __init__(self, errors: list[str] | tuple[str, ...]) -> None:
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True, slots=True)
class LoadedSources:
    """Conteúdo válido do registo, pela ordem do ficheiro."""

    sources: tuple[SourceRegistry, ...]
    endpoints: tuple[SourceEndpoint, ...]


def load_sources(path: Path) -> LoadedSources:
    """Lê e valida `config/sources.yaml`. Levanta `SourceRegistryError` se for inválido."""
    try:
        data = load_yaml(path)
    except YamlLoadError as exc:
        raise SourceRegistryError([str(exc)]) from None
    return parse_sources(data)


def parse_sources(data: object) -> LoadedSources:
    """Converte o conteúdo já interpretado do YAML. Determinista para a mesma entrada."""
    if not isinstance(data, list):
        raise SourceRegistryError(
            [f"a raiz do registo tem de ser uma lista de fontes, recebido {_kind(data)}"]
        )

    errors: list[str] = []
    sources: list[SourceRegistry] = []
    endpoints: list[SourceEndpoint] = []
    source_ids: dict[str, str] = {}
    endpoint_ids: dict[str, str] = {}

    for index, item in enumerate(data):
        where = _where(f"sources[{index}]", item)
        if not isinstance(item, dict):
            errors.append(f"{where}: cada fonte tem de ser um mapeamento, recebido {_kind(item)}")
            continue
        _check_unique(item, where, source_ids, "fonte", errors)
        source = _parse_source(item, where, errors)
        if source is not None:
            sources.append(source)
        source_status = _source_status(item)

        raw_endpoints = item.get("endpoints", [])
        if not isinstance(raw_endpoints, list):
            errors.append(
                f"{where}: endpoints tem de ser uma lista, recebido {_kind(raw_endpoints)}"
            )
            continue
        for ep_index, ep_item in enumerate(raw_endpoints):
            ep_where = _where(f"sources[{index}].endpoints[{ep_index}]", ep_item)
            if not isinstance(ep_item, dict):
                errors.append(
                    f"{ep_where}: cada endpoint tem de ser um mapeamento, recebido {_kind(ep_item)}"
                )
                continue
            _check_unique(ep_item, ep_where, endpoint_ids, "endpoint", errors)
            endpoint = _parse_endpoint(ep_item, item.get("id"), source_status, ep_where, errors)
            if endpoint is not None:
                endpoints.append(endpoint)

    if errors:
        raise SourceRegistryError(errors)
    return LoadedSources(sources=tuple(sources), endpoints=tuple(endpoints))


def _parse_source(item: dict, where: str, errors: list[str]) -> SourceRegistry | None:
    problems = _check_keys(item, SOURCE_REQUIRED, SOURCE_OPTIONAL)
    fields: dict[str, object] = {}
    for key in ("id", "name"):
        _put(fields, key, _text(item, key, problems))
    _put(fields, "notes", _text(item, "notes", problems))
    _put(fields, "validated_by", _text(item, "validated_by", problems))
    _put(fields, "entity_type", _by_value(item, "entity_type", EntityType, problems))
    _put(fields, "tier", _by_value(item, "tier", SourceTier, problems))
    _put(fields, "registry_status", _by_name(item, "registry_status", RegistryStatus, problems))
    _put(fields, "categories", _text_list(item, "categories", problems))
    _put(fields, "domains", _text_list(item, "domains", problems))
    _put(fields, "validated_at", _timestamp(item, "validated_at", problems))

    if problems:
        errors.extend(f"{where}: {problem}" for problem in problems)
        return None
    try:
        return SourceRegistry(**fields)
    except DomainValidationError as exc:
        errors.append(f"{where}: {exc}")
        return None


def _source_status(item: dict) -> RegistryStatus | None:
    """Estado da fonte para DEC-035; `None` se o próprio estado for inválido (já reportado)."""
    if "registry_status" not in item:
        return _DEFAULT_REGISTRY_STATUS
    status = _by_name(item, "registry_status", RegistryStatus, [])
    return None if status is _MISSING else status


def _parse_endpoint(
    item: dict,
    source_id: object,
    source_status: RegistryStatus | None,
    where: str,
    errors: list[str],
) -> SourceEndpoint | None:
    problems = _check_keys(item, ENDPOINT_REQUIRED, ENDPOINT_OPTIONAL)
    fields: dict[str, object] = {"source_id": source_id}
    _put(fields, "id", _text(item, "id", problems))
    _put(fields, "url", _text(item, "url", problems))
    _put(fields, "validated_by", _text(item, "validated_by", problems))
    _put(fields, "endpoint_type", _by_value(item, "endpoint_type", EndpointType, problems))
    _put(fields, "endpoint_status", _by_name(item, "endpoint_status", EndpointStatus, problems))
    _put(fields, "validated_at", _timestamp(item, "validated_at", problems))
    _put(fields, "redirect_hosts", _text_list(item, "redirect_hosts", problems))
    _put(fields, "redirect_is_throttle", _boolean(item, "redirect_is_throttle", problems))
    fetch = item.get("fetch")
    if fetch is not None and not isinstance(fetch, dict):
        problems.append(f"fetch tem de ser um mapeamento, recebido {_kind(fetch)}")

    if fields.get("endpoint_status") is EndpointStatus.ACTIVE:
        # SOURCES.md §4: recusa endpoints ACTIVE sem url e sem validated_at.
        if fields.get("url") is None:
            problems.append("um endpoint ACTIVE exige url")
        if fields.get("validated_at") is None:
            problems.append("um endpoint ACTIVE exige validated_at")
        # DEC-035: só com o estado da fonte lido sem erro; nenhuma outra regra entre estados.
        if source_status is not None and source_status is not RegistryStatus.VALIDATED:
            problems.append(
                "um endpoint ACTIVE exige fonte VALIDATED "
                f"(fonte {source_id}: {source_status.name})"
            )

    if problems:
        errors.extend(f"{where}: {problem}" for problem in problems)
        return None
    try:
        return SourceEndpoint(**fields)
    except DomainValidationError as exc:
        errors.append(f"{where}: {exc}")
        return None


def _check_keys(item: dict, required: tuple[str, ...], optional: tuple[str, ...]) -> list[str]:
    problems = [f"campo obrigatório em falta: {key}" for key in required if key not in item]
    allowed = set(required) | set(optional)
    unknown = sorted(str(key) for key in item if key not in allowed)
    problems.extend(f"campo desconhecido: {key}" for key in unknown)
    return problems


def _check_unique(
    item: dict, where: str, seen: dict[str, str], label: str, errors: list[str]
) -> None:
    value = item.get("id")
    if not isinstance(value, str):
        return
    if value in seen:
        errors.append(f"{where}: id de {label} repetido (já usado em {seen[value]}): {value}")
    else:
        seen[value] = where


def _put(fields: dict[str, object], key: str, value: object) -> None:
    if value is not _MISSING:
        fields[key] = value


class _Missing:
    pass


_MISSING = _Missing()

# Valor por omissão de `SourceRegistry.registry_status` (M2.2), quando o campo falta no YAML.
_DEFAULT_REGISTRY_STATUS = RegistryStatus.CANDIDATE


def _text(item: Mapping, key: str, problems: list[str]) -> object:
    """Texto ou nulo; o domínio decide se pode ser nulo ou vazio."""
    if key not in item:
        return _MISSING
    value = item[key]
    if value is not None and not isinstance(value, str):
        problems.append(f"{key} tem de ser texto, recebido {_kind(value)}")
        return _MISSING
    return value


def _text_list(item: Mapping, key: str, problems: list[str]) -> object:
    if key not in item:
        return _MISSING
    value = item[key]
    if not isinstance(value, list):
        problems.append(f"{key} tem de ser uma lista, recebido {_kind(value)}")
        return _MISSING
    bad = [element for element in value if not isinstance(element, str)]
    if bad:
        problems.append(f"{key} só pode conter texto, recebido {_kind(bad[0])}")
        return _MISSING
    return tuple(value)


def _boolean(item: Mapping, key: str, problems: list[str]) -> object:
    if key not in item:
        return _MISSING
    value = item[key]
    if not isinstance(value, bool):
        problems.append(f"{key} tem de ser booleano, recebido {_kind(value)}")
        return _MISSING
    return value


def _by_value(item: Mapping, key: str, enum_type: type[Enum], problems: list[str]) -> object:
    """Enumeração escrita na documentação tal como o valor interno (ex.: `html_page`, `T1`)."""
    if key not in item:
        return _MISSING
    value = item[key]
    allowed = [member.value for member in enum_type]
    if isinstance(value, str) and value in allowed:
        return enum_type(value)
    problems.append(f"{key} inválido: {value!r} (aceites: {' | '.join(allowed)})")
    return _MISSING


def _by_name(item: Mapping, key: str, enum_type: type[Enum], problems: list[str]) -> object:
    """Estado escrito na documentação em maiúsculas (ex.: `CANDIDATE` → `candidate`)."""
    if key not in item:
        return _MISSING
    value = item[key]
    allowed = [member.name for member in enum_type]
    if isinstance(value, str) and value in allowed:
        return enum_type[value]
    problems.append(f"{key} inválido: {value!r} (aceites: {' | '.join(allowed)})")
    return _MISSING


def _timestamp(item: Mapping, key: str, problems: list[str]) -> object:
    """ISO 8601 com fuso explícito → UTC. Sem fuso não é aceite: nenhum fuso é assumido."""
    if key not in item:
        return _MISSING
    value = item[key]
    if value is None:
        return None
    if not isinstance(value, str):
        problems.append(f"{key} tem de ser texto ISO 8601, recebido {_kind(value)}")
        return _MISSING
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        problems.append(f"{key} não é uma data/hora ISO 8601: {value!r}")
        return _MISSING
    if parsed.tzinfo is None:
        problems.append(f"{key} tem de indicar o fuso horário explicitamente: {value!r}")
        return _MISSING
    return parsed.astimezone(UTC)


def _where(path: str, item: object) -> str:
    if isinstance(item, dict) and isinstance(item.get("id"), str):
        return f"{path} (id={item['id']})"
    return path


def _kind(value: object) -> str:
    names = {
        type(None): "nulo",
        bool: "booleano",
        int: "inteiro",
        float: "número",
        str: "texto",
        list: "lista",
        dict: "mapeamento",
    }
    return names.get(type(value), type(value).__name__)
