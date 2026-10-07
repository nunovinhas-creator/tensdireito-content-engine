"""Extracção de texto e língua de itens `rss` (ROADMAP.md M2.11; DEC-040, DEC-038).

Função pura de `raw_content` (o `<item>` serializado pelo collector `rss`, DEC-032) para
o texto extraído e normalizado (ou nenhum) e a língua declarada (ou nenhuma). Só a
biblioteca padrão, sem rede; `raw_content` não é alterado.

- XML: uma primeira passagem com Expat recusa qualquer `DOCTYPE` antes de se processarem
  entidades (DEC-033 §10); só depois `xml.etree.ElementTree` constrói o elemento, cuja
  raiz tem de ser `item`, sem namespace.
- Candidatos: `content:encoded`, pelo URI do namespace e nunca pelo prefixo (a
  serialização do M2.9 reescreve-o, ex.: `ns0:`), e `description`, sem namespace; o
  primeiro filho directo de cada um. Um candidato existe quando o seu texto, sem HTML e
  normalizado (DEC-021), não é vazio; `content:encoded` prevalece e os dois nunca se
  concatenam. Sem candidato, não há texto: o título nunca o substitui.
- HTML: `html.parser`, com entidades convertidas; `script`/`style`, comentários,
  declarações e instruções de processamento descartados; as etiquetas da lista fechada
  de DEC-040 separam linhas e as restantes são removidas sem separador; atributos não
  produzem texto.
- Língua: `xml:lang` efectiva do elemento escolhido (o seu, senão o do `<item>`; sem
  elemento escolhido, o do `<item>`), reduzida à subetiqueta primária em minúsculas
  quando tem 2 ou 3 letras ASCII; senão nula. Nunca presumida (DEC-038).
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from xml.parsers import expat

from tensdireito_content_engine.normalize.text import normalize_text

CONTENT_NAMESPACE = "http://purl.org/rss/1.0/modules/content/"
_CONTENT_ENCODED = f"{{{CONTENT_NAMESPACE}}}encoded"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_PRIMARY_SUBTAG = re.compile(r"[A-Za-z]{2,3}")

# Etiquetas cujo início e fim são substituídos por uma quebra de linha (DEC-040 (4)).
BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
_DISCARDED_CONTENT = frozenset({"script", "style"})


class RawContentError(Exception):
    """`raw_content` ilegível; mensagem determinista, sem o conteúdo (DEC-040 (2))."""


class _DoctypeFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RssExtraction:
    text: str | None  # normalizado (DEC-021); nulo = sem texto útil
    language: str | None  # subetiqueta primária em minúsculas; nulo = desconhecida


def extract_rss_item(raw_content: str) -> RssExtraction:
    """Texto e língua de um `<item>` RSS. XML ilegível → `RawContentError`."""
    item = _parse_item(raw_content)
    for candidate in (_first_child(item, _CONTENT_ENCODED), _first_child(item, "description")):
        if candidate is None:
            continue
        text = html_to_text("".join(candidate.itertext()))
        if text:
            lang = candidate.get(_XML_LANG)
            return RssExtraction(text=text, language=primary_language(lang, item))
    return RssExtraction(text=None, language=primary_language(None, item))


def html_to_text(html: str) -> str:
    """Remove o HTML (DEC-040 (4)) e normaliza o texto (DEC-021)."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return normalize_text("".join(parser.parts))


def primary_language(element_lang: str | None, item: ET.Element) -> str | None:
    """`xml:lang` efectiva → subetiqueta primária em minúsculas, ou `None` (DEC-038 (2))."""
    declared = element_lang if element_lang is not None else item.get(_XML_LANG)
    if declared is None:
        return None
    primary = declared.split("-", 1)[0]
    if not _PRIMARY_SUBTAG.fullmatch(primary):
        return None
    return primary.lower()


def _parse_item(raw_content: str) -> ET.Element:
    _reject_doctype(raw_content)
    try:
        root = ET.fromstring(raw_content)
    except ET.ParseError as exc:
        raise RawContentError(f"XML malformado: {exc}") from None
    if root.tag != "item":
        raise RawContentError(f"raiz não suportada: {root.tag}")
    return root


def _reject_doctype(raw_content: str) -> None:
    parser = expat.ParserCreate()

    def on_doctype(*_args: object) -> None:
        raise _DoctypeFound

    parser.StartDoctypeDeclHandler = on_doctype
    try:
        parser.Parse(raw_content, True)
    except _DoctypeFound:
        raise RawContentError("DOCTYPE não permitido") from None
    except expat.ExpatError as exc:
        raise RawContentError(f"XML malformado: {exc}") from None
    except (LookupError, UnicodeError) as exc:
        raise RawContentError(f"XML malformado: {exc}") from None


def _first_child(item: ET.Element, tag: str) -> ET.Element | None:
    """Primeiro filho directo com a etiqueta exacta (nome local e namespace)."""
    for child in item:
        if child.tag == tag:
            return child
    return None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._discarding: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._discarding is not None:
            return
        if tag in _DISCARDED_CONTENT:
            self._discarding = tag
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Uma etiqueta vazia (`<br/>`) é uma só etiqueta: uma quebra, não duas.
        if self._discarding is None and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._discarding is not None:
            if tag == self._discarding:
                self._discarding = None
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._discarding is None:
            self.parts.append(data)
