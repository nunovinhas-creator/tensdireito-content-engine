"""Pontuação lexical inicial para priorização editorial; não verifica factos."""

import re
import unicodedata
from dataclasses import dataclass

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
class EditorialScore:
    value: float
    components: tuple[tuple[str, int], ...]


def score_item(item: NormalizedItem) -> EditorialScore:
    """Calcula um score determinístico, sem inferir verificação ou aprovação."""
    text = _fold(f"{item.title}\n{item.text}")
    components = {
        name: _dimension_score(text, terms)
        for name, terms in _TERMS.items()
    }
    # Não há ainda histórico de eventos nem agrupamento de fontes para medir estas dimensões.
    components.update(novelty=0, interest=0)
    value = sum(components[name] * weight / 5 for name, weight in WEIGHTS.items())
    return EditorialScore(
        value=value,
        components=tuple((name, components[name]) for name in WEIGHTS),
    )


def _dimension_score(text: str, terms: tuple[str, ...]) -> int:
    matches = sum(1 for term in terms if _contains_term(text, term))
    if matches == 0:
        return 0
    return min(5, matches + 2)


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}\w*", text) is not None


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
