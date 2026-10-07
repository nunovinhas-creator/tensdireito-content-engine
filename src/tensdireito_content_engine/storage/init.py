"""`tde init`: cria a base de dados e aplica as migrações pendentes (ROADMAP.md M2.6).

Escreve só o esquema: não cria nenhum `run` nem registo de negócio, não sincroniza
`config/sources.yaml` e não acede à rede.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources.abc import Traversable
from pathlib import Path

from tensdireito_content_engine.storage.database import connect
from tensdireito_content_engine.storage.migrator import load_migrations, migrate


@dataclass(frozen=True, slots=True)
class InitResult:
    path: Path
    applied: tuple[str, ...]  # nomes das migrações aplicadas nesta execução


def init_database(
    path: Path,
    migrations_dir: Traversable | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> InitResult:
    """Cria a base de dados (se não existir) e aplica as migrações pendentes.

    Idempotente: sem migrações pendentes, não altera nada. Erros → `StorageError`.
    """
    migrations = load_migrations(migrations_dir)
    conn = connect(path)
    try:
        applied = migrate(conn, migrations, now)
    finally:
        conn.close()
    return InitResult(path=path, applied=tuple(migration.name for migration in applied))
