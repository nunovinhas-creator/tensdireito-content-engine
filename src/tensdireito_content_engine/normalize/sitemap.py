"""Extracção de uma entrada de news sitemap (`<url>` com `<news:news>`; DEC-069).

Um news sitemap não traz o corpo da notícia: o texto fica nulo (DEC-040, sem texto útil)
e a língua vem de `<news:publication><news:language>` quando é uma subetiqueta válida.
A extracção da página fica para a fase 3. XML ilegível → `RawContentError`.
"""

import xml.etree.ElementTree as ET

from tensdireito_content_engine.normalize.rss import (
    _PRIMARY_SUBTAG,
    RawContentError,
    RssExtraction,
    _reject_doctype,
)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_URL = f"{{{SITEMAP_NS}}}url"
_LANGUAGE = f"{{{NEWS_NS}}}news/{{{NEWS_NS}}}publication/{{{NEWS_NS}}}language"


def extract_sitemap_entry(raw_content: str) -> RssExtraction:
    _reject_doctype(raw_content)
    try:
        root = ET.fromstring(raw_content)
    except ET.ParseError as exc:
        raise RawContentError(f"XML malformado: {exc}") from None
    if root.tag != _URL:
        raise RawContentError(f"raiz não suportada: {root.tag}")
    element = root.find(_LANGUAGE)
    declared = "".join(element.itertext()).strip() if element is not None else ""
    primary = declared.split("-", 1)[0]
    language = primary.lower() if _PRIMARY_SUBTAG.fullmatch(primary) else None
    return RssExtraction(text=None, language=language)
