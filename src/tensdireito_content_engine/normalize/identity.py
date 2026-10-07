"""Identidade de conteúdo de um `NormalizedItem` (DATA_MODEL.md §2.1 `text_hash`, DEC-021).

O fingerprint é o SHA-256 (hex) do texto normalizado: base para a futura deduplicação
exacta. Identifica a representação normalizada, não o acontecimento: não é um `event_id`
e não decide se dois itens pertencem ao mesmo `Event` (etapa CLUSTER).
"""

import hashlib

from tensdireito_content_engine.normalize.item import NormalizedItem


def fingerprint(item: NormalizedItem) -> str:
    """SHA-256 (hex, minúsculas) do texto normalizado codificado em UTF-8."""
    if not isinstance(item, NormalizedItem):
        raise TypeError(f"esperado NormalizedItem, recebido {type(item).__name__}")
    return hashlib.sha256(item.text.encode("utf-8")).hexdigest()
