"""Identidade de conteúdo de um `NormalizedItem` (DATA_MODEL.md §2.1 `text_hash`, DEC-021).

O fingerprint é o SHA-256 (hex) do texto normalizado: base da deduplicação exacta
(`dedup.py`, DEC-022). Identifica a representação normalizada, não o acontecimento: não
é um `event_id` e não decide se dois itens pertencem ao mesmo `Event` (etapa CLUSTER).
"""

import hashlib

from tensdireito_content_engine.normalize.item import NormalizedItem


def fingerprint(item: NormalizedItem) -> str:
    """SHA-256 (hex, minúsculas) do texto normalizado codificado em UTF-8."""
    if not isinstance(item, NormalizedItem):
        raise TypeError(f"esperado NormalizedItem, recebido {type(item).__name__}")
    return text_fingerprint(item.text)


def text_fingerprint(text: str) -> str:
    """O mesmo fingerprint, sobre um texto já normalizado (`text_hash`; DEC-021, DEC-040 (7))."""
    if not isinstance(text, str):
        raise TypeError(f"esperado str, recebido {type(text).__name__}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
