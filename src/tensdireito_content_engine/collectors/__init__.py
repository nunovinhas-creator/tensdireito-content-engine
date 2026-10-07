"""Collectors: obtenção de `RawItem` por `endpoint_type` (TECHNICAL_SPEC.md §4.1; DEC-031).

Dependem só de `domain`: não importam `storage` nem `sqlite3`. No M2.8 existe apenas o
contrato e o registo; nenhum collector concreto (`rss`, `html_page`, `manual`) está
implementado e o registo de produção fica vazio.
"""

from tensdireito_content_engine.collectors.base import (
    Collector,
    CollectorRegistry,
    default_registry,
)

__all__ = ["Collector", "CollectorRegistry", "default_registry"]
