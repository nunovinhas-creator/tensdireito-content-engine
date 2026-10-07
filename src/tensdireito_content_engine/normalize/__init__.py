"""Etapa NORMALIZE: normalização mecânica e identidade de conteúdo (DEC-021).

RawItem → NormalizedItem → fingerprint → deduplicação exacta (M2.4, DEC-022). Sem rede,
sem persistência, sem IA e sem lógica editorial; o agrupamento em `Event` pertence à
etapa CLUSTER.
"""

from tensdireito_content_engine.normalize.dates import normalize_published_at
from tensdireito_content_engine.normalize.dedup import (
    DeduplicationResult,
    ExactDuplicate,
    deduplicate_exact,
)
from tensdireito_content_engine.normalize.identity import fingerprint
from tensdireito_content_engine.normalize.item import NormalizedItem, normalize_raw_item
from tensdireito_content_engine.normalize.text import normalize_text, normalize_title

__all__ = [
    "DeduplicationResult",
    "ExactDuplicate",
    "NormalizedItem",
    "deduplicate_exact",
    "fingerprint",
    "normalize_published_at",
    "normalize_raw_item",
    "normalize_text",
    "normalize_title",
]
