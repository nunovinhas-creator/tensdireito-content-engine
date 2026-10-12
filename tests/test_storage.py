"""Testes do M2.6: storage SQLite, migrações e `tde init` (ROADMAP.md M2.6).

Offline: bases de dados em directórios temporários, sem rede e sem IA. Nenhum teste
escreve em `data/` do repositório (o caso do caminho por defeito corre em `tmp_path`).
"""

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tensdireito_content_engine.cli import main
from tensdireito_content_engine.storage import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    StorageError,
    connect,
    init_database,
    load_migrations,
    resolve_db_path,
    to_utc_iso,
)
from tensdireito_content_engine.storage.migrator import default_migrations_dir, split_statements

FIXED_NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
MIGRATIONS_DIR = Path(str(default_migrations_dir()))
BUSINESS_TABLES = {
    "run",
    "source_registry",
    "source_endpoint",
    "raw_item",
    "source_document",
    "whatsapp_draft",
    "candidate",
    "candidate_group",
    "candidate_discovery",
    "candidate_transition",
}
ALL_TABLES = {"schema_migration", *BUSINESS_TABLES}


def fixed_now() -> datetime:
    return FIXED_NOW


def tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {name for (name,) in rows}


def schema_sql(path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()


def migration_rows(path: Path) -> list[tuple[int, str, str]]:
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT version, checksum, applied_at FROM schema_migration ORDER BY version"
        ).fetchall()


def columns(path: Path, table: str) -> dict[str, tuple[str, bool, int]]:
    """nome → (tipo declarado, NOT NULL, posição na PK)."""
    with sqlite3.connect(path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {name: (ctype, bool(notnull), pk) for _, name, ctype, notnull, _, pk in rows}


def write_migrations(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, sql in files.items():
        (directory / name).write_text(sql, encoding="utf-8")
    return directory


FAKE_0001 = (
    "CREATE TABLE schema_migration (version INTEGER NOT NULL PRIMARY KEY, "
    "checksum TEXT NOT NULL, applied_at TEXT NOT NULL);\n"
    "CREATE TABLE alpha (id INTEGER NOT NULL PRIMARY KEY);\n"
)
FAKE_0002 = "CREATE TABLE beta (id INTEGER NOT NULL PRIMARY KEY);\n"
FAKE_0003 = "CREATE TABLE gamma (id INTEGER NOT NULL PRIMARY KEY);\n"


# --- Caminho da base de dados -------------------------------------------------


def test_resolve_db_path_option_wins_over_env():
    env = {DB_PATH_ENV: "env.sqlite3"}
    assert resolve_db_path(Path("opt.sqlite3"), env) == Path("opt.sqlite3")


def test_resolve_db_path_env_when_no_option():
    assert resolve_db_path(None, {DB_PATH_ENV: "env.sqlite3"}) == Path("env.sqlite3")


def test_resolve_db_path_default():
    assert resolve_db_path(None, {}) == Path("data/tde.sqlite3")
    assert DEFAULT_DB_PATH == Path("data/tde.sqlite3")


def test_resolve_db_path_empty_values_count_as_absent():
    assert resolve_db_path("", {DB_PATH_ENV: ""}) == DEFAULT_DB_PATH
    assert resolve_db_path("", {DB_PATH_ENV: "env.sqlite3"}) == Path("env.sqlite3")


def test_cli_init_uses_db_option_over_env(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "env" / "env.sqlite3"))
    assert main(["--db", str(tmp_path / "opt" / "opt.sqlite3"), "init"]) == 0
    assert (tmp_path / "opt" / "opt.sqlite3").is_file()
    assert not (tmp_path / "env").exists()
    assert not (tmp_path / "data").exists()
    assert capsys.readouterr().out.startswith(f"init: OK — {tmp_path / 'opt' / 'opt.sqlite3'}")


def test_cli_init_uses_env_when_no_option(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "env" / "env.sqlite3"))
    assert main(["init"]) == 0
    assert (tmp_path / "env" / "env.sqlite3").is_file()
    assert not (tmp_path / "data").exists()


def test_cli_init_default_path_creates_data_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DB_PATH_ENV, raising=False)
    assert main(["init"]) == 0
    assert (tmp_path / "data" / "tde.sqlite3").is_file()
    assert capsys.readouterr().out.splitlines()[0] == "init: OK — data/tde.sqlite3"


# --- tde init: criação inicial e idempotência --------------------------------


def test_cli_init_creates_database_and_reports(tmp_path, capsys):
    db = tmp_path / "nested" / "dir" / "tde.sqlite3"
    assert not db.parent.exists()
    assert main(["--db", str(db), "init"]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"init: OK — {db}",
        "migrações aplicadas: 0001_init, 0002_source_document, 0003_whatsapp_draft, "
        "0004_candidate",
    ]
    assert captured.err == ""
    assert db.is_file()
    assert tables(db) == ALL_TABLES


def test_init_registers_migrations_with_checksum(tmp_path):
    db = tmp_path / "tde.sqlite3"
    result = init_database(db, now=fixed_now)
    assert result.applied == (
        "0001_init",
        "0002_source_document",
        "0003_whatsapp_draft",
        "0004_candidate",
    )
    applied_at = "2026-10-07T12:00:00.000000+00:00"
    assert migration_rows(db) == [
        (
            1,
            hashlib.sha256((MIGRATIONS_DIR / "0001_init.sql").read_bytes()).hexdigest(),
            applied_at,
        ),
        (
            2,
            hashlib.sha256((MIGRATIONS_DIR / "0002_source_document.sql").read_bytes()).hexdigest(),
            applied_at,
        ),
        (
            3,
            hashlib.sha256((MIGRATIONS_DIR / "0003_whatsapp_draft.sql").read_bytes()).hexdigest(),
            applied_at,
        ),
        (
            4,
            hashlib.sha256((MIGRATIONS_DIR / "0004_candidate.sql").read_bytes()).hexdigest(),
            applied_at,
        ),
    ]


def test_business_tables_are_empty_after_init(tmp_path):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    with sqlite3.connect(db) as conn:
        for table in BUSINESS_TABLES:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)


def test_source_document_is_created_by_0002(tmp_path):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    assert "source_document" in tables(db)


def test_second_init_is_idempotent(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    assert main(["--db", str(db), "init"]) == 0
    schema_before = schema_sql(db)
    rows_before = migration_rows(db)
    capsys.readouterr()

    assert main(["--db", str(db), "init"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"init: OK — {db}",
        "migrações aplicadas: nenhuma",
    ]
    assert schema_sql(db) == schema_before
    assert migration_rows(db) == rows_before
    assert init_database(db).applied == ()


def test_init_accepts_existing_empty_file(tmp_path):
    db = tmp_path / "tde.sqlite3"
    db.touch()
    assert init_database(db).applied == (
        "0001_init",
        "0002_source_document",
        "0003_whatsapp_draft",
        "0004_candidate",
    )


# --- Esquema da 0001 e da 0002 ------------------------------------------------


EXPECTED_COLUMNS = {
    "schema_migration": {
        "version": ("INTEGER", True, 1),
        "checksum": ("TEXT", True, 0),
        "applied_at": ("TEXT", True, 0),
    },
    "run": {
        "id": ("INTEGER", True, 1),
        "command": ("TEXT", False, 0),
        "started_at": ("TEXT", False, 0),
        "finished_at": ("TEXT", False, 0),
        "status": ("TEXT", False, 0),
        "stats": ("TEXT", False, 0),
        "outcome": ("TEXT", False, 0),
        "report_path": ("TEXT", False, 0),
        "created_at": ("TEXT", True, 0),
        "updated_at": ("TEXT", True, 0),
    },
    "source_registry": {
        "id": ("TEXT", True, 1),
        "name": ("TEXT", True, 0),
        "entity_type": ("TEXT", True, 0),
        "tier": ("TEXT", True, 0),
        "categories": ("TEXT", True, 0),
        "domains": ("TEXT", True, 0),
        "registry_status": ("TEXT", True, 0),
        "validated_at": ("TEXT", False, 0),
        "validated_by": ("TEXT", False, 0),
        "notes": ("TEXT", False, 0),
        "created_at": ("TEXT", True, 0),
        "updated_at": ("TEXT", True, 0),
    },
    "source_endpoint": {
        "id": ("TEXT", True, 1),
        "source_id": ("TEXT", True, 0),
        "endpoint_type": ("TEXT", True, 0),
        "url": ("TEXT", False, 0),
        "fetch": ("TEXT", False, 0),
        "endpoint_status": ("TEXT", True, 0),
        "validated_at": ("TEXT", False, 0),
        "validated_by": ("TEXT", False, 0),
        "last_success_at": ("TEXT", False, 0),
        "last_error": ("TEXT", False, 0),
        "created_at": ("TEXT", True, 0),
        "updated_at": ("TEXT", True, 0),
    },
    "raw_item": {
        "id": ("INTEGER", True, 1),
        "source_endpoint_id": ("TEXT", False, 0),
        "url": ("TEXT", True, 0),
        "external_id": ("TEXT", False, 0),
        "title": ("TEXT", True, 0),
        "raw_content": ("TEXT", True, 0),
        "fetched_at": ("TEXT", True, 0),
        "published_at_raw": ("TEXT", False, 0),
        "content_hash": ("TEXT", True, 0),
        "manual_note": ("TEXT", False, 0),
        "created_in_run": ("INTEGER", False, 0),
        "created_at": ("TEXT", True, 0),
        "updated_at": ("TEXT", True, 0),
    },
    "source_document": {
        "id": ("INTEGER", True, 1),
        "raw_item_id": ("INTEGER", True, 0),
        "source_id": ("TEXT", False, 0),
        "canonical_url": ("TEXT", False, 0),
        "title": ("TEXT", True, 0),
        "text": ("TEXT", False, 0),
        "language": ("TEXT", False, 0),
        "published_at": ("TEXT", False, 0),
        "source_tier": ("TEXT", True, 0),
        "document_kind": ("TEXT", False, 0),
        "text_hash": ("TEXT", False, 0),
        "duplicate_of": ("INTEGER", False, 0),
        "status": ("TEXT", True, 0),
        "created_in_run": ("INTEGER", True, 0),
        "created_at": ("TEXT", True, 0),
        "updated_at": ("TEXT", True, 0),
    },
    "whatsapp_draft": {
        "id": ("INTEGER", True, 1),
        "raw_item_id": ("INTEGER", True, 0),
        "editorial_score": ("REAL", True, 0),
        "verification_status": ("TEXT", True, 0),
        "status": ("TEXT", True, 0),
        "message": ("TEXT", True, 0),
        "created_at": ("TEXT", True, 0),
        "updated_at": ("TEXT", True, 0),
        "approved_at": ("TEXT", False, 0),
        "candidate_id": ("INTEGER", False, 0),
    },
}


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "tde.sqlite3"
    init_database(path, now=fixed_now)
    return path


@pytest.mark.parametrize("table", sorted(EXPECTED_COLUMNS))
def test_table_columns_match_contract(db, table):
    assert columns(db, table) == EXPECTED_COLUMNS[table]


def test_only_expected_tables_exist(db):
    assert tables(db) == ALL_TABLES


def test_no_indexes_beyond_pk_unique_and_text_hash(db):
    with sqlite3.connect(db) as conn:
        explicit = conn.execute(
            "SELECT tbl_name, name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
        ).fetchall()
    assert sorted(explicit) == [
        ("candidate", "candidate_group_id"),
        ("candidate", "candidate_last_seen_at"),
        ("candidate", "candidate_published_at"),
        ("candidate", "candidate_state_next_attempt"),
        ("candidate_discovery", "candidate_discovery_endpoint_seen"),
        ("candidate_discovery", "candidate_discovery_raw_item"),
        ("candidate_transition", "candidate_transition_candidate_at"),
        ("source_document", "source_document_text_hash"),
        ("whatsapp_draft", "whatsapp_draft_status"),
    ]


def test_foreign_keys_declared(db):
    with sqlite3.connect(db) as conn:
        endpoint_fks = conn.execute("PRAGMA foreign_key_list(source_endpoint)").fetchall()
        raw_fks = conn.execute("PRAGMA foreign_key_list(raw_item)").fetchall()
    assert {(fk[2], fk[3], fk[4]) for fk in endpoint_fks} == {
        ("source_registry", "source_id", "id")
    }
    assert {(fk[2], fk[3], fk[4]) for fk in raw_fks} == {
        ("source_endpoint", "source_endpoint_id", "id"),
        ("run", "created_in_run", "id"),
    }


def test_raw_item_unique_constraint(db):
    with sqlite3.connect(db) as conn:
        uniques = [
            row for row in conn.execute("PRAGMA index_list(raw_item)").fetchall() if row[2] == 1
        ]
        assert len(uniques) == 1
        cols = [row[2] for row in conn.execute(f"PRAGMA index_info({uniques[0][1]})").fetchall()]
    assert cols == ["source_endpoint_id", "url", "content_hash"]


RAW_ITEM_INSERT = (
    "INSERT INTO raw_item (source_endpoint_id, url, title, raw_content, fetched_at, "
    "content_hash, created_at, updated_at) VALUES (?, 'u', 't', 'c', 'f', 'h', 'x', 'x')"
)


def test_foreign_keys_enforced_on_connections(db):
    conn = connect(db)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(RAW_ITEM_INSERT, ("inexistente",))
    finally:
        conn.close()


def test_raw_item_unique_rejects_duplicate_and_documents_null_limitation(db):
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO source_registry (id, name, entity_type, tier, categories, domains, "
            "registry_status, created_at, updated_at) "
            "VALUES ('s', 'S', 'other', 'T4', '[]', '[]', 'candidate', 'x', 'x')"
        )
        conn.execute(
            "INSERT INTO source_endpoint (id, source_id, endpoint_type, endpoint_status, "
            "created_at, updated_at) VALUES ('e', 's', 'manual', 'candidate', 'x', 'x')"
        )
        conn.execute(RAW_ITEM_INSERT, ("e",))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(RAW_ITEM_INSERT, ("e",))
        # Limitação conhecida (ROADMAP.md M2.6): NULL não colide no UNIQUE.
        conn.execute(RAW_ITEM_INSERT, (None,))
        conn.execute(RAW_ITEM_INSERT, (None,))
    finally:
        conn.close()


def test_text_primary_keys_reject_null(db):
    conn = connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO source_registry (id, name, entity_type, tier, categories, domains, "
                "registry_status, created_at, updated_at) "
                "VALUES (NULL, 'S', 'other', 'T4', '[]', '[]', 'candidate', 'x', 'x')"
            )
    finally:
        conn.close()


# --- Migrações -----------------------------------------------------------------


def test_load_migrations_reads_package_resource():
    migrations = load_migrations()
    assert [m.name for m in migrations] == [
        "0001_init",
        "0002_source_document",
        "0003_whatsapp_draft",
        "0004_candidate",
    ]
    assert [m.version for m in migrations] == [1, 2, 3, 4]


def test_migration_filenames_follow_convention():
    for path in MIGRATIONS_DIR.iterdir():
        if path.suffix == ".sql":
            assert len(path.name.split("_", 1)[0]) == 4


def test_only_pending_migrations_are_applied_in_order(tmp_path):
    db = tmp_path / "tde.sqlite3"
    first = write_migrations(tmp_path / "m1", {"0001_init.sql": FAKE_0001})
    assert init_database(db, first, fixed_now).applied == ("0001_init",)

    later = write_migrations(
        tmp_path / "m2",
        {"0003_gamma.sql": FAKE_0003, "0001_init.sql": FAKE_0001, "0002_beta.sql": FAKE_0002},
    )
    assert init_database(db, later, fixed_now).applied == ("0002_beta", "0003_gamma")
    assert [row[0] for row in migration_rows(db)] == [1, 2, 3]
    assert tables(db) == {"schema_migration", "alpha", "beta", "gamma"}
    assert init_database(db, later, fixed_now).applied == ()


def test_unchanged_checksum_passes(tmp_path):
    db = tmp_path / "tde.sqlite3"
    migrations = write_migrations(tmp_path / "m", {"0001_init.sql": FAKE_0001})
    init_database(db, migrations, fixed_now)
    rows = migration_rows(db)
    assert init_database(db, migrations, fixed_now).applied == ()
    assert migration_rows(db) == rows


def test_changed_checksum_fails(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE schema_migration SET checksum = 'outro' WHERE version = 1")
    rows = migration_rows(db)
    assert main(["--db", str(db), "init"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"init: ERRO — {db}",
        "- a migração 0001_init foi alterada depois de aplicada (checksum diferente do registado)",
    ]
    assert migration_rows(db) == rows


def test_edited_migration_file_fails(tmp_path):
    db = tmp_path / "tde.sqlite3"
    migrations = write_migrations(tmp_path / "m", {"0001_init.sql": FAKE_0001})
    init_database(db, migrations, fixed_now)
    (migrations / "0001_init.sql").write_text(FAKE_0001 + "-- editada\n", encoding="utf-8")
    with pytest.raises(StorageError, match="checksum diferente"):
        init_database(db, migrations, fixed_now)


def test_database_newer_than_code_fails(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO schema_migration (version, checksum, applied_at) "
            "VALUES (5, 'abc', '2026-10-07T12:00:00.000000+00:00')"
        )
    assert main(["--db", str(db), "init"]) == 1
    assert capsys.readouterr().err.splitlines() == [
        f"init: ERRO — {db}",
        "- a base de dados tem a migração 0005, desconhecida desta versão do código "
        "(base de dados mais recente que o código)",
    ]


def test_pending_migration_older_than_applied_fails(tmp_path):
    db = tmp_path / "tde.sqlite3"
    first = write_migrations(
        tmp_path / "m1", {"0001_init.sql": FAKE_0001, "0003_gamma.sql": FAKE_0003}
    )
    init_database(db, first, fixed_now)
    gap = write_migrations(
        tmp_path / "m2",
        {"0001_init.sql": FAKE_0001, "0002_beta.sql": FAKE_0002, "0003_gamma.sql": FAKE_0003},
    )
    with pytest.raises(StorageError, match="0002_beta está pendente"):
        init_database(db, gap, fixed_now)


def test_failed_migration_rolls_back_completely(tmp_path):
    db = tmp_path / "tde.sqlite3"
    first = write_migrations(tmp_path / "m1", {"0001_init.sql": FAKE_0001})
    init_database(db, first, fixed_now)
    rows = migration_rows(db)

    broken = write_migrations(
        tmp_path / "m2",
        {
            "0001_init.sql": FAKE_0001,
            "0002_broken.sql": "CREATE TABLE beta (id INTEGER NOT NULL PRIMARY KEY);\n"
            "INSERT INTO alpha (id) VALUES (1);\n"
            "CREATE TABLE alpha (id INTEGER);\n",
        },
    )
    with pytest.raises(StorageError, match="a migração 0002_broken falhou"):
        init_database(db, broken, fixed_now)
    assert tables(db) == {"schema_migration", "alpha"}
    assert migration_rows(db) == rows
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM alpha").fetchone() == (0,)


def test_failed_first_migration_leaves_no_tables(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    broken = write_migrations(
        tmp_path / "m",
        {"0001_init.sql": FAKE_0001 + "CREATE TABLE alpha (id INTEGER);\n"},
    )
    with pytest.raises(StorageError, match="0001_init falhou"):
        init_database(db, broken, fixed_now)
    assert tables(db) == set()


def test_earlier_migrations_in_same_run_stay_applied_after_failure(tmp_path):
    db = tmp_path / "tde.sqlite3"
    migrations = write_migrations(
        tmp_path / "m",
        {"0001_init.sql": FAKE_0001, "0002_broken.sql": "CREATE TABLE alpha (id INTEGER);\n"},
    )
    with pytest.raises(StorageError):
        init_database(db, migrations, fixed_now)
    assert [row[0] for row in migration_rows(db)] == [1]


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("1_init.sql", "nome de migração inválido: 1_init.sql"),
        ("0001-init.sql", "nome de migração inválido: 0001-init.sql"),
        ("0001_Init.sql", "nome de migração inválido: 0001_Init.sql"),
        ("0000_zero.sql", "versão de migração inválida: 0000_zero.sql"),
    ],
)
def test_invalid_migration_names_fail(tmp_path, filename, message):
    migrations = write_migrations(tmp_path / "m", {filename: FAKE_0002})
    with pytest.raises(StorageError) as exc:
        load_migrations(migrations)
    assert str(exc.value) == message


def test_duplicate_migration_version_fails(tmp_path):
    migrations = write_migrations(
        tmp_path / "m", {"0002_a.sql": FAKE_0002, "0002_b.sql": FAKE_0003}
    )
    with pytest.raises(StorageError, match="versão de migração repetida: 0002_b.sql"):
        load_migrations(migrations)


def test_non_sql_files_are_ignored(tmp_path):
    migrations = write_migrations(
        tmp_path / "m", {"0001_init.sql": FAKE_0001, "README.md": "notas"}
    )
    assert [m.name for m in load_migrations(migrations)] == ["0001_init"]


def test_split_statements_respects_literals_and_comments():
    sql = "-- a; b\nCREATE TABLE t (x TEXT DEFAULT 'a;b');\n/* c; */\nINSERT INTO t VALUES (';');\n"
    assert split_statements(sql) == [
        "-- a; b\nCREATE TABLE t (x TEXT DEFAULT 'a;b');",
        "/* c; */\nINSERT INTO t VALUES (';');",
    ]


def test_split_statements_rejects_incomplete_statement():
    with pytest.raises(StorageError, match="instrução SQL incompleta"):
        split_statements("CREATE TABLE t (x TEXT)")


# --- Erros -----------------------------------------------------------------------


def test_non_sqlite_file_fails(tmp_path, capsys):
    db = tmp_path / "not.sqlite3"
    db.write_bytes(b"isto nao e uma base de dados sqlite")
    assert main(["--db", str(db), "init"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"init: ERRO — {db}",
        "- o ficheiro não é uma base de dados SQLite",
    ]
    assert db.read_bytes() == b"isto nao e uma base de dados sqlite"


def test_directory_as_db_path_fails(tmp_path, capsys):
    assert main(["--db", str(tmp_path), "init"]) == 1
    assert capsys.readouterr().err.splitlines() == [
        f"init: ERRO — {tmp_path}",
        "- o caminho da base de dados é um directório",
    ]


def test_error_messages_are_deterministic(tmp_path, capsys):
    db = tmp_path / "not.sqlite3"
    db.write_text("x", encoding="utf-8")
    outputs = []
    for _ in range(2):
        assert main(["--db", str(db), "init"]) == 1
        outputs.append(capsys.readouterr().err)
    assert outputs[0] == outputs[1]


# --- Determinismo e datas ----------------------------------------------------------


def test_same_migrations_produce_same_schema(tmp_path):
    a, b = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3"
    init_database(a, now=fixed_now)
    init_database(b, now=lambda: FIXED_NOW + timedelta(days=1))
    assert schema_sql(a) == schema_sql(b)
    assert [r[:2] for r in migration_rows(a)] == [r[:2] for r in migration_rows(b)]


def test_applied_at_is_utc_iso_8601_with_offset(tmp_path):
    db = tmp_path / "tde.sqlite3"
    lisbon_summer = timezone(timedelta(hours=1))
    init_database(db, now=lambda: datetime(2026, 7, 1, 13, 0, tzinfo=lisbon_summer))
    applied_at = migration_rows(db)[0][2]
    assert applied_at == "2026-07-01T12:00:00.000000+00:00"
    assert datetime.fromisoformat(applied_at).utcoffset() == timedelta(0)


def test_to_utc_iso_rejects_naive_datetime():
    with pytest.raises(ValueError, match="fuso horário"):
        to_utc_iso(datetime(2026, 10, 7, 12, 0))


# --- CLI -------------------------------------------------------------------------


def test_init_appears_in_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "init" in out
    assert "--db PATH" in out
