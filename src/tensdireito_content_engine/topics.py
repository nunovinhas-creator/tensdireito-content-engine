"""Mapa de apoios (`config/apoios.yaml`): áreas temáticas e guias do tensdireito.com.

DEC-058. Funções puras sobre o YAML: identificam as áreas de um texto (para as
etiquetas das issues) e o guia do tensdireito.com referido num título (para o
"Saiba mais" dos rascunhos). Correspondência por palavra inteira, sem diacríticos.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

TOPICS_FILENAME = "apoios.yaml"
_PARENTHESES = re.compile(r"\(([^)]*)\)")


@dataclass(frozen=True, slots=True)
class Area:
    id: str
    name: str
    terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Guide:
    url: str
    terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TopicMap:
    areas: tuple[Area, ...] = ()
    guides: tuple[Guide, ...] = ()

    def areas_for(self, text: str) -> tuple[Area, ...]:
        """Áreas com pelo menos um termo presente em `text`, pela ordem do YAML."""
        folded = fold(text)
        return tuple(area for area in self.areas if any(contains(folded, t) for t in area.terms))

    def guide_for(self, title: str) -> str | None:
        """URL do primeiro guia cujo termo aparece no título, ou `None`."""
        folded = fold(title)
        for guide in self.guides:
            if any(contains(folded, term) for term in guide.terms):
                return guide.url
        return None


def load_topic_map(path: Path) -> TopicMap:
    """Lê `apoios.yaml`; devolve um mapa vazio se o ficheiro não existir."""
    path = Path(path)
    if not path.is_file():
        return TopicMap()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    areas = []
    for area_id, area in (data.get("areas") or {}).items():
        terms: set[str] = set()
        for name in area.get("apoios") or ():
            terms.update(support_terms(str(name)))
        for term in [*(area.get("palavras_chave") or ()), *(area.get("pesquisas") or ())]:
            terms.add(fold(str(term)).strip())
        areas.append(
            Area(
                id=str(area_id),
                name=str(area.get("nome") or area_id),
                terms=tuple(sorted(t for t in terms if len(t) >= 3)),
            )
        )
    guides = [
        Guide(
            url=str(guide["url"]),
            terms=tuple(fold(str(t)).strip() for t in guide.get("termos") or () if str(t).strip()),
        )
        for guide in data.get("guias") or ()
        if str(guide.get("url", "")).startswith("https://")
    ]
    return TopicMap(areas=tuple(areas), guides=tuple(guides))


def support_terms(name: str) -> list[str]:
    """`Ação Social Escolar (ASE)` → `acao social escolar`, `ase`."""
    inside = [part.strip() for match in _PARENTHESES.findall(name) for part in match.split(",")]
    outside = _PARENTHESES.sub("", name).strip()
    terms = [fold(term).strip() for term in (outside, *inside)]
    return [term for term in terms if len(term) >= 3]


def contains(folded_text: str, folded_term: str) -> bool:
    """Palavra ou expressão inteira, com plural opcional (`lar` não casa com `largo`)."""
    pattern = rf"(?<!\w){re.escape(folded_term)}(?:s|es)?(?!\w)"
    return re.search(pattern, folded_text) is not None


def fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
