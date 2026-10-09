"""Localização e ligação à base de dados SQLite local (ROADMAP.md M2.6; DEC-026).

Toda a configuração da ligação vive aqui: cada ligação activa as chaves
estrangeiras (`PRAGMA foreign_keys = ON`) e controla as transacções de forma
explícita (`isolation_level=None`), para que cada migração seja uma transacção.
"""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.interfaces import Connection

DEFAULT_DB_PATH = Path("data") / "tde.sqlite3"
DB_PATH_ENV = "TDE_DB_PATH"

_SQLITE_HEADER = b"SQLite format 3\x00"


def resolve_db_path(option: Path | str | None, environ: Mapping[str, str]) -> Path:
    """Caminho da base de dados: `--db PATH`, senão `TDE_DB_PATH`, senão `data/tde.sqlite3`.

    Um valor vazio conta como ausente. Caminhos relativos são relativos ao
    directório de trabalho.
    """
    if option is not None and str(option) != "":
        return Path(option)
    from_env = environ.get(DB_PATH_ENV, "")
    if from_env != "":
        return Path(from_env)
    return DEFAULT_DB_PATH


def connect(path: Path) -> sqlite3.Connection:
    """Abre (e cria, se não existir) a base de dados em `path`.

    Cria o directório pai se faltar. Recusa um caminho que seja um directório ou
    um ficheiro que não seja uma base de dados SQLite.
    """
    path = Path(path)
    if path.is_dir():
        raise StorageError("o caminho da base de dados é um directório")
    if path.exists() and not _is_sqlite_file(path):
        raise StorageError("o ficheiro não é uma base de dados SQLite")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError(f"não foi possível criar o directório {path.parent}: {exc}") from exc
    try:
        conn = sqlite3.connect(path, isolation_level=None)
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível abrir a base de dados: {exc}") from exc
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise StorageError("o ficheiro não é uma base de dados SQLite") from exc
    return conn


@contextmanager
def transaction(conn: Connection, failure: str) -> Iterator[None]:
    """Transacção explícita (`BEGIN` … `COMMIT`); qualquer erro → `ROLLBACK`.

    Um erro SQLite é relançado como `StorageError` com o prefixo `failure`, encadeado
    com a excepção original.
    """
    try:
        conn.execute("BEGIN")
    except sqlite3.Error as exc:
        raise StorageError(f"{failure}: {exc}") from exc
    try:
        yield
        conn.execute("COMMIT")
    except sqlite3.Error as exc:
        conn.execute("ROLLBACK")
        raise StorageError(f"{failure}: {exc}") from exc
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def to_utc_iso(value: datetime) -> str:
    """Data com fuso → texto ISO 8601 em UTC com fuso explícito (`+00:00`)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("a data tem de ter fuso horário")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _is_sqlite_file(path: Path) -> bool:
    """Um ficheiro vazio é uma base SQLite vazia; senão exige o cabeçalho SQLite."""
    with path.open("rb") as handle:
        header = handle.read(len(_SQLITE_HEADER))
    return header == b"" or header == _SQLITE_HEADER
