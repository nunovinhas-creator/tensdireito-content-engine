"""Deduplicação exacta de `NormalizedItem` por `text_hash` (M2.4, DEC-022).

Dois itens são duplicados exactos quando têm o mesmo fingerprint (`text_hash`,
DEC-021), isto é, o mesmo texto normalizado. Não há similaridade, deduplicação
aproximada nem agrupamento em `Event` (etapa CLUSTER).

Regra do representante (técnica, sem significado editorial): em cada grupo com o
mesmo `text_hash`, o representante é o primeiro item na ordem da sequência de
entrada; os restantes são duplicados desse representante. A mesma sequência dá
sempre o mesmo resultado. Os itens de entrada não são alterados, fundidos nem
descartados: todos aparecem no resultado, como representante ou como duplicado.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from tensdireito_content_engine.normalize.identity import fingerprint
from tensdireito_content_engine.normalize.item import NormalizedItem


@dataclass(frozen=True, slots=True, kw_only=True)
class ExactDuplicate:
    item: NormalizedItem
    duplicate_of: NormalizedItem  # representante do grupo (DATA_MODEL.md §2.1 `duplicate_of`)
    text_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DeduplicationResult:
    representatives: tuple[NormalizedItem, ...]  # um por `text_hash`, na ordem de entrada
    duplicates: tuple[ExactDuplicate, ...]  # na ordem de entrada


def deduplicate_exact(items: Iterable[NormalizedItem]) -> DeduplicationResult:
    """Separa representantes e duplicados exactos por `text_hash`. Sem efeitos laterais."""
    seen: dict[str, NormalizedItem] = {}
    representatives: list[NormalizedItem] = []
    duplicates: list[ExactDuplicate] = []
    for item in items:
        if not isinstance(item, NormalizedItem):
            raise TypeError(f"esperado NormalizedItem, recebido {type(item).__name__}")
        text_hash = fingerprint(item)
        representative = seen.get(text_hash)
        if representative is None:
            seen[text_hash] = item
            representatives.append(item)
        else:
            duplicates.append(
                ExactDuplicate(item=item, duplicate_of=representative, text_hash=text_hash)
            )
    return DeduplicationResult(representatives=tuple(representatives), duplicates=tuple(duplicates))
