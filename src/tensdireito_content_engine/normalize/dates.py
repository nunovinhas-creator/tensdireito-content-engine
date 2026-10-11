"""Normalização de `published_at` (CONTENT_PIPELINE.md etapa 2, DEC-021).

Regra documentada: normalizar para UTC; se não for possível, deixar nulo — nunca
inventar uma data. São convertidas datas/horas ISO 8601 com fuso explícito e datas
RFC 822 (o formato de `pubDate` em RSS 2.0) com fuso explícito (DEC-057). Uma data sem
hora, uma data/hora sem fuso (incluindo `-0000`) ou outro formato dão `None`: não se
assume o fuso local nem se acrescenta precisão que a fonte não tem.
O valor original continua em `RawItem.published_at_raw`.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def normalize_published_at(value: str | None) -> datetime | None:
    """Converte `published_at_raw` em `datetime` UTC, ou `None` se não for possível."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"esperado str ou None, recebido {type(value).__name__}")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = _rfc822(text)
    if parsed is None or parsed.tzinfo is None:  # inclui datas sem hora
        return None
    return parsed.astimezone(UTC)


def _rfc822(text: str) -> datetime | None:
    """`Fri, 09 Oct 2026 09:00:00 GMT` ou `+0100`; `-0000` (fuso desconhecido) dá `None`."""
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
