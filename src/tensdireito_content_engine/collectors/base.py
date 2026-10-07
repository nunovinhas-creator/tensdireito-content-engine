"""Contrato `Collector` e registo por `endpoint_type` (ROADMAP.md M2.8; DEC-031).

`fetch(endpoint, since)` recebe o `SourceEndpoint` de domínio e devolve `RawItem` de
domínio (o `RawItemIn` de TECHNICAL_SPEC.md §4.1). No M2.8, `since` é sempre `None`.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from tensdireito_content_engine.domain import EndpointType, RawItem, SourceEndpoint


class Collector(Protocol):
    endpoint_type: EndpointType

    def fetch(self, endpoint: SourceEndpoint, since: datetime | None) -> Iterable[RawItem]: ...


class CollectorRegistry:
    """Associa cada `endpoint_type` a, no máximo, um `Collector`."""

    def __init__(self, collectors: Iterable[Collector] = ()) -> None:
        self._by_type: dict[EndpointType, Collector] = {}
        for collector in collectors:
            endpoint_type = EndpointType(collector.endpoint_type)
            if endpoint_type in self._by_type:
                raise ValueError(f"collector repetido para endpoint_type {endpoint_type.value}")
            self._by_type[endpoint_type] = collector

    def get(self, endpoint_type: EndpointType) -> Collector | None:
        return self._by_type.get(endpoint_type)


def default_registry() -> CollectorRegistry:
    """Registo de produção: vazio no M2.8 (sem collectors concretos)."""
    return CollectorRegistry()
