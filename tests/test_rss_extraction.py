"""Testes do M2.11: extracção de texto e língua de itens `rss` (DEC-040, DEC-038).

Funções puras, sem base de dados e sem rede. `raw_content` sintético, escrito à mão ou
produzido pelo parser do M2.9 (`parse_feed`), para cobrir a serialização real (`ns0:`).
"""

from datetime import UTC, datetime

import pytest

from tensdireito_content_engine.collectors.rss import parse_feed
from tensdireito_content_engine.normalize import (
    RawContentError,
    extract_rss_item,
    html_to_text,
    normalize_text,
    text_fingerprint,
)
from tensdireito_content_engine.normalize.rss import BLOCK_TAGS, CONTENT_NAMESPACE

FETCHED = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
NS = f'xmlns:content="{CONTENT_NAMESPACE}"'


def item(children: str, attrs: str = "") -> str:
    return f"<item{attrs}><title>Título</title><link>https://feed.example.org/1</link>{children}</item>"


def via_m29(item_xml: str, namespaces: str = NS) -> str:
    """`raw_content` tal como o collector `rss` o grava (DEC-032)."""
    feed = f'<rss version="2.0" {namespaces}><channel><title>F</title>{item_xml}</channel></rss>'
    (raw,) = parse_feed(feed.encode("utf-8"), "feed_sintetico", FETCHED)
    return raw.raw_content


def text_of(raw_content: str) -> str | None:
    return extract_rss_item(raw_content).text


# --- Selecção do candidato --------------------------------------------------------


def test_content_encoded_is_preferred_and_never_concatenated():
    raw = via_m29(
        item("<description>Resumo.</description><content:encoded>Corpo.</content:encoded>")
    )
    assert text_of(raw) == "Corpo."


def test_m29_serialization_rewrites_the_prefix_and_is_still_recognised():
    raw = via_m29(item("<content:encoded>Corpo.</content:encoded>"))
    assert "ns0:encoded" in raw
    assert "content:encoded" not in raw
    assert text_of(raw) == "Corpo."


def test_content_encoded_is_recognised_by_namespace_uri_not_prefix():
    other_prefix = item(f'<x:encoded xmlns:x="{CONTENT_NAMESPACE}">Corpo.</x:encoded>')
    assert text_of(other_prefix) == "Corpo."
    wrong_uri = item(
        '<content:encoded xmlns:content="https://feed.example.org/ns">Falso.</content:encoded>'
        "<description>Resumo.</description>"
    )
    assert text_of(wrong_uri) == "Resumo."
    no_namespace = item("<encoded>Falso.</encoded><description>Resumo.</description>")
    assert text_of(no_namespace) == "Resumo."


def test_description_is_used_without_content_encoded():
    assert text_of(via_m29(item("<description>Resumo.</description>"))) == "Resumo."


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "   ",
        "<![CDATA[<p> </p><br/>]]>",
        "&lt;script&gt;x&lt;/script&gt;",
        "<![CDATA[<!-- c -->]]>",
    ],
)
def test_empty_content_encoded_after_html_removal_falls_back_to_description(encoded):
    raw = via_m29(
        item(f"<content:encoded>{encoded}</content:encoded><description>R.</description>")
    )
    assert text_of(raw) == "R."


def test_description_in_a_namespace_is_not_description():
    raw = item('<d:description xmlns:d="https://feed.example.org/ns">Falso.</d:description>')
    assert text_of(raw) is None


def test_only_direct_children_are_candidates():
    raw = item("<outro><description>Profundo.</description></outro>")
    assert text_of(raw) is None


def test_first_candidate_element_is_used():
    raw = item("<description>Primeira.</description><description>Segunda.</description>")
    assert text_of(raw) == "Primeira."


def test_candidate_text_includes_descendants():
    raw = item("<description>Um <b>dois</b> três</description>")
    assert text_of(raw) == "Um dois três"


# --- Sem texto útil ---------------------------------------------------------------


@pytest.mark.parametrize(
    "children",
    ["", "<description></description>", "<description>  \n </description>"],
)
def test_without_useful_text_there_is_no_text_and_the_title_is_never_used(children):
    extraction = extract_rss_item(via_m29(item(children)))
    assert extraction.text is None


# --- Remoção de HTML ----------------------------------------------------------------


def test_cdata_and_escaped_html_give_the_same_text():
    cdata = via_m29(item("<description><![CDATA[<p>A &amp; B</p><p>C</p>]]></description>"))
    escaped = via_m29(
        item("<description>&lt;p&gt;A &amp;amp; B&lt;/p&gt;&lt;p&gt;C&lt;/p&gt;</description>")
    )
    assert text_of(cdata) == text_of(escaped) == "A & B\n\nC"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("&amp; &lt; &gt; &quot; &#39; &#x41; &eacute;", "& < > \" ' A é"),
        ("a&nbsp;b", "a b"),
        ("<p>Antes<script>alert('x')</script>depois</p>", "Antesdepois"),
        ("<style>p { color: red }</style>Texto", "Texto"),
        ("<SCRIPT type='text/javascript'>var a = '<p>';</SCRIPT>Texto", "Texto"),
        ("Antes<!-- comentário -->depois", "Antesdepois"),
        ("<!DOCTYPE html>Texto<?pi x?>", "Texto"),
        ("<p>A</p><p>B</p>", "A\n\nB"),
        ("A<br>B", "A\nB"),
        ("A<br/>B", "A\nB"),
        ("A<br />B", "A\nB"),
        ("<ul><li>um</li><li>dois</li></ul>", "um\n\ndois"),
        ("<h1>T</h1>texto", "T\ntexto"),
        (
            "pala<b>vra</b> <i>in</i>teira <a href='https://x.example'>ligação</a>",
            "palavra inteira ligação",
        ),
        ("<span>a</span><em>b</em><strong>c</strong>", "abc"),
        ("<img alt='alternativo' title='título' src='x.png'>Texto", "Texto"),
        ("<div>  muito   espaço\t aqui  </div>", "muito espaço aqui"),
        ("<p>A</p>\n\n\n\n<p>B</p>", "A\n\nB"),
        ("Café", "Café"),
    ],
)
def test_html_removal(html, expected):
    assert html_to_text(html) == expected


@pytest.mark.parametrize("tag", sorted(BLOCK_TAGS))
def test_every_block_tag_separates_lines(tag):
    assert html_to_text(f"a<{tag}>b</{tag}>c") == "a\nb\nc"


def test_block_tags_are_the_closed_list_of_dec040():
    headings = {f"h{level}" for level in range(1, 7)}
    assert BLOCK_TAGS == {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "figcaption", "figure", "footer", "header", "hr", "li", "main", "nav", "ol", "p",
        "pre", "section", "table", "td", "th", "tr", "ul",
    } | headings  # fmt: skip


@pytest.mark.parametrize("tag", ["span", "b", "strong", "i", "em", "a", "code", "small", "font"])
def test_inline_tags_do_not_separate(tag):
    assert html_to_text(f"pa<{tag}>la</{tag}>vra") == "palavra"


def test_result_is_normalized_by_dec021():
    raw = html_to_text("  <p>\tlinha  um  </p>\r\n<p>linha dois</p>  ")
    assert raw == normalize_text(raw) == "linha um\n\nlinha dois"


def test_extraction_is_deterministic_and_hash_is_the_dec021_fingerprint():
    raw = via_m29(item("<content:encoded><![CDATA[<p>Corpo.</p>]]></content:encoded>"))
    first, second = extract_rss_item(raw), extract_rss_item(raw)
    assert first == second
    assert text_fingerprint(first.text) == text_fingerprint("Corpo.")
    assert len(text_fingerprint("Corpo.")) == 64


# --- XML ilegível ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("<item><title>x</title>", "XML malformado: "),
        ("não é XML", "XML malformado: "),
        ("", "XML malformado: "),
        (
            '<!DOCTYPE item [<!ENTITY e "x">]><item><title>&e;</title></item>',
            "DOCTYPE não permitido",
        ),
        ("<!DOCTYPE item><item/>", "DOCTYPE não permitido"),
        ("<rss><channel/></rss>", "raiz não suportada: rss"),
        (
            '<x:item xmlns:x="https://feed.example.org/ns"/>',
            "raiz não suportada: {https://feed.example.org/ns}item",
        ),
    ],
)
def test_unreadable_raw_content_is_an_error(raw, message):
    with pytest.raises(RawContentError) as excinfo:
        extract_rss_item(raw)
    assert str(excinfo.value).startswith(message)


def test_doctype_is_rejected_before_entities_are_expanded():
    bomb = (
        '<!DOCTYPE item [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        "<item><description>&b;</description></item>"
    )
    with pytest.raises(RawContentError, match="^DOCTYPE não permitido$"):
        extract_rss_item(bomb)


def test_raw_content_is_not_modified():
    raw = via_m29(item("<description><![CDATA[<p>A</p>]]></description>"))
    copy = str(raw)
    extract_rss_item(raw)
    assert raw == copy


# --- Língua (DEC-038) ------------------------------------------------------------


def lang_of(raw_content: str) -> str | None:
    return extract_rss_item(raw_content).language


def test_item_xml_lang_gives_the_primary_subtag_in_lowercase():
    assert lang_of(via_m29(item("<description>T.</description>", ' xml:lang="pt-PT"'))) == "pt"


def test_chosen_element_xml_lang_wins_over_item():
    raw = via_m29(
        item(
            '<description xml:lang="es">R.</description>'
            '<content:encoded xml:lang="EN-gb">C.</content:encoded>',
            ' xml:lang="pt-PT"',
        )
    )
    extraction = extract_rss_item(raw)
    assert (extraction.text, extraction.language) == ("C.", "en")


def test_xml_lang_of_an_unchosen_element_is_ignored():
    raw = item(
        f'<content:encoded {NS} xml:lang="en"></content:encoded><description>R.</description>',
        ' xml:lang="pt"',
    )
    assert lang_of(raw) == "pt"


def test_without_chosen_element_the_item_xml_lang_is_used():
    raw = via_m29(item("", ' xml:lang="pt"'))
    extraction = extract_rss_item(raw)
    assert (extraction.text, extraction.language) == (None, "pt")


@pytest.mark.parametrize("value", ["", "p", "port", "pt_PT", "1a", " pt", "pt ", "pö", "x-pt"])
def test_empty_or_malformed_xml_lang_is_null(value):
    raw = item("<description>T.</description>", f' xml:lang="{value}"')
    assert lang_of(raw) is None


@pytest.mark.parametrize(("value", "expected"), [("PT", "pt"), ("mwl", "mwl"), ("pt-BR", "pt")])
def test_valid_primary_subtags(value, expected):
    assert lang_of(item("<description>T.</description>", f' xml:lang="{value}"')) == expected


def test_empty_xml_lang_on_the_element_overrides_the_item():
    raw = item('<description xml:lang="">T.</description>', ' xml:lang="pt"')
    assert lang_of(raw) is None


def test_without_declaration_language_is_null():
    assert lang_of(via_m29(item("<description>Texto em português.</description>"))) is None


def test_channel_language_has_no_effect():
    feed = (
        '<rss version="2.0"><channel><title>F</title><language>pt-PT</language>'
        f"{item('<description>Texto.</description>')}</channel></rss>"
    )
    (raw,) = parse_feed(feed.encode("utf-8"), "feed_sintetico", FETCHED)
    assert lang_of(raw.raw_content) is None


def test_other_language_declarations_are_not_used():
    raw = item(
        '<dc:language xmlns:dc="http://purl.org/dc/elements/1.1/">pt</dc:language>'
        "<description>T.</description>"
    )
    assert lang_of(raw) is None
