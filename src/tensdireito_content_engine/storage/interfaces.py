"""Interfaces comuns da camada de persistência.

O contrato exposto aos repositórios não depende do tipo concreto do driver.
O adaptador SQLite actual continua a ser responsável pelas suas ligações,
erros, migrações e dialecto SQL.
"""

from collections.abc import Sequence
from typing import Protocol


class Cursor(Protocol):
    """Resultados mínimos usados pelos repositórios."""

    @property
    def lastrowid(self) -> int | None: ...

    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


class Connection(Protocol):
    """Operações comuns de uma ligação usadas pela camada de repositórios."""

    def execute(self, sql: str, parameters: Sequence[object] = ()) -> Cursor: ...

    def close(self) -> None: ...
