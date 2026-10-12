"""Etapa NORMALIZE: normalização mecânica e identidade de conteúdo (DEC-021).

RawItem → NormalizedItem → fingerprint → deduplicação exacta (M2.4, DEC-022), e a
extracção de texto e língua de itens `rss` (M2.11, DEC-040, DEC-038). Sem rede, sem
persistência, sem IA e sem lógica editorial; o agrupamento em `Event` pertence à etapa
CLUSTER.
"""

from tensdireito_content_engine.normalize.dates import normalize_published_at
from tensdireito_content_engine.normalize.dedup import (
    DeduplicationResult,
    ExactDuplicate,
    deduplicate_exact,
)
from tensdireito_content_engine.normalize.identity import fingerprint, text_fingerprint
from tensdireito_content_engine.normalize.item import NormalizedItem, normalize_raw_item
from tensdireito_content_engine.normalize.rss import (
    RawContentError,
    RssExtraction,
    extract_rss_item,
    html_to_text,
)
from tensdireito_content_engine.normalize.sitemap import extract_sitemap_entry
from tensdireito_content_engine.normalize.text import normalize_text, normalize_title

__all__ = [
    "DeduplicationResult",
    "ExactDuplicate",
    "NormalizedItem",
    "RawContentError",
    "RssExtraction",
    "deduplicate_exact",
    "extract_rss_item",
    "extract_sitemap_entry",
    "fingerprint",
    "html_to_text",
    "normalize_published_at",
    "normalize_raw_item",
    "normalize_text",
    "normalize_title",
    "text_fingerprint",
]
