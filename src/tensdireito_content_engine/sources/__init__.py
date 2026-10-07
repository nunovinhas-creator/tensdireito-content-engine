"""Registo de fontes: leitura e validação local de `config/sources.yaml` (M2.5).

Sem rede, sem recolha e sem persistência; os collectors pertencem a outra unidade.
"""

from tensdireito_content_engine.sources.registry import (
    LoadedSources,
    SourceRegistryError,
    load_sources,
    parse_sources,
)

__all__ = [
    "LoadedSources",
    "SourceRegistryError",
    "load_sources",
    "parse_sources",
]
