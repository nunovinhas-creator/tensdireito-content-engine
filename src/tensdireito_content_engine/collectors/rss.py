"""Collector `rss`: RSS 2.0 → `RawItem` (ROADMAP.md M2.9; DEC-032).

O parsing (`parse_feed`) é uma função pura de `bytes` para `RawItem`, sem rede; o corpo
do feed chega pelo transporte injectado (`collectors/http.py`, DEC-033). O collector não
deduplica, não segue os links dos itens, não calcula `canonical_url` (D12) e não
normaliza texto, título nem datas (D13).

XML: só a biblioteca padrão. Uma primeira passagem com Expat recusa qualquer `DOCTYPE`
antes de se processarem entidades (DEC-033 §10); só depois o documento é construído com
`xml.etree.ElementTree`.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from xml.parsers import expat

from tensdireito_content_engine.collectors.http import FeedTransport, TransportError
from tensdireito_content_engine.domain import EndpointType, RawItem, SourceEndpoint


class FeedError(Exception):
    """Conteúdo do feed recusado; a mensagem é determinista e não inclui o corpo."""


class _DoctypeFound(Exception):
    pass


class RssCollector:
    endpoint_type = EndpointType.RSS

    def __init__(
        self,
        transport: FeedTransport,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._transport = transport
        self._now = now

    def fetch(self, endpoint: SourceEndpoint, since: datetime | None) -> list[RawItem]:
        """`since` é ignorado (sempre `None`, DEC-031)."""
        if endpoint.url is None:
            raise TransportError("URL ausente")
        response = self._transport.fetch_feed(
            endpoint.url,
            redirect_hosts=endpoint.redirect_hosts,
            redirect_is_throttle=endpoint.redirect_is_throttle,
        )
        return parse_feed(response.body, endpoint.id, self._now())


def parse_feed(body: bytes, endpoint_id: str, fetched_at: datetime) -> list[RawItem]:
    """Um `RawItem` por `<item>` do `<channel>`, pela ordem do documento."""
    _reject_doctype(body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise FeedError(f"XML malformado: {exc}") from None
    if root.tag != "rss":
        raise FeedError(f"formato não suportado: {root.tag}")
    channels = root.findall("channel")
    if len(channels) != 1:
        raise FeedError(f"formato não suportado: rss com {len(channels)} channel")
    return [
        _raw_item(position, element, endpoint_id, fetched_at)
        for position, element in enumerate(channels[0].findall("item"), start=1)
    ]


def _reject_doctype(body: bytes) -> None:
    parser = expat.ParserCreate()

    def on_doctype(*_args: object) -> None:
        raise _DoctypeFound

    parser.StartDoctypeDeclHandler = on_doctype
    try:
        parser.Parse(body, True)
    except _DoctypeFound:
        raise FeedError("DOCTYPE não permitido") from None
    except expat.ExpatError as exc:
        raise FeedError(f"XML malformado: {exc}") from None
    except (LookupError, UnicodeError):
        raise FeedError("codificação não suportada") from None


def _raw_item(
    position: int, element: ET.Element, endpoint_id: str, fetched_at: datetime
) -> RawItem:
    title = _text(element, "title")
    if title is None or not title.strip():
        raise FeedError(f"item {position}: sem título")
    link = _text(element, "link")
    if link is None or not link.strip():
        raise FeedError(f"item {position}: sem link")
    url = _unwrap_aggregator_link(link.strip())
    if not _is_absolute_http_url(url):
        raise FeedError(f"item {position}: link não é URL absoluto http/https")
    return RawItem(
        url=url,
        title=title,
        raw_content=_serialize(element),
        fetched_at=fetched_at,
        source_endpoint_id=endpoint_id,
        external_id=_stripped(_text(element, "guid")),
        published_at_raw=_stripped(_text(element, "pubDate")),
    )


def _text(element: ET.Element, tag: str) -> str | None:
    """Texto do primeiro filho `tag`, ou `None` se não existir."""
    child = element.find(tag)
    if child is None:
        return None
    return "".join(child.itertext())


def _stripped(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


_AGGREGATOR_REDIRECTS = {
    ("www.bing.com", "/news/apiclick.aspx"),
    ("bing.com", "/news/apiclick.aspx"),
}


def _unwrap_aggregator_link(url: str) -> str:
    """URL do editor dentro de um link de clique de agregador (DEC-055).

    O Bing Notícias entrega `bing.com/news/apiclick.aspx?url=<editor>&tid=…`; o
    parâmetro `url` é lido sem seguir o link. Outros URLs ficam inalterados.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if ((parts.hostname or "").lower(), parts.path.lower()) not in _AGGREGATOR_REDIRECTS:
        return url
    target = parse_qs(parts.query).get("url", [""])[0].strip()
    return target if _is_absolute_http_url(target) else url


def _is_absolute_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _serialize(element: ET.Element) -> str:
    """O elemento `<item>` completo, sem o espaço que o segue no documento."""
    tail, element.tail = element.tail, None
    try:
        return ET.tostring(element, encoding="unicode")
    finally:
        element.tail = tail
