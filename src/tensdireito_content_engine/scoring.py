"""Pontuação lexical inicial para priorização editorial; não verifica factos."""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

from tensdireito_content_engine.normalize import NormalizedItem

WEIGHTS = {
    "impact": 30,
    "reach": 20,
    "actionability": 20,
    "urgency": 15,
    "novelty": 10,
    "interest": 5,
}

_TERMS = {
    "impact": (
        "altera",
        "aumenta",
        "reduz",
        "novo",
        "nova",
        "cria",
        "entra em vigor",
        "termina",
    ),
    "reach": (
        "trabalhadores",
        "desempregados",
        "familias",
        "pensionistas",
        "contribuintes",
        "beneficiarios",
        "cidadaos",
    ),
    "actionability": (
        "pedir",
        "requerer",
        "candidatura",
        "inscricao",
        "entregar",
        "prazo",
        "direito",
        "apoio",
        "prestacao",
        "subsidio",
    ),
    "urgency": (
        "prazo",
        "ate ",
        "a partir de",
        "entra em vigor",
        "termina em",
        "dias uteis",
    ),
}


@dataclass(frozen=True, slots=True)
class TopicTerms:
    """Termos de `config/apoios.yaml`, já normalizados (DEC-056).

    `keywords`: palavras-chave, nomes de apoios e pesquisas de todas as áreas.
    `named_supports`: nomes de apoios e pesquisas, procurados só no título.
    """

    keywords: tuple[str, ...] = ()
    named_supports: tuple[str, ...] = ()


_PARENTHESES = re.compile(r"\(([^)]*)\)")


def load_topic_terms(path: Path) -> TopicTerms:
    """Lê `apoios.yaml`; devolve termos vazios se o ficheiro não existir."""
    path = Path(path)
    if not path.is_file():
        return TopicTerms()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    keywords: set[str] = set()
    named: set[str] = set()
    for area in (data.get("areas") or {}).values():
        for name in area.get("apoios") or ():
            for term in _support_terms(str(name)):
                named.add(term)
        for term in area.get("pesquisas") or ():
            folded = _fold(str(term)).strip()
            if len(folded) >= 3:
                named.add(folded)
        for term in area.get("palavras_chave") or ():
            folded = _fold(str(term)).strip()
            if len(folded) >= 3:
                keywords.add(folded)
    keywords |= named
    return TopicTerms(keywords=tuple(sorted(keywords)), named_supports=tuple(sorted(named)))


def _support_terms(name: str) -> list[str]:
    """`Ação Social Escolar (ASE)` → `acao social escolar`, `ase`."""
    inside = [part.strip() for match in _PARENTHESES.findall(name) for part in match.split(",")]
    outside = _PARENTHESES.sub("", name).strip()
    terms = [_fold(term).strip() for term in (outside, *inside)]
    return [term for term in terms if len(term) >= 3]


@dataclass(frozen=True, slots=True)
class EditorialScore:
    value: float
    components: tuple[tuple[str, int], ...]


def score_item(item: NormalizedItem, topics: TopicTerms | None = None) -> EditorialScore:
    """Calcula um score determinístico, sem inferir verificação ou aprovação."""
    text = _fold(f"{item.title}\n{item.text}")
    components = {name: _dimension_score(text, terms) for name, terms in _TERMS.items()}
    # DEC-056: sem histórico de eventos nem agrupamento, `interest` e `novelty` usam
    # provisoriamente o mapa de apoios: termos do tema no texto e apoio nomeado no título.
    topics = topics or TopicTerms()
    title = _fold(item.title)
    components.update(
        novelty=_dimension_score(title, topics.named_supports, whole_word=True),
        interest=_dimension_score(text, topics.keywords, whole_word=True),
    )
    value = sum(components[name] * weight / 5 for name, weight in WEIGHTS.items())
    return EditorialScore(
        value=value,
        components=tuple((name, components[name]) for name in WEIGHTS),
    )


def _dimension_score(text: str, terms: tuple[str, ...], *, whole_word: bool = False) -> int:
    contains = _contains_word if whole_word else _contains_term
    matches = sum(1 for term in terms if contains(text, term))
    if matches == 0:
        return 0
    return min(5, matches + 2)


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}\w*", text) is not None


def _contains_word(text: str, term: str) -> bool:
    """Palavra ou expressão inteira, com plural opcional (`lar` não casa com `largo`)."""
    return re.search(rf"(?<!\w){re.escape(term)}(?:s|es)?(?!\w)", text) is not None


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
