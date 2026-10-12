"""Collector `news_sitemap`: news sitemap do editor → `RawItem` (DEC-069; especificação §3).

Lê um `<urlset>` com entradas `<news:news>` (título e data de publicação) ou um
`<sitemapindex>` com profundidade 1: neste caso lê até `MAX_CHILD_SITEMAPS` sitemaps
filhos do mesmo anfitrião, os mais recentes por `<lastmod>` (ou pela ordem do documento).

Como o collector `rss`: só descobre — não segue os links das notícias nem normaliza texto
ou datas; a rede passa só pelo transporte de `collectors/http.py` (DEC-033: HTTPS,
robots.txt, IP público, limites), e um `DOCTYPE` é recusado antes de construir o XML.

Zero resultados e falha são estados diferentes: um sitemap válido sem entradas devolve
lista vazia; XML truncado, raiz desconhecida, índice dentro de índice ou um sitemap só
com entradas que não são notícias levantam `FeedError`.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

from tensdireito_content_engine.collectors.http import FeedTransport, TransportError
from tensdireito_content_engine.collectors.rss import FeedError, _reject_doctype
from tensdireito_content_engine.domain import EndpointType, RawItem, SourceEndpoint

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
MAX_CHILD_SITEMAPS = 3

_URLSET = f"{{{SITEMAP_NS}}}urlset"
_INDEX = f"{{{SITEMAP_NS}}}sitemapindex"
_URL = f"{{{SITEMAP_NS}}}url"
_SITEMAP = f"{{{SITEMAP_NS}}}sitemap"
_LOC = f"{{{SITEMAP_NS}}}loc"
_LASTMOD = f"{{{SITEMAP_NS}}}lastmod"
_NEWS = f"{{{NEWS_NS}}}news"
_NEWS_TITLE = f"{{{NEWS_NS}}}title"
_NEWS_DATE = f"{{{NEWS_NS}}}publication_date"


class NewsSitemapCollector:
    endpoint_type = EndpointType.NEWS_SITEMAP

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
        fetched_at = self._now()
        body = self._transport.fetch_feed(endpoint.url).body
        root = parse_document(body)
        if root.tag == _URLSET:
            return entries(root, endpoint.id, fetched_at)
        children = child_sitemaps(root, endpoint.url)
        items: list[RawItem] = []
        for child_url in children:
            child = parse_document(self._transport.fetch_feed(child_url).body)
            if child.tag != _URLSET:
                raise FeedError("índice de sitemaps dentro de índice (só profundidade 1)")
            items.extend(entries(child, endpoint.id, fetched_at))
        return items


def parse_document(body: bytes) -> ET.Element:
    """Raiz `<urlset>` ou `<sitemapindex>` no namespace dos sitemaps."""
    _reject_doctype(body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise FeedError(f"XML malformado: {exc}") from None
    if root.tag not in (_URLSET, _INDEX):
        raise FeedError(f"formato não suportado: {root.tag}")
    return root


def child_sitemaps(index: ET.Element, index_url: str) -> list[str]:
    """Até `MAX_CHILD_SITEMAPS` filhos HTTPS do mesmo anfitrião, os mais recentes primeiro."""
    host = (urlsplit(index_url).hostname or "").lower()
    found: list[tuple[str, int, str]] = []
    for position, element in enumerate(index.findall(_SITEMAP)):
        loc = _child_text(element, _LOC)
        if loc is None:
            continue
        parts = urlsplit(loc)
        if parts.scheme != "https" or (parts.hostname or "").lower() != host:
            continue
        found.append((_child_text(element, _LASTMOD) or "", -position, loc))
    found.sort(reverse=True)
    return [loc for _, _, loc in found[:MAX_CHILD_SITEMAPS]]


def entries(urlset: ET.Element, endpoint_id: str, fetched_at: datetime) -> list[RawItem]:
    """Um `RawItem` por `<url>` com `<news:news>` e título, pela ordem do documento."""
    urls = urlset.findall(_URL)
    items: list[RawItem] = []
    for position, element in enumerate(urls, start=1):
        loc = _child_text(element, _LOC)
        news = element.find(_NEWS)
        title = _child_text(news, _NEWS_TITLE) if news is not None else None
        if news is None or title is None:
            continue  # entrada que não é notícia (página, categoria, imagem)
        if loc is None or not _is_absolute_http_url(loc):
            raise FeedError(f"entrada {position}: loc não é URL absoluto http/https")
        items.append(
            RawItem(
                url=loc,
                title=title,
                raw_content=_serialize(element),
                fetched_at=fetched_at,
                source_endpoint_id=endpoint_id,
                external_id=loc,
                published_at_raw=_child_text(news, _NEWS_DATE),
            )
        )
    if urls and not items:
        raise FeedError(f"sitemap sem entradas de notícias ({len(urls)} entradas sem news:news)")
    return items


def _child_text(element: ET.Element | None, tag: str) -> str | None:
    if element is None:
        return None
    child = element.find(tag)
    if child is None:
        return None
    text = "".join(child.itertext()).strip()
    return text or None


def _is_absolute_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _serialize(element: ET.Element) -> str:
    tail, element.tail = element.tail, None
    try:
        return ET.tostring(element, encoding="unicode")
    finally:
        element.tail = tail
