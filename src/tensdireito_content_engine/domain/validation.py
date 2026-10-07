"""Verificações locais partilhadas pelas entidades de domínio."""

from datetime import datetime, timedelta
from enum import Enum


class DomainValidationError(ValueError):
    """Dados que violam um invariante do domínio."""


def require_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field} é obrigatório e não pode ser vazio")


def optional_text(value: object, field: str) -> None:
    if value is not None:
        require_text(value, field)


def require_id(value: object, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DomainValidationError(f"{field} tem de ser um inteiro positivo")


def optional_id(value: object, field: str) -> None:
    if value is not None:
        require_id(value, field)


def require_member(value: object, enum_type: type[Enum], field: str) -> None:
    if not isinstance(value, enum_type):
        raise DomainValidationError(f"{field} tem de ser {enum_type.__name__}: {value!r}")


def require_utc(value: object, field: str) -> None:
    if not isinstance(value, datetime):
        raise DomainValidationError(f"{field} tem de ser datetime")
    if value.utcoffset() != timedelta(0):
        raise DomainValidationError(f"{field} tem de estar em UTC")


def optional_utc(value: object, field: str) -> None:
    if value is not None:
        require_utc(value, field)


def require_text_tuple(value: object, field: str) -> None:
    if not isinstance(value, tuple):
        raise DomainValidationError(f"{field} tem de ser tuple")
    for item in value:
        require_text(item, field)
    if len(set(value)) != len(value):
        raise DomainValidationError(f"{field} não pode ter valores repetidos")


def require_human_actor(value: object, field: str) -> None:
    """Uma pessoa identificada; nunca um modelo de IA (DEC-014)."""
    require_text(value, field)
    if str(value).strip().lower().startswith("llm:"):
        raise DomainValidationError(f"{field} tem de ser uma pessoa, não um modelo: {value!r}")


def optional_human_actor(value: object, field: str) -> None:
    if value is not None:
        require_human_actor(value, field)


def require_origin(value: object, field: str) -> None:
    """Origem automática ou humana: `rules`, `human` ou `llm:<prompt_id>`."""
    require_text(value, field)
    text = str(value)
    if text in ("rules", "human"):
        return
    if text.startswith("llm:") and text.removeprefix("llm:").strip():
        return
    raise DomainValidationError(f"{field} tem de ser rules, human ou llm:<prompt_id>: {value!r}")
