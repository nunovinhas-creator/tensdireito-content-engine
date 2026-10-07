"""Normalização de `published_at` (CONTENT_PIPELINE.md etapa 2, DEC-021).

Regra documentada: normalizar para UTC; se não for possível, deixar nulo — nunca
inventar uma data. Só uma data/hora ISO 8601 com fuso explícito é convertida. Uma
data sem hora, uma data/hora sem fuso ou outro formato dão `None`: não se assume o fuso
local nem se acrescenta precisão que a fonte não tem (pendente D13 em ROADMAP.md).
O valor original continua em `RawItem.published_at_raw`.
"""

from datetime import UTC, datetime


def normalize_published_at(value: str | None) -> datetime | None:
    """Converte `published_at_raw` em `datetime` UTC, ou `None` se não for possível."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"esperado str ou None, recebido {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:  # inclui datas sem hora
        return None
    return parsed.astimezone(UTC)
