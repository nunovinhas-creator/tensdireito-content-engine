"""Testes estruturais do M2.6: isolamento da camada SQL e portabilidade das migrações.

Verificam o código e os ficheiros de migração, sem PostgreSQL real (ROADMAP.md M2.6,
critérios 5 e 6; DEC-013).
"""

import ast
import re
import sqlite3
from pathlib import Path

import pytest

import tensdireito_content_engine
from tensdireito_content_engine.storage.migrator import default_migrations_dir

PACKAGE_DIR = Path(tensdireito_content_engine.__file__).parent
STORAGE_DIR = PACKAGE_DIR / "storage"
MIGRATIONS_DIR = Path(str(default_migrations_dir()))
ISOLATED_LAYERS = ("domain", "normalize", "sources", "collectors")
MIGRATION_FILES = sorted(MIGRATIONS_DIR.glob("*.sql"))


def imported_modules(path: Path) -> set[str]:
    """Módulos importados por um ficheiro, com imports relativos resolvidos."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = ".".join(path.relative_to(PACKAGE_DIR.parent).with_suffix("").parts[:-1])
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                prefix = ".".join(base)
                module = f"{prefix}.{node.module}" if node.module else prefix
            else:
                module = node.module or ""
            modules.add(module)
            modules.update(f"{module}.{alias.name}" for alias in node.names)
    return modules


def python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


@pytest.mark.parametrize("layer", ISOLATED_LAYERS)
def test_layer_does_not_import_storage_or_sqlite(layer):
    files = python_files(PACKAGE_DIR / layer)
    assert files
    for path in files:
        for module in imported_modules(path):
            assert not module.startswith("tensdireito_content_engine.storage"), (path, module)
            assert module.split(".")[0] != "sqlite3", (path, module)


def test_sqlite3_only_imported_in_storage():
    for path in python_files(PACKAGE_DIR):
        if STORAGE_DIR in path.parents:
            continue
        for module in imported_modules(path):
            assert module.split(".")[0] != "sqlite3", (path, module)


def test_storage_only_depends_on_itself_within_package():
    for path in python_files(STORAGE_DIR):
        for module in imported_modules(path):
            if module.startswith("tensdireito_content_engine."):
                layer = module.split(".")[1]
                assert layer in {"storage", "domain"}, (path, module)


def test_no_sql_outside_storage():
    sql = re.compile(r"\b(CREATE\s+TABLE|INSERT\s+INTO|SELECT\s+.+\s+FROM)\b", re.IGNORECASE)
    for path in python_files(PACKAGE_DIR):
        if STORAGE_DIR in path.parents:
            continue
        assert not sql.search(path.read_text(encoding="utf-8")), path


# --- Portabilidade --------------------------------------------------------------

FORBIDDEN = {
    "AUTOINCREMENT": r"\bAUTOINCREMENT\b",
    "WITHOUT ROWID": r"\bWITHOUT\s+ROWID\b",
    "STRICT": r"\bSTRICT\b",
    "INSERT OR REPLACE": r"\bINSERT\s+OR\s+REPLACE\b",
    "PRAGMA": r"\bPRAGMA\b",
    "CURRENT_TIMESTAMP": r"\bCURRENT_TIMESTAMP\b",
    "user_version": r"\buser_version\b",
}


def sql_without_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL))


def test_there_are_migration_files():
    assert [path.name for path in MIGRATION_FILES] == ["0001_init.sql"]


@pytest.mark.parametrize("path", MIGRATION_FILES, ids=lambda path: path.name)
@pytest.mark.parametrize("construct", sorted(FORBIDDEN))
def test_migrations_avoid_sqlite_only_constructs(path, construct):
    code = sql_without_comments(path.read_text(encoding="utf-8"))
    assert not re.search(FORBIDDEN[construct], code, re.IGNORECASE)


@pytest.mark.parametrize("path", MIGRATION_FILES, ids=lambda path: path.name)
def test_migrations_avoid_other_sqlite_only_defaults(path):
    code = sql_without_comments(path.read_text(encoding="utf-8"))
    for pattern in (r"\bCURRENT_DATE\b", r"\bCURRENT_TIME\b", r"\bdatetime\s*\(", r"\bDEFAULT\b"):
        assert not re.search(pattern, code, re.IGNORECASE), pattern


@pytest.fixture(scope="module")
def schema(tmp_path_factory) -> dict[str, dict[str, str]]:
    db = tmp_path_factory.mktemp("schema") / "tde.sqlite3"
    conn = sqlite3.connect(db)
    try:
        for path in MIGRATION_FILES:
            conn.executescript(path.read_text(encoding="utf-8"))
        names = [
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            name: {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({name})")}
            for name in names
        }
    finally:
        conn.close()


def test_column_types_are_portable(schema):
    for table, cols in schema.items():
        for column, ctype in cols.items():
            assert ctype in {"TEXT", "INTEGER", "REAL"}, (table, column, ctype)


JSON_COLUMNS = {
    ("run", "stats"),
    ("source_registry", "categories"),
    ("source_registry", "domains"),
    ("source_endpoint", "fetch"),
}
DATE_COLUMNS = {
    ("schema_migration", "applied_at"),
    ("run", "started_at"),
    ("run", "finished_at"),
    ("source_registry", "validated_at"),
    ("source_endpoint", "validated_at"),
    ("source_endpoint", "last_success_at"),
    ("raw_item", "fetched_at"),
} | {
    (table, column)
    for table in ("run", "source_registry", "source_endpoint", "raw_item")
    for column in ("created_at", "updated_at")
}


@pytest.mark.parametrize(("table", "column"), sorted(JSON_COLUMNS | DATE_COLUMNS))
def test_json_and_date_columns_are_text(schema, table, column):
    assert schema[table][column] == "TEXT"


def test_published_at_raw_kept_as_text(schema):
    assert schema["raw_item"]["published_at_raw"] == "TEXT"
