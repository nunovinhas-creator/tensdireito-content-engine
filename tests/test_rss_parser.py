"""Testes do M2.9: parsing de RSS 2.0 → `RawItem` (ROADMAP.md M2.9; DEC-032, DEC-033 §10).

Offline: só bytes de fixtures sintéticas (domínios reservados `example.org`; RFC 2606),
sem transporte nem rede.
"""

import pyexpat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tensdireito_content_engine.collectors.rss import FeedError, parse_feed

FIXTURES = Path(__file__).parent / "fixtures" / "rss"
T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
ENDPOINT = "feed_sintetico"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def parse(body: bytes | str):
    if isinstance(body, str):
        body = body.encode("utf-8")
    return parse_feed(body, ENDPOINT, T0)


def rss(items: str, *, channel_extra: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>Feed</title><link>https://feed.example.org/</link>{channel_extra}{items}"
        "</channel></rss>"
    )


def failure(body: bytes | str) -> str:
    with pytest.raises(FeedError) as info:
        parse(body)
    return str(info.value)


# --- Feed válido ----------------------------------------------------------------


def test_valid_feed_maps_every_item_in_document_order():
    items = parse(fixture("valid.xml"))
    assert [item.title for item in items] == [
        "Primeira notícia",
        "Segunda notícia",
        "Terceira notícia",
    ]
    first = items[0]
    assert first.url == "https://feed.example.org/noticias/1?utm_source=rss#topo"
    assert first.external_id == "id-0001"
    assert first.published_at_raw == "Wed, 07 Oct 2026 10:00:00 +0100"
    assert first.source_endpoint_id == ENDPOINT
    assert first.fetched_at == T0
    assert first.manual_note is None


def test_url_is_preserved_without_canonicalisation():
    # D12 aberta: parâmetros, fragmento e `http` mantêm-se.
    items = parse(fixture("valid.xml"))
    assert items[0].url.endswith("?utm_source=rss#topo")
    assert items[2].url == "http://feed.example.org/noticias/3"


def test_fetched_at_is_the_same_for_every_item():
    assert {item.fetched_at for item in parse(fixture("valid.xml"))} == {T0}


def test_raw_content_is_the_whole_item_element():
    items = parse(fixture("valid.xml"))
    second = items[1].raw_content
    assert second.startswith("<item")
    assert second.endswith("</item>")
    assert "<category>Trabalho</category>" in second
    assert "Corpo completo." in second  # content:encoded preservado
    assert "Primeira notícia" not in second


def test_raw_content_is_deterministic():
    first = [item.raw_content for item in parse(fixture("valid.xml"))]
    second = [item.raw_content for item in parse(fixture("valid.xml"))]
    assert first == second
    assert [i.content_hash for i in parse(fixture("valid.xml"))] == [
        i.content_hash for i in parse(fixture("valid.xml"))
    ]


def test_html_in_description_is_kept_raw_without_editorial_interpretation():
    raw = parse(fixture("valid.xml"))[1].raw_content
    # O HTML do CDATA fica como texto escapado no XML do item, sem limpeza nem extracção.
    assert "&lt;p&gt;Texto com &lt;strong&gt;HTML&lt;/strong&gt; &amp;amp; entidades." in raw


def test_rss_version_attribute_is_not_a_condition():
    body = rss("<item><title>T</title><link>https://feed.example.org/1</link></item>")
    assert len(parse(body.replace(' version="2.0"', ""))) == 1
    assert len(parse(body.replace('version="2.0"', 'version="0.92"'))) == 1


def test_several_items():
    items_xml = "".join(
        f"<item><title>Item {n}</title><link>https://feed.example.org/{n}</link></item>"
        for n in range(1, 51)
    )
    items = parse(rss(items_xml))
    assert [item.url for item in items] == [f"https://feed.example.org/{n}" for n in range(1, 51)]


def test_empty_feed_is_success_with_zero_items():
    assert parse(fixture("empty.xml")) == []


def test_items_outside_the_channel_are_not_items_of_the_feed():
    body = rss("").replace(
        "</channel>",
        "</channel><item><title>T</title><link>https://feed.example.org/</link></item>",
    )
    assert parse(body) == []


# --- Campos obrigatórios e opcionais --------------------------------------------


@pytest.mark.parametrize(
    ("second_item", "error"),
    [
        ("<item><link>https://feed.example.org/2</link></item>", "item 2: sem título"),
        ("<item><title> </title><link>https://f.example.org/2</link></item>", "item 2: sem título"),
        ("<item><title/><link>https://feed.example.org/2</link></item>", "item 2: sem título"),
        ("<item><title>T</title></item>", "item 2: sem link"),
        ("<item><title>T</title><link> </link></item>", "item 2: sem link"),
        (
            "<item><title>T</title><link>/relativo/2</link></item>",
            "item 2: link não é URL absoluto http/https",
        ),
        (
            "<item><title>T</title><link>ftp://feed.example.org/2</link></item>",
            "item 2: link não é URL absoluto http/https",
        ),
        (
            "<item><title>T</title><link>https://</link></item>",
            "item 2: link não é URL absoluto http/https",
        ),
        (
            # O `guid` nunca substitui `<link>`, mesmo com isPermaLink.
            '<item><title>T</title><guid isPermaLink="true">https://feed.example.org/2</guid></item>',
            "item 2: sem link",
        ),
    ],
)  # fmt: skip
def test_invalid_item_fails_the_whole_feed_with_its_position(second_item, error):
    first = "<item><title>Válido</title><link>https://feed.example.org/1</link></item>"
    assert failure(rss(first + second_item)) == error


def test_missing_description_is_accepted():
    [item] = parse(rss("<item><title>T</title><link>https://feed.example.org/1</link></item>"))
    assert "description" not in item.raw_content


def test_missing_guid_and_pubdate_are_null():
    [item] = parse(rss("<item><title>T</title><link>https://feed.example.org/1</link></item>"))
    assert item.external_id is None
    assert item.published_at_raw is None


def test_empty_guid_and_pubdate_are_null():
    body = rss(
        "<item><title>T</title><link>https://feed.example.org/1</link>"
        "<guid>  </guid><pubDate></pubDate></item>"
    )
    [item] = parse(body)
    assert (item.external_id, item.published_at_raw) == (None, None)


def test_guid_ispermalink_is_not_interpreted_and_link_wins():
    body = rss(
        "<item><title>T</title><link>https://feed.example.org/link</link>"
        '<guid isPermaLink="true"> https://feed.example.org/guid </guid></item>'
    )
    [item] = parse(body)
    assert item.url == "https://feed.example.org/link"
    assert item.external_id == "https://feed.example.org/guid"


def test_pubdate_is_kept_raw_only_without_outer_whitespace():
    body = rss(
        "<item><title>T</title><link>https://feed.example.org/1</link>"
        "<pubDate>\n  Qua, 7 Out 2026 25:99 hora de Lisboa \n</pubDate></item>"
    )
    [item] = parse(body)
    assert item.published_at_raw == "Qua, 7 Out 2026 25:99 hora de Lisboa"


def test_link_only_loses_outer_whitespace():
    body = rss("<item><title>T</title><link>\n  https://feed.example.org/A?b=C  \n</link></item>")
    [item] = parse(body)
    assert item.url == "https://feed.example.org/A?b=C"


def test_title_is_kept_unchanged():
    body = rss(
        "<item><title>  Título   com  espaços </title><link>https://x.example.org/</link></item>"
    )
    [item] = parse(body)
    assert item.title == "  Título   com  espaços "


# --- Formato --------------------------------------------------------------------


def test_atom_is_rejected():
    assert (
        failure(fixture("atom.xml")) == "formato não suportado: {http://www.w3.org/2005/Atom}feed"
    )


def test_rss_1_0_rdf_is_rejected():
    assert failure(fixture("rss1.xml")) == (
        "formato não suportado: {http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
    )


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("<html><body>não é um feed</body></html>", "formato não suportado: html"),
        ("<rss version='2.0'/>", "formato não suportado: rss com 0 channel"),
        ("<rss><channel/><channel/></rss>", "formato não suportado: rss com 2 channel"),
        ("<rss xmlns='urn:x'><channel/></rss>", "formato não suportado: {urn:x}rss"),
    ],
)
def test_unexpected_xml_content_is_rejected(body, error):
    assert failure(body) == error


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<rss><channel></rss>",
        b"isto n\xc3\xa3o \xc3\xa9 XML",
        b"<rss><channel><item><title>T &nbsp; </title></item></channel></rss>",
        b'<?xml version="1.0"?><rss><channel><title>\xff\xfe</title></channel></rss>',
    ],
    ids=["vazio", "mal-fechado", "texto", "entidade-indefinida", "bytes-invalidos"],
)
def test_malformed_or_undecodable_xml_fails(body):
    assert failure(body).startswith("XML malformado: ")


def test_unsupported_encoding_fails():
    body = b'<?xml version="1.0" encoding="x-desconhecida"?><rss><channel/></rss>'
    assert failure(body) == "codificação não suportada"


# --- DOCTYPE e entidades (DEC-033 §10) ----------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<?xml version="1.0"?><!DOCTYPE rss><rss><channel/></rss>',
        '<!DOCTYPE rss SYSTEM "https://feed.example.org/rss.dtd"><rss><channel/></rss>',
        (
            '<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<rss><channel><item><title>&xxe;</title><link>https://a.example.org/</link></item>"
            "</channel></rss>"
        ),
        (
            '<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">'
            '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;">]>'
            "<rss><channel><title>&lol3;</title></channel></rss>"
        ),
        (
            '<!DOCTYPE rss [<!ENTITY % ext SYSTEM "https://feed.example.org/x.dtd"> %ext;]>'
            "<rss><channel/></rss>"
        ),
    ],
    ids=["simples", "dtd-externo", "xxe", "expansao", "entidade-parametro"],
)
def test_any_doctype_is_rejected_before_entities(body):
    assert failure(body) == "DOCTYPE não permitido"


def test_expat_version_is_safe():
    assert pyexpat.version_info >= (2, 4, 1)


# --- Codificação e Unicode ------------------------------------------------------


def test_unicode_characters_are_preserved():
    body = rss(
        "<item><title>Decisão — férias, subsídio e 1.º trimestre € 😀</title>"
        "<link>https://feed.example.org/ação?q=ç</link>"
        "<description>Acórdão «uniformizador» n.º 5/2026</description></item>"
    )
    [item] = parse(body)
    assert item.title == "Decisão — férias, subsídio e 1.º trimestre € 😀"
    assert item.url == "https://feed.example.org/ação?q=ç"
    assert "Acórdão «uniformizador» n.º 5/2026" in item.raw_content


def test_utf8_with_bom():
    [item] = parse(fixture("utf-8-bom.xml"))
    assert item.title == "Decisão sobre férias — € 1º"


def test_declared_iso_8859_1():
    [item] = parse(fixture("iso-8859-1.xml"))
    assert item.title == "Decisão do Tribunal sobre férias e subsídio"
    assert item.url == "https://feed.example.org/ação"
    assert "Acórdão n.º 1" in item.raw_content


# --- Links de clique do Bing Notícias (DEC-055) ---------------------------------


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        (
            "https://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;tid=ABC"
            "&amp;url=https%3a%2f%2fnoticias.example.org%2fabono%3fx%3d1&amp;c=123&amp;mkt=pt-pt",
            "https://noticias.example.org/abono?x=1",
        ),
        (
            "https://bing.com/news/apiclick.aspx?url=javascript%3aalert(1)",
            "https://bing.com/news/apiclick.aspx?url=javascript%3aalert(1)",
        ),
        ("https://www.bing.com/news/search?url=https%3a%2f%2fx.example.org", None),
        ("https://noticias.example.org/a?url=https%3a%2f%2fy.example.org", None),
    ],
)
def test_bing_click_links_are_unwrapped_to_the_publisher_url(link, expected):
    body = rss(f"<item><title>T</title><link>{link}</link></item>")
    [item] = parse(body)
    original = link.replace("&amp;", "&")
    assert item.url == (expected if expected is not None else original)
