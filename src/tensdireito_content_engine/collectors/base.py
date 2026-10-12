"""Contrato `Collector` e registo por `endpoint_type` (ROADMAP.md M2.8; DEC-031).

`fetch(endpoint, since)` recebe o `SourceEndpoint` de domínio e devolve `RawItem` de
domínio (o `RawItemIn` de TECHNICAL_SPEC.md §4.1). `since` é sempre `None` (DEC-031).
"""

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Protocol

from tensdireito_content_engine.collectors.http import HttpsTransport, TransportEvent
from tensdireito_content_engine.collectors.news_sitemap import NewsSitemapCollector
from tensdireito_content_engine.collectors.rss import RssCollector
from tensdireito_content_engine.domain import EndpointType, RawItem, SourceEndpoint


class Collector(Protocol):
    endpoint_type: EndpointType

    def fetch(self, endpoint: SourceEndpoint, since: datetime | None) -> Iterable[RawItem]: ...


class CollectorRegistry:
    """Associa cada `endpoint_type` a, no máximo, um `Collector`."""

    def __init__(
        self,
        collectors: Iterable[Collector] = (),
        events: Callable[[], list[TransportEvent]] | None = None,
    ) -> None:
        self._events = events
        self._by_type: dict[EndpointType, Collector] = {}
        for collector in collectors:
            endpoint_type = EndpointType(collector.endpoint_type)
            if endpoint_type in self._by_type:
                raise ValueError(f"collector repetido para endpoint_type {endpoint_type.value}")
            self._by_type[endpoint_type] = collector

    def get(self, endpoint_type: EndpointType) -> Collector | None:
        return self._by_type.get(endpoint_type)

    def drain_events(self) -> list[TransportEvent]:
        """Eventos do transporte desde a última chamada (DEC-070); vazio sem transporte."""
        return [] if self._events is None else self._events()


def default_registry() -> CollectorRegistry:
    """Registo de produção: `rss` e `news_sitemap` (DEC-069), com o transporte real.

    Cada chamada cria um transporte novo, partilhado pelos dois collectors: `robots.txt`
    e o intervalo por anfitrião valem para uma execução de `tde collect`.
    """
    transport = HttpsTransport()
    return CollectorRegistry(
        [RssCollector(transport), NewsSitemapCollector(transport)],
        events=transport.drain_events,
    )
