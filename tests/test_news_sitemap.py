"""Collector `news_sitemap` (DEC-069): casos da §9 da especificação (fase 2, sitemaps)."""

from datetime import UTC, datetime

import pytest

from tensdireito_content_engine.collectors.http import Response, TransportError
from tensdireito_content_engine.collectors.news_sitemap import (
    MAX_CHILD_SITEMAPS,
    NewsSitemapCollector,
)
from tensdireito_content_engine.collectors.rss import FeedError
from tensdireito_content_engine.domain import EndpointStatus, EndpointType, SourceEndpoint
from tensdireito_content_engine.normalize import normalize_published_at

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
SM = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS = "http://www.google.com/schemas/sitemap-news/0.9"


class FakeTransport:
    def __init__(self, pages: dict[str, bytes | Exception]):
        self.pages = pages
        self.requested: list[str] = []
        self.options: list[tuple[tuple[str, ...], bool]] = []

    def fetch_feed(self, url: str, *, redirect_hosts=(), redirect_is_throttle=False) -> Response:
        self.requested.append(url)
        self.options.append((tuple(redirect_hosts), redirect_is_throttle))
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return Response(status=200, content_type="application/xml", body=page)


def endpoint(url="https://jornal.example/news-sitemap.xml"):
    return SourceEndpoint(
        id="jornal-news-sitemap",
        source_id="jornal",
        endpoint_type=EndpointType.NEWS_SITEMAP,
        url=url,
        endpoint_status=EndpointStatus.ACTIVE,
        validated_at=NOW,
        validated_by="nuno",
    )


def entry(loc, title=None, date=None, prefix="news"):
    news = ""
    if title is not None:
        parts = [f"<{prefix}:title>{title}</{prefix}:title>"]
        if date is not None:
            parts.append(f"<{prefix}:publication_date>{date}</{prefix}:publication_date>")
        news = f"<{prefix}:news>{''.join(parts)}</{prefix}:news>"
    return f"<url><loc>{loc}</loc>{news}</url>"


def urlset(*entries, prefix="news"):
    body = "".join(entries)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="{SM}" xmlns:{prefix}="{NEWS}">{body}</urlset>'
    ).encode()


def collect(pages, url="https://jornal.example/news-sitemap.xml"):
    transport = FakeTransport(pages)
    items = NewsSitemapCollector(transport, now=lambda: NOW).fetch(endpoint(url), None)
    return items, transport


def test_news_entries_become_raw_items():
    body = urlset(
        entry("https://jornal.example/a", "Abono sobe em janeiro", "2026-10-12T08:30:00+01:00"),
        entry("https://jornal.example/b", "IEFP abre candidaturas", "2026-10-12"),
    )
    items, _ = collect({"https://jornal.example/news-sitemap.xml": body})
    assert [(i.url, i.title, i.published_at_raw) for i in items] == [
        ("https://jornal.example/a", "Abono sobe em janeiro", "2026-10-12T08:30:00+01:00"),
        ("https://jornal.example/b", "IEFP abre candidaturas", "2026-10-12"),
    ]
    assert items[0].external_id == "https://jornal.example/a"
    assert items[0].source_endpoint_id == "jornal-news-sitemap"
    assert items[0].fetched_at == NOW
    assert "Abono sobe em janeiro" in items[0].raw_content
    assert normalize_published_at(items[0].published_at_raw) == datetime(
        2026, 10, 12, 7, 30, tzinfo=UTC
    )


def test_namespace_prefixes_do_not_matter():
    body = (
        f'<?xml version="1.0"?><sm:urlset xmlns:sm="{SM}" xmlns:n="{NEWS}">'
        "<sm:url><sm:loc>https://jornal.example/a</sm:loc>"
        "<n:news><n:title>Pensões sobem</n:title>"
        "<n:publication_date>2026-10-12T08:00:00Z</n:publication_date></n:news></sm:url>"
        "</sm:urlset>"
    ).encode()
    items, _ = collect({"https://jornal.example/news-sitemap.xml": body})
    assert [i.title for i in items] == ["Pensões sobem"]


def test_entry_without_publication_date_is_kept_without_date():
    body = urlset(entry("https://jornal.example/a", "Abono sobe"))
    items, _ = collect({"https://jornal.example/news-sitemap.xml": body})
    assert items[0].published_at_raw is None


def test_malformed_date_is_kept_raw_and_does_not_normalize():
    body = urlset(entry("https://jornal.example/a", "Abono sobe", "ontem à tarde"))
    items, _ = collect({"https://jornal.example/news-sitemap.xml": body})
    assert items[0].published_at_raw == "ontem à tarde"
    assert normalize_published_at(items[0].published_at_raw) is None


def test_valid_empty_sitemap_is_empty_not_an_error():
    items, _ = collect({"https://jornal.example/news-sitemap.xml": urlset()})
    assert items == []


@pytest.mark.parametrize(
    "body",
    [
        urlset(entry("https://jornal.example/a", "Abono sobe"))[:-20],  # truncado
        b"<?xml version='1.0'?><rss><channel/></rss>",  # raiz desconhecida
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><urlset/>',  # DOCTYPE
    ],
)
def test_broken_documents_are_errors_not_empty(body):
    with pytest.raises(FeedError):
        collect({"https://jornal.example/news-sitemap.xml": body})


def test_sitemap_with_only_non_news_entries_is_an_error():
    body = urlset(entry("https://jornal.example/categoria"), entry("https://jornal.example/sobre"))
    with pytest.raises(FeedError, match="sem entradas de notícias"):
        collect({"https://jornal.example/news-sitemap.xml": body})


def test_non_news_entries_are_skipped_when_news_exist():
    body = urlset(
        entry("https://jornal.example/categoria"),
        entry("https://jornal.example/a", "Abono sobe", "2026-10-12"),
    )
    items, _ = collect({"https://jornal.example/news-sitemap.xml": body})
    assert [i.url for i in items] == ["https://jornal.example/a"]


def test_relative_loc_in_a_news_entry_is_an_error():
    body = urlset(entry("/a", "Abono sobe", "2026-10-12"))
    with pytest.raises(FeedError, match="loc"):
        collect({"https://jornal.example/news-sitemap.xml": body})


def index(*children):
    body = "".join(
        f"<sitemap><loc>{loc}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "") + "</sitemap>"
        for loc, mod in children
    )
    return f'<?xml version="1.0"?><sitemapindex xmlns="{SM}">{body}</sitemapindex>'.encode()


def test_index_reads_the_most_recent_children_of_the_same_host():
    root = "https://jornal.example/sitemap.xml"
    children = [(f"https://jornal.example/news-{n}.xml", f"2026-10-{n:02d}") for n in range(1, 6)]
    pages = {root: index(*children, ("https://outro.example/news.xml", "2026-10-30"))}
    for n in range(1, 6):
        pages[f"https://jornal.example/news-{n}.xml"] = urlset(
            entry(f"https://jornal.example/{n}", f"Notícia {n}", "2026-10-12")
        )
    items, transport = collect(pages, root)
    assert transport.requested == [
        root,
        "https://jornal.example/news-5.xml",
        "https://jornal.example/news-4.xml",
        "https://jornal.example/news-3.xml",
    ]
    assert len(transport.requested) == 1 + MAX_CHILD_SITEMAPS
    assert [i.title for i in items] == ["Notícia 5", "Notícia 4", "Notícia 3"]


def test_index_inside_index_is_rejected():
    root = "https://jornal.example/sitemap.xml"
    pages = {
        root: index(("https://jornal.example/sub.xml", None)),
        "https://jornal.example/sub.xml": index(("https://jornal.example/news.xml", None)),
    }
    with pytest.raises(FeedError, match="profundidade 1"):
        collect(pages, root)


def test_transport_failures_propagate():
    error = TransportError("resposta excede 5 MiB")
    with pytest.raises(TransportError, match="5 MiB"):
        collect({"https://jornal.example/news-sitemap.xml": error})


def test_normalize_extracts_language_and_no_text_from_a_sitemap_entry():
    from tensdireito_content_engine.normalize import RawContentError, extract_sitemap_entry

    raw = (
        f'<url xmlns="{SM}" xmlns:n="{NEWS}"><loc>https://jornal.example/a</loc><n:news>'
        "<n:publication><n:name>Jornal</n:name><n:language>pt-PT</n:language></n:publication>"
        "<n:title>Abono sobe</n:title></n:news></url>"
    )
    extraction = extract_sitemap_entry(raw)
    assert (extraction.text, extraction.language) == (None, "pt")
    assert extract_sitemap_entry(raw.replace("pt-PT", "português")).language is None
    with pytest.raises(RawContentError):
        extract_sitemap_entry("<item><title>RSS</title></item>")
    with pytest.raises(RawContentError):
        extract_sitemap_entry(raw[:-10])
