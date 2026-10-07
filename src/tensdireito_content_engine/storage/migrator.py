"""Executor de migrações SQL numeradas, só para a frente (DEC-026; ROADMAP.md M2.6).

- As migrações são ficheiros `NNNN_<nome>.sql` em `storage/migrations/`, lidos como
  recursos do pacote e aplicados por ordem numérica.
- Cada migração é aplicada numa transacção, juntamente com o seu registo em
  `schema_migration` (`version`, `checksum` SHA-256 do ficheiro, `applied_at` UTC);
  qualquer falha faz rollback completo dessa migração.
- Uma migração aplicada nunca é reaplicada: checksum diferente do registado, versão
  registada que o código não conhece, ou migração pendente anterior a uma já
  aplicada, são erros.
- Não usa `PRAGMA user_version` (específico de SQLite).
"""

import hashlib
import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from importlib.resources.abc import Traversable

from tensdireito_content_engine.storage.database import to_utc_iso
from tensdireito_content_engine.storage.errors import StorageError

MIGRATION_TABLE = "schema_migration"
_FILENAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str  # nome do ficheiro sem extensão, ex.: `0001_init`
    sql: str
    checksum: str  # SHA-256 (hex) dos bytes do ficheiro


def default_migrations_dir() -> Traversable:
    return files("tensdireito_content_engine.storage") / "migrations"


def load_migrations(directory: Traversable | None = None) -> list[Migration]:
    """Lê as migrações do directório, ordenadas por versão.

    Ficheiros `.sql` com nome fora do formato `NNNN_<nome>.sql`, versões repetidas
    e a versão `0000` são erros. Outros ficheiros são ignorados.
    """
    directory = default_migrations_dir() if directory is None else directory
    migrations: dict[int, Migration] = {}
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if not entry.is_file() or not entry.name.endswith(".sql"):
            continue
        match = _FILENAME.match(entry.name)
        if match is None:
            raise StorageError(f"nome de migração inválido: {entry.name}")
        version = int(match["version"])
        if version == 0:
            raise StorageError(f"versão de migração inválida: {entry.name}")
        if version in migrations:
            raise StorageError(f"versão de migração repetida: {entry.name}")
        data = entry.read_bytes()
        try:
            sql = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StorageError(f"migração {entry.name} não está em UTF-8") from exc
        migrations[version] = Migration(
            version=version,
            name=entry.name.removesuffix(".sql"),
            sql=sql,
            checksum=hashlib.sha256(data).hexdigest(),
        )
    return [migrations[version] for version in sorted(migrations)]


def applied_migrations(conn: sqlite3.Connection) -> dict[int, str]:
    """Versões registadas em `schema_migration` e respectivos checksums."""
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (MIGRATION_TABLE,),
        ).fetchone()
        if exists is None:
            return {}
        rows = conn.execute(
            f"SELECT version, checksum FROM {MIGRATION_TABLE} ORDER BY version"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise StorageError(f"não foi possível ler {MIGRATION_TABLE}: {exc}") from exc
    return {int(version): checksum for version, checksum in rows}


def pending_migrations(applied: dict[int, str], migrations: Iterable[Migration]) -> list[Migration]:
    """Verifica as migrações aplicadas contra as conhecidas e devolve as pendentes."""
    known = {migration.version: migration for migration in migrations}
    for version, checksum in sorted(applied.items()):
        migration = known.get(version)
        if migration is None:
            raise StorageError(
                f"a base de dados tem a migração {version:04d}, desconhecida desta versão "
                "do código (base de dados mais recente que o código)"
            )
        if migration.checksum != checksum:
            raise StorageError(
                f"a migração {migration.name} foi alterada depois de aplicada "
                "(checksum diferente do registado)"
            )
    pending = [known[version] for version in sorted(known) if version not in applied]
    if pending and applied and pending[0].version < max(applied):
        raise StorageError(
            f"a migração {pending[0].name} está pendente mas é anterior a uma migração já aplicada"
        )
    return pending


def apply_migration(
    conn: sqlite3.Connection, migration: Migration, now: Callable[[], datetime]
) -> None:
    """Aplica uma migração e regista-a numa única transacção; falha → rollback."""
    conn.execute("BEGIN")
    try:
        for statement in split_statements(migration.sql):
            conn.execute(statement)
        conn.execute(
            f"INSERT INTO {MIGRATION_TABLE} (version, checksum, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.checksum, to_utc_iso(now())),
        )
    except sqlite3.Error as exc:
        conn.execute("ROLLBACK")
        raise StorageError(f"a migração {migration.name} falhou: {exc}") from exc
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migrate(
    conn: sqlite3.Connection,
    migrations: list[Migration],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[Migration]:
    """Aplica as migrações pendentes, por ordem; devolve as aplicadas nesta execução."""
    pending = pending_migrations(applied_migrations(conn), migrations)
    for migration in pending:
        apply_migration(conn, migration, now)
    return pending


def split_statements(sql: str) -> list[str]:
    """Divide um script SQL em instruções completas.

    Usa `sqlite3.complete_statement`, que respeita literais e comentários, em vez
    de `executescript` (que faz COMMIT implícito e quebraria a transacção).
    """
    statements: list[str] = []
    buffer = ""
    for char in sql:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if _has_code(statement):
                statements.append(statement)
            buffer = ""
    if _has_code(buffer):
        raise StorageError("instrução SQL incompleta no fim da migração")
    return statements


def _has_code(text: str) -> bool:
    """Verdadeiro se o texto tiver algo além de espaços, comentários e `;`."""
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", "", without_block)
    return without_line.replace(";", "").strip() != ""
