"""Etapa NORMALIZE: normalização mecânica e identidade de conteúdo (DEC-021).

RawItem → NormalizedItem → fingerprint. Sem rede, sem persistência, sem IA e sem
lógica editorial; a deduplicação e o agrupamento em `Event` pertencem a etapas futuras.
"""

from tensdireito_content_engine.normalize.dates import normalize_published_at
from tensdireito_content_engine.normalize.identity import fingerprint
from tensdireito_content_engine.normalize.item import NormalizedItem, normalize_raw_item
from tensdireito_content_engine.normalize.text import normalize_text, normalize_title

__all__ = [
    "NormalizedItem",
    "fingerprint",
    "normalize_published_at",
    "normalize_raw_item",
    "normalize_text",
    "normalize_title",
]
