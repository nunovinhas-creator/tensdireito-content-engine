"""Prioridade editorial dos candidatos: alta, rever ou baixa (DEC-063, fase 1).

Substitui o limiar lexical de 65 como critério de exclusão. Nenhuma prioridade apaga
um candidato: todas ficam no relatório com o motivo, e só `alta` gera rascunho nesta
fase. `rever` fica à espera da classificação por IA (fase 3) e da revisão humana;
`baixa` fica arquivada, com uma amostra no resumo do run para auditoria.

Regras, por ordem:
1. o título contém um termo forte (apoio nomeado, pesquisa ou termo de `alta`) → alta;
2. a fonte é oficial (T1/T2) → rever (as fontes oficiais nunca ficam em baixa);
3. o título contém um termo ambíguo (palavra-chave ou termo de `rever`) → rever;
4. o resumo contém um termo forte → rever;
5. nada disto → baixa.

A correspondência é por palavra inteira, sem maiúsculas nem diacríticos, e aceita os
plurais portugueses de cada palavra (`pensão` → `pensões`, `social` → `sociais`).
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml

from tensdireito_content_engine.topics import fold, support_terms


class Priority(StrEnum):
    HIGH = "alta"
    REVIEW = "rever"
    LOW = "baixa"


OFFICIAL_TIERS = frozenset({"T1", "T2"})

# Termos que, no título, chegam para considerar a notícia sobre apoios ou direitos.
DEFAULT_HIGH_TERMS = (
    "subsidio",
    "prestacao",
    "prestacao social",
    "psu",
    "apoio social",
    "apoio extraordinario",
    "abono",
    "pensao",
    "pensionista",
    "reformado",
    "aposentacao",
    "caixa geral de aposentacoes",
    "seguranca social",
    "rendimento social de insercao",
    "rsi",
    "complemento solidario para idosos",
    "irs",
    "salario minimo",
    "iefp",
    "bolsa de estudo",
    "propina",
    "creche gratuita",
    "manuais escolares",
    "acao social escolar",
    "tarifa social",
    "porta 65",
    "apoio a renda",
    "cuidador informal",
    "baixa medica",
    "licenca parental",
    "adse",
    "cheque-dentista",
    "taxas moderadoras",
    "beneficiario",
    "indexante dos apoios sociais",
)

# Termos que, no título, justificam análise mas não chegam para a prioridade alta.
DEFAULT_REVIEW_TERMS = (
    "apoio",
    "medida",
    "orcamento do estado",
    "oe2026",
    "oe2027",
    "oe2028",
    "portaria",
    "decreto-lei",
    "despacho",
    "conselho de ministros",
    "proposta de lei",
    "projeto de lei",
    "ministra do trabalho",
    "ministro do trabalho",
    "ministerio do trabalho",
    "salario",
    "renda",
    "custo de vida",
    "credito habitacao",
    "inflacao",
    "candidatura",
    "prazo",
    "pagamento",
    "desemprego",
    "reforma",
)


@dataclass(frozen=True, slots=True)
class PriorityTerms:
    """Termos já normalizados (`fold`)."""

    high: tuple[str, ...]
    review: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PriorityDecision:
    level: Priority
    reason: str


def load_priority_terms(path: Path) -> PriorityTerms:
    """Predefinições + `config/apoios.yaml` (apoios e pesquisas → alta; palavras-chave → rever).

    A secção opcional `prioridade: {alta: [...], rever: [...]}` acrescenta termos. Um termo
    que esteja nas duas listas conta como alta. Sem ficheiro, ficam só as predefinições.
    """
    high: set[str] = {fold(term) for term in DEFAULT_HIGH_TERMS}
    review: set[str] = {fold(term) for term in DEFAULT_REVIEW_TERMS}
    path = Path(path)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for area in (data.get("areas") or {}).values():
            for name in area.get("apoios") or ():
                # O nome completo é forte; os apelidos entre parênteses (PSI, MEGA,
                # "jovens", "declaração") colidem com outros sentidos e ficam em rever.
                full, *aliases = support_terms(str(name))
                high.add(full)
                review.update(aliases)
            high.update(_folded(area.get("pesquisas")))
            review.update(_folded(area.get("palavras_chave")))
        section = data.get("prioridade") or {}
        high.update(_folded(section.get("alta")))
        review.update(_folded(section.get("rever")))
    high = {term for term in high if len(term) >= 3}
    review = {term for term in review if len(term) >= 3} - high
    return PriorityTerms(high=tuple(sorted(high)), review=tuple(sorted(review)))


def classify(title: str, text: str, tier: str | None, terms: PriorityTerms) -> PriorityDecision:
    """Decide a prioridade de um candidato e devolve o motivo legível."""
    folded_title = fold(title)
    if term := _first_match(folded_title, terms.high):
        return PriorityDecision(Priority.HIGH, f"título refere «{term}»")
    if tier in OFFICIAL_TIERS:
        return PriorityDecision(Priority.REVIEW, f"fonte oficial ({tier})")
    if term := _first_match(folded_title, terms.review):
        return PriorityDecision(Priority.REVIEW, f"título ambíguo: «{term}»")
    if term := _first_match(fold(text), terms.high):
        return PriorityDecision(Priority.REVIEW, f"resumo refere «{term}»")
    return PriorityDecision(Priority.LOW, "sem termos de apoios no título nem no resumo")


def _folded(values: object) -> set[str]:
    if not isinstance(values, list | tuple):
        return set()
    return {fold(str(value)).strip() for value in values if str(value).strip()}


def _first_match(folded_text: str, terms: tuple[str, ...]) -> str | None:
    # Termos mais longos primeiro, para o motivo citar a expressão mais específica.
    for term in sorted(terms, key=lambda t: (-len(t), t)):
        if _pattern(term).search(folded_text):
            return term
    return None


@lru_cache(maxsize=4096)
def _pattern(term: str) -> re.Pattern[str]:
    words = [_word_variants(word) for word in term.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)")


def _word_variants(word: str) -> str:
    """Forma singular e plurais portugueses da palavra, já sem diacríticos."""
    variants = {word, word + "s", word + "es"}
    if word.endswith("ao"):
        stem = word[:-2]
        variants |= {stem + "oes", stem + "aes", stem + "aos"}
    elif word.endswith(("al", "el", "ol", "ul")):
        variants.add(word[:-1] + "is")
    elif word.endswith("il"):
        variants |= {word[:-2] + "is", word[:-1] + "eis"}
    elif word.endswith("m"):
        variants.add(word[:-1] + "ns")
    return "(?:" + "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)) + ")"
