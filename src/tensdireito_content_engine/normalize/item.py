"""`NormalizedItem` — representação mecânica normalizada de um `RawItem` (DEC-021).

Intermédio da etapa NORMALIZE: contém apenas os campos de `source_document` que se
obtêm por transformação mecânica (`title`, `text`, `published_at`). Os restantes
(`canonical_url`, `language`, `source_tier`, `document_kind`, classificação, extracção
de texto de HTML) exigem regras ainda não definidas ou interpretação, e ficam para as
unidades correspondentes. Não é um `SourceDocument`, não é um `Event` e não é evidência.
"""

from dataclasses import dataclass
from datetime import datetime

from tensdireito_content_engine.domain.raw_item import RawItem
from tensdireito_content_engine.normalize.dates import normalize_published_at
from tensdireito_content_engine.normalize.text import normalize_text, normalize_title


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizedItem:
    raw_item: RawItem  # original preservado, intacto, para auditoria
    title: str
    text: str
    published_at: datetime | None  # UTC; nulo se desconhecida (nunca inventada)


def normalize_raw_item(raw_item: RawItem) -> NormalizedItem:
    """Normaliza mecanicamente um `RawItem`. Determinística e sem efeitos laterais."""
    if not isinstance(raw_item, RawItem):
        raise TypeError(f"esperado RawItem, recebido {type(raw_item).__name__}")
    return NormalizedItem(
        raw_item=raw_item,
        title=normalize_title(raw_item.title),
        text=normalize_text(raw_item.raw_content),
        published_at=normalize_published_at(raw_item.published_at_raw),
    )
