"""Collectors: obtenção de `RawItem` por `endpoint_type` (TECHNICAL_SPEC.md §4.1; DEC-031).

Dependem só de `domain`: não importam `storage` nem `sqlite3`. Desde o M2.9, o registo de
produção tem um collector concreto, `rss` (RSS 2.0; DEC-032), sobre o único transporte de
rede do sistema, `collectors/http.py` (DEC-033). `html_page` e `manual` não existem.
"""

from tensdireito_content_engine.collectors.base import (
    Collector,
    CollectorRegistry,
    default_registry,
)

__all__ = ["Collector", "CollectorRegistry", "default_registry"]
