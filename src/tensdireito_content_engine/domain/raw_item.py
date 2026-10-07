"""`RawItem` — captura bruta de um documento, Nível 1 (DATA_MODEL.md §2.1, ARCHITECTURE.md §4).

Material tal como recebido de uma fonte, antes da normalização. Preserva o original
para auditoria: nenhum campo é limpo ou reinterpretado aqui. Não é um `Event`, não é
evidência e não tem estado editorial nem de verificação.

`id` e `created_in_run` pertencem à futura camada de persistência e não estão aqui.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from tensdireito_content_engine.domain.validation import (
    optional_text,
    require_text,
    require_utc,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RawItem:
    url: str  # tal como obtido
    title: str
    raw_content: str  # HTML/XML/texto bruto
    fetched_at: datetime
    source_endpoint_id: str | None = None  # nulo para pistas manuais sem fonte registada
    external_id: str | None = None  # GUID do feed, se existir
    published_at_raw: str | None = None  # data tal como aparece na fonte
    manual_note: str | None = None  # apenas para entradas manuais

    def __post_init__(self) -> None:
        require_text(self.url, "url")
        require_text(self.title, "title")
        require_text(self.raw_content, "raw_content")
        require_utc(self.fetched_at, "fetched_at")
        optional_text(self.source_endpoint_id, "source_endpoint_id")
        optional_text(self.external_id, "external_id")
        optional_text(self.published_at_raw, "published_at_raw")
        optional_text(self.manual_note, "manual_note")

    @property
    def content_hash(self) -> str:
        """SHA-256 (hex) do conteúdo bruto, sem qualquer normalização (DATA_MODEL.md §2.1)."""
        return hashlib.sha256(self.raw_content.encode("utf-8")).hexdigest()
