"""Testes do M2.11: migração `0002`, `source_document` e `tde normalize` (ROADMAP.md M2.11).

DEC-021, DEC-022, DEC-031, DEC-037 a DEC-041. Offline e deterministas: bases de dados em
directórios temporários, relógio injectado e `raw_item` sintéticos (domínios reservados,
RFC 2606), construídos directamente ou por `tde collect` com transporte falso. Nenhum
teste escreve em `data/` nem usa a rede (salvaguarda em `conftest.py`).
"""

import ast
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from _fake_http import FEED_URL, HOST, NO_ROBOTS, FakeServer, feed

import tensdireito_content_engine
from tensdireito_content_engine import cli, normalize_command
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.collectors.rss import RssCollector
from tensdireito_content_engine.domain import (
    DocumentStatus,
    EndpointStatus,
    EndpointType,
    EntityType,
    RegistryStatus,
    SourceDocument,
    SourceEndpoint,
    SourceRegistry,
    SourceTier,
)
from tensdireito_content_engine.normalize import text_fingerprint
from tensdireito_content_engine.normalize.rss import CONTENT_NAMESPACE
from tensdireito_content_engine.normalize_command import run_normalize
from tensdireito_content_engine.storage import (
    StorageError,
    connect,
    init_database,
    insert_source_document,
    pending_raw_items,
    start_run,
    sync_sources,
)
from tensdireito_content_engine.storage.migrator import default_migrations_dir

PACKAGE_DIR = Path(tensdireito_content_engine.__file__).parent
REPO_ROOT = PACKAGE_DIR.parents[1]
MIGRATIONS_DIR = Path(str(default_migrations_dir()))
RSS_FIXTURES = Path(__file__).parent / "fixtures" / "rss"
T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
T0_ISO = "2026-10-07T12:00:00.000000+00:00"
X = "2026-10-01T09:00:00.000000+00:00"

# fonte → (tier, registry_status interno)
SOURCES = {
    "fonte_t1": ("T1", "validated"),
    "fonte_t2": ("T2", "validated"),
    "fonte_candidata": ("T1", "candidate"),
    "fonte_inactiva": ("T1", "inactive"),
}
# endpoint → (fonte, endpoint_type)
ENDPOINTS = {
    "feed": ("fonte_t1", "rss"),
    "feed_t2": ("fonte_t2", "rss"),
    "feed_candidato": ("fonte_candidata", "rss"),
    "feed_inactivo": ("fonte_inactiva", "rss"),
    "pagina": ("fonte_t1", "html_page"),
    "entrada_manual": ("fonte_t1", "manual"),
}
DOCUMENT_COLUMNS = (
    "id",
    "raw_item_id",
    "source_id",
    "canonical_url",
    "title",
    "text",
    "language",
    "published_at",
    "source_tier",
    "document_kind",
    "text_hash",
    "duplicate_of",
    "status",
    "created_in_run",
    "created_at",
    "updated_at",
)


def fixed_now() -> datetime:
    return T0


def item_xml(children: str = "", attrs: str = "", title: str = "Título") -> str:
    return (
        f'<item xmlns:ns0="{CONTENT_NAMESPACE}"{attrs}><title>{title}</title>'
        f"<link>https://feed.example.org/1</link>{children}</item>"
    )


def desc(text: str) -> str:
    return item_xml(f"<description>{text}</description>")


def query(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def execute(db: Path, sql: str, params: tuple = ()) -> int:
    conn = sqlite3.connect(db)
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def seed(db: Path) -> None:
    for source_id, (tier, status) in SOURCES.items():
        execute(
            db,
            "INSERT INTO source_registry (id, name, entity_type, tier, categories, domains, "
            "registry_status, validated_at, validated_by, created_at, updated_at) "
            "VALUES (?, ?, 'public_body', ?, '[]', '[]', ?, NULL, NULL, ?, ?)",
            (source_id, source_id, tier, status, X, X),
        )
    for endpoint_id, (source_id, endpoint_type) in ENDPOINTS.items():
        execute(
            db,
            "INSERT INTO source_endpoint (id, source_id, endpoint_type, url, endpoint_status, "
            "created_at, updated_at) VALUES (?, ?, ?, NULL, 'candidate', ?, ?)",
            (endpoint_id, source_id, endpoint_type, X, X),
        )


_counter = iter(range(1, 1_000_000))


def add_raw(
    db: Path,
    raw_content: str,
    endpoint: str | None = "feed",
    title: str = "  Título\n do   item ",
    published_at_raw: str | None = "Wed, 07 Oct 2026 10:00:00 +0100",
    url: str | None = None,
) -> int:
    url = url or f"https://feed.example.org/noticias/{next(_counter)}?utm_source=rss#topo"
    return execute(
        db,
        "INSERT INTO raw_item (source_endpoint_id, url, external_id, title, raw_content, "
        "fetched_at, published_at_raw, content_hash, manual_note, created_in_run, created_at, "
        "updated_at) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
        (
            endpoint,
            url,
            title,
            raw_content,
            X,
            published_at_raw,
            hashlib.sha256(raw_content.encode("utf-8")).hexdigest(),
            X,
            X,
        ),
    )


def documents(db: Path) -> list[dict]:
    rows = query(db, f"SELECT {', '.join(DOCUMENT_COLUMNS)} FROM source_document ORDER BY id")
    return [dict(zip(DOCUMENT_COLUMNS, row, strict=True)) for row in rows]


def document_for(db: Path, raw_item_id: int) -> dict:
    (document,) = [doc for doc in documents(db) if doc["raw_item_id"] == raw_item_id]
    return document


def runs(db: Path) -> list[dict]:
    columns = ("id", "command", "started_at", "finished_at", "status", "stats", "outcome")
    rows = query(db, f"SELECT {', '.join(columns)} FROM run ORDER BY id")
    result = [dict(zip(columns, row, strict=True)) for row in rows]
    for row in result:
        row["stats"] = None if row["stats"] is None else json.loads(row["stats"])
    return result


def table_snapshot(db: Path, table: str) -> list[tuple]:
    return query(db, f"SELECT * FROM {table} ORDER BY 1")


def normalize_cli(db: Path, *extra: str) -> int:
    return cli.main([*extra, "--db", str(db), "normalize"])


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    original = normalize_command.run_normalize

    def fixed(path, now=fixed_now):
        return original(path, now)

    monkeypatch.setattr(cli, "run_normalize", fixed)


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "db" / "tde.sqlite3"
    init_database(path, now=fixed_now)
    seed(path)
    return path


# --- Migração 0002 ---------------------------------------------------------------


def test_empty_database_gets_0001_and_0002(tmp_path, capsys):
    db = tmp_path / "novo" / "tde.sqlite3"
    assert cli.main(["--db", str(db), "init"]) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        "migrações aplicadas: 0001_init, 0002_source_document, 0003_whatsapp_draft"
    )
    assert [row[0] for row in query(db, "SELECT version FROM schema_migration")] == [1, 2, 3]
    assert query(db, "SELECT COUNT(*) FROM source_document") == [(0,)]


def only_0001(tmp_path: Path) -> Path:
    directory = tmp_path / "so_0001"
    directory.mkdir()
    shutil.copy(MIGRATIONS_DIR / "0001_init.sql", directory / "0001_init.sql")
    return directory


def test_existing_database_with_only_0001_gets_only_0002_and_keeps_data(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    assert init_database(db, only_0001(tmp_path), fixed_now).applied == ("0001_init",)
    seed(db)
    add_raw(db, desc("Texto."))
    tables_0001 = ("schema_migration", "run", "source_registry", "source_endpoint", "raw_item")
    before = {table: table_snapshot(db, table) for table in tables_0001}
    schema_before = query(
        db,
        "SELECT name, sql FROM sqlite_master "
        "WHERE tbl_name NOT IN ('source_document', 'whatsapp_draft') ORDER BY 1",
    )

    assert cli.main(["--db", str(db), "init"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"init: OK — {db}",
        "migrações aplicadas: 0002_source_document, 0003_whatsapp_draft",
    ]
    for table in tables_0001[1:]:
        assert table_snapshot(db, table) == before[table]
    assert table_snapshot(db, "schema_migration")[0] == before["schema_migration"][0]
    assert query(
        db,
        "SELECT name, sql FROM sqlite_master "
        "WHERE tbl_name NOT IN ('source_document', 'whatsapp_draft') "
        "AND name != 'schema_migration' ORDER BY 1",
    ) == [row for row in schema_before if row[0] != "schema_migration"]
    assert init_database(db).applied == ()


def test_normalize_on_database_without_0002_fails_without_run_or_migration(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    init_database(db, only_0001(tmp_path), fixed_now)
    seed(db)
    add_raw(db, desc("Texto."))
    before = query(db, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    assert normalize_cli(db) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"normalize: ERRO — {db}",
        "- esquema não conforme: migrações pendentes: 0002_source_document, "
        "0003_whatsapp_draft; execute `tde init`",
    ]
    assert query(db, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
    assert query(db, "SELECT COUNT(*) FROM run") == [(0,)]


def test_source_document_foreign_keys_are_declared(db):
    fks = query(db, "PRAGMA foreign_key_list(source_document)")
    assert {(fk[2], fk[3], fk[4]) for fk in fks} == {
        ("raw_item", "raw_item_id", "id"),
        ("source_registry", "source_id", "id"),
        ("source_document", "duplicate_of", "id"),
        ("run", "created_in_run", "id"),
    }


def test_source_document_unique_raw_item_and_text_hash_index(db):
    indexes = query(db, "PRAGMA index_list(source_document)")
    unique = [row[1] for row in indexes if row[2] == 1]
    assert len(unique) == 1
    assert [row[2] for row in query(db, f"PRAGMA index_info({unique[0]})")] == ["raw_item_id"]
    (text_hash_index,) = [row for row in indexes if row[1] == "source_document_text_hash"]
    assert text_hash_index[2] == 0  # não único
    assert [row[2] for row in query(db, "PRAGMA index_info(source_document_text_hash)")] == [
        "text_hash"
    ]


INSERT_DOCUMENT = (
    "INSERT INTO source_document (raw_item_id, source_id, title, source_tier, text_hash, "
    "duplicate_of, status, created_in_run, created_at, updated_at) "
    "VALUES (?, ?, 't', 'T4', ?, ?, 'normalized', ?, 'x', 'x')"
)


def test_source_document_constraints_are_enforced(db):
    raw_id = add_raw(db, desc("Texto."))
    conn = connect(db)
    try:
        run_id = start_run(conn, "normalize", T0)
        for params in (
            (999, None, None, None, run_id),  # raw_item inexistente
            (raw_id, "fonte_inexistente", None, None, run_id),
            (raw_id, None, None, 999, run_id),  # duplicate_of inexistente
            (raw_id, None, None, None, 999),  # run inexistente
            (raw_id, None, None, None, None),  # created_in_run obrigatório
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(INSERT_DOCUMENT, params)
        conn.execute(INSERT_DOCUMENT, (raw_id, None, "h", None, run_id))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(INSERT_DOCUMENT, (raw_id, None, "h", None, run_id))
        other = add_raw(db, desc("Outro."))
        conn.execute(INSERT_DOCUMENT, (other, None, "h", None, run_id))  # text_hash não único
    finally:
        conn.close()


def test_0002_has_no_classification_columns(db):
    names = {row[1] for row in query(db, "PRAGMA table_info(source_document)")}
    assert len(names) == 16
    assert not {name for name in names if name.startswith("proposed_")}
    assert not names & {"relevance_flag", "classified_by"}


def sql_code(path: Path) -> str:
    """O SQL de um ficheiro: a migração inteira, ou os literais de um módulo sem docstrings."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".sql":
        return text
    tree = ast.parse(text)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and ast.get_docstring(node) is not None
    }
    return "\n".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    )


def test_0002_new_sql_avoids_conflict_clauses():
    paths = [
        MIGRATIONS_DIR / "0002_source_document.sql",
        PACKAGE_DIR / "storage" / "source_documents.py",
    ]
    for path in paths:
        code = sql_code(path)
        assert "INSERT INTO source_document" in code or path.suffix == ".sql"
        for pattern in (r"INSERT\s+OR\s+IGNORE", r"INSERT\s+OR\s+REPLACE", r"ON\s+CONFLICT"):
            assert not re.search(pattern, code, re.IGNORECASE), (path, pattern)


# --- Pré-condições ------------------------------------------------------------


def test_missing_database_fails_without_creating_anything(tmp_path, capsys):
    db = tmp_path / "nao" / "existe" / "tde.sqlite3"
    assert normalize_cli(db) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"normalize: ERRO — {db}",
        "- a base de dados não existe; execute `tde init` para a criar",
    ]
    assert not (tmp_path / "nao").exists()


def test_non_sqlite_file_fails_asking_for_init(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    db.write_text("isto não é SQLite", encoding="utf-8")
    assert normalize_cli(db) == 1
    assert "esquema não conforme" in capsys.readouterr().err
    assert db.read_text(encoding="utf-8") == "isto não é SQLite"


def test_altered_migration_fails_without_run(db, capsys):
    execute(db, "UPDATE schema_migration SET checksum = 'x' WHERE version = 2")
    assert normalize_cli(db) == 1
    assert "esquema não conforme: a migração 0002_source_document foi alterada" in (
        capsys.readouterr().err
    )
    assert query(db, "SELECT COUNT(*) FROM run") == [(0,)]


def test_config_directory_is_not_read(db, tmp_path, capsys):
    add_raw(db, desc("Texto."))
    assert normalize_cli(db, "--config", str(tmp_path / "inexistente")) == 0
    assert "normalize: OK" in capsys.readouterr().out


# --- Zero pendentes e run -----------------------------------------------------------


def test_zero_pending_is_success(db, capsys):
    assert normalize_cli(db) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"normalize: OK — {db}",
        "run: 1",
        "pendentes: 0",
        "normalizados: 0",
        "duplicados: 0",
        "sem texto: 0",
        "não suportados: 0",
        "com falha: 0",
    ]
    assert captured.err == ""
    assert runs(db) == [
        {
            "id": 1,
            "command": "normalize",
            "started_at": T0_ISO,
            "finished_at": T0_ISO,
            "status": "success",
            "stats": {
                "items": [],
                "totals": {
                    "pending": 0,
                    "normalized": 0,
                    "duplicates": 0,
                    "without_text": 0,
                    "unsupported": 0,
                    "failed": 0,
                },
            },
            "outcome": None,
        }
    ]
    assert query(db, "SELECT report_path FROM run") == [(None,)]


def test_empty_database_from_init_normalizes_nothing(tmp_path, capsys):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    assert normalize_cli(db) == 0
    assert documents(db) == []


def test_run_is_open_while_items_are_processed(db, monkeypatch):
    add_raw(db, desc("Texto."))
    seen = []
    original = normalize_command.insert_source_document

    def spy(conn, document, run_id, at):
        seen.append(
            conn.execute("SELECT finished_at, status FROM run WHERE id = ?", (run_id,)).fetchone()
        )
        return original(conn, document, run_id, at)

    monkeypatch.setattr(normalize_command, "insert_source_document", spy)
    assert normalize_cli(db) == 0
    assert seen == [(None, None)]


# --- Um item rss ------------------------------------------------------------------


def test_rss_item_becomes_a_source_document(db, capsys):
    raw = item_xml(
        "<description>Resumo.</description>"
        "<ns0:encoded><![CDATA[<p>Corpo  do</p><p>documento.</p>]]></ns0:encoded>",
        ' xml:lang="pt-PT"',
    )
    raw_id = add_raw(db, raw)
    assert normalize_cli(db) == 0
    assert capsys.readouterr().out.splitlines()[1:] == [
        "run: 1",
        "pendentes: 1",
        "normalizados: 1",
        "duplicados: 0",
        "sem texto: 0",
        "não suportados: 0",
        "com falha: 0",
    ]
    text = "Corpo do\n\ndocumento."
    assert documents(db) == [
        {
            "id": 1,
            "raw_item_id": raw_id,
            "source_id": "fonte_t1",
            "canonical_url": None,
            "title": "Título do item",
            "text": text,
            "language": "pt",
            "published_at": None,
            "source_tier": "T1",
            "document_kind": None,
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "duplicate_of": None,
            "status": "normalized",
            "created_in_run": 1,
            "created_at": T0_ISO,
            "updated_at": T0_ISO,
        }
    ]
    assert document_for(db, raw_id)["text_hash"] == text_fingerprint(text)


def test_canonical_url_is_null_and_raw_url_is_preserved(db):
    url = "https://feed.example.org/noticias/9?utm_source=rss&utm_medium=x#fragmento"
    raw_id = add_raw(db, desc("Texto."), url=url)
    normalize_cli(db)
    assert document_for(db, raw_id)["canonical_url"] is None
    assert query(db, "SELECT url FROM raw_item WHERE id = ?", (raw_id,)) == [(url,)]


def test_document_kind_is_always_null_never_other(db):
    for endpoint in ("feed", "feed_t2", "feed_candidato"):
        add_raw(db, desc(f"Texto {endpoint}."), endpoint=endpoint)
    add_raw(db, item_xml())
    normalize_cli(db)
    assert {doc["document_kind"] for doc in documents(db)} == {None}
    assert query(db, "SELECT COUNT(*) FROM source_document WHERE document_kind = 'other'") == [(0,)]


def test_language_null_without_xml_lang_even_for_validated_t1(db):
    raw_id = add_raw(db, desc("Texto em português."))
    normalize_cli(db)
    document = document_for(db, raw_id)
    assert (document["source_tier"], document["language"]) == ("T1", None)


def test_language_from_chosen_element_and_from_item(db):
    element = add_raw(
        db, item_xml('<description xml:lang="en-GB">Text.</description>', ' xml:lang="pt"')
    )
    from_item = add_raw(db, item_xml("<description>Texto.</description>", ' xml:lang="pt-PT"'))
    empty = add_raw(db, item_xml("<description>Vazio.</description>", ' xml:lang=""'))
    normalize_cli(db)
    assert document_for(db, element)["language"] == "en"
    assert document_for(db, from_item)["language"] == "pt"
    assert document_for(db, empty)["language"] is None


def test_title_is_never_used_as_text(db, capsys):
    raw_id = add_raw(db, item_xml(), title="Título sem corpo")
    other = add_raw(db, item_xml("<description> </description>"), title="Outro sem corpo")
    assert normalize_cli(db) == 0
    assert capsys.readouterr().out.splitlines()[3:6] == [
        "normalizados: 2",
        "duplicados: 0",
        "sem texto: 2",
    ]
    for identifier, title in ((raw_id, "Título sem corpo"), (other, "Outro sem corpo")):
        document = document_for(db, identifier)
        assert (document["text"], document["text_hash"]) == (None, None)
        assert (document["title"], document["status"], document["duplicate_of"]) == (
            title,
            "normalized",
            None,
        )


def test_raw_item_is_unchanged(db):
    for text in ("Um.", "Dois."):
        add_raw(db, desc(f"<![CDATA[<p>{text}</p>]]>"))
    add_raw(db, "<item><title>x", endpoint="feed")
    before = table_snapshot(db, "raw_item")
    others = {t: table_snapshot(db, t) for t in ("source_registry", "source_endpoint")}
    normalize_cli(db)
    assert table_snapshot(db, "raw_item") == before
    for table, rows in others.items():
        assert table_snapshot(db, table) == rows


# --- published_at --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Wed, 07 Oct 2026 10:00:00 +0100", None),
        ("Tue, 06 Oct 2026 09:30:00 GMT", None),
        ("2026-10-07T10:00:00+01:00", "2026-10-07T09:00:00.000000+00:00"),
        ("2026-10-07T10:00:00Z", "2026-10-07T10:00:00.000000+00:00"),
        ("2026-10-07T10:00:00", None),
        ("2026-10-07", None),
        (None, None),
    ],
)
def test_published_at_follows_dec021(db, raw, expected):
    raw_id = add_raw(db, desc("Texto."), published_at_raw=raw)
    normalize_cli(db)
    assert document_for(db, raw_id)["published_at"] == expected
    assert query(db, "SELECT published_at_raw FROM raw_item WHERE id = ?", (raw_id,)) == [(raw,)]


# --- source_tier --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "source_id", "tier"),
    [
        ("feed", "fonte_t1", "T1"),
        ("feed_t2", "fonte_t2", "T2"),
        ("feed_candidato", "fonte_candidata", "T4"),
        ("feed_inactivo", "fonte_inactiva", "T4"),
    ],
)
def test_source_tier_and_source_id(db, endpoint, source_id, tier):
    raw_id = add_raw(db, desc("Texto."), endpoint=endpoint)
    normalize_cli(db)
    document = document_for(db, raw_id)
    assert (document["source_id"], document["source_tier"]) == (source_id, tier)


def test_source_tier_is_read_at_normalization_time(db):
    raw_id = add_raw(db, desc("Texto."))
    execute(db, "UPDATE source_registry SET registry_status = 'inactive' WHERE id = 'fonte_t1'")
    normalize_cli(db)
    assert document_for(db, raw_id)["source_tier"] == "T4"


# --- Deduplicação (DEC-022) ------------------------------------------------------------


def test_duplicates_in_the_same_run(db, capsys):
    first = add_raw(db, desc("<![CDATA[<p>Mesmo texto.</p>]]>"))
    second = add_raw(db, desc("&lt;p&gt;Mesmo   texto.&lt;/p&gt;"), endpoint="feed_t2")
    third = add_raw(db, desc("Mesmo texto."), endpoint="feed_candidato")
    assert normalize_cli(db) == 0
    assert capsys.readouterr().out.splitlines()[3:5] == ["normalizados: 1", "duplicados: 2"]
    representative = document_for(db, first)
    assert (representative["status"], representative["duplicate_of"]) == ("normalized", None)
    for raw_id in (second, third):
        duplicate = document_for(db, raw_id)
        assert (duplicate["status"], duplicate["duplicate_of"]) == ("ignored", representative["id"])
        assert duplicate["text_hash"] == representative["text_hash"]
    # Tier e fonte não são transferidos (DEC-022).
    assert document_for(db, third)["source_tier"] == "T4"


def test_duplicates_across_runs_keep_the_registered_representative(db, capsys):
    first = add_raw(db, desc("Texto repetido."))
    assert normalize_cli(db) == 0
    representative_row = table_snapshot(db, "source_document")
    later = add_raw(db, desc("Texto repetido."), endpoint="feed_t2")
    assert normalize_cli(db) == 0
    assert capsys.readouterr().out.splitlines()[-6:-3] == [
        "pendentes: 1",
        "normalizados: 0",
        "duplicados: 1",
    ]
    assert table_snapshot(db, "source_document")[0] == representative_row[0]
    duplicate = document_for(db, later)
    representative = document_for(db, first)
    assert (duplicate["duplicate_of"], duplicate["status"], duplicate["created_in_run"]) == (
        representative["id"],
        "ignored",
        2,
    )


def test_duplicate_points_to_the_representative_not_to_another_duplicate(db):
    first = add_raw(db, desc("Igual."))
    for _ in range(3):
        add_raw(db, desc("Igual."))
    normalize_cli(db)
    representative = document_for(db, first)["id"]
    assert {doc["duplicate_of"] for doc in documents(db) if doc["raw_item_id"] != first} == {
        representative
    }


def test_insert_never_reuses_a_document_as_representative_twice(db):
    raw_ids = [add_raw(db, desc("Igual.")) for _ in range(2)]
    conn = connect(db)
    try:
        run_id = start_run(conn, "normalize", T0)
        stored = [
            insert_source_document(
                conn,
                SourceDocument(
                    raw_item_id=raw_id,
                    source_id="fonte_t1",
                    title="T",
                    text="Igual.",
                    text_hash=text_fingerprint("Igual."),
                    source_tier=SourceTier.T1,
                    status=DocumentStatus.NORMALIZED,
                ),
                run_id,
                T0,
            )
            for raw_id in raw_ids
        ]
    finally:
        conn.close()
    assert [doc.status for doc in stored] == [DocumentStatus.NORMALIZED, DocumentStatus.IGNORED]
    assert stored[1].duplicate_of == stored[0].id


def test_insert_rejects_documents_already_decided(db):
    conn = connect(db)
    try:
        base = {"raw_item_id": 1, "title": "T", "source_tier": SourceTier.T4}
        for document in (
            SourceDocument(**base, id=5, status=DocumentStatus.NORMALIZED),
            SourceDocument(
                **base,
                text="x",
                text_hash=text_fingerprint("x"),
                duplicate_of=1,
                status=DocumentStatus.IGNORED,
            ),
            SourceDocument(**base, status=DocumentStatus.IGNORED),
        ):
            with pytest.raises(ValueError):
                insert_source_document(conn, document, 1, T0)
    finally:
        conn.close()


# --- unsupported -----------------------------------------------------------------------


def test_unsupported_items_stay_pending_and_are_not_failures(db, capsys):
    html = add_raw(db, "<html><body>Página</body></html>", endpoint="pagina")
    manual = add_raw(db, desc("Manual."), endpoint="entrada_manual")
    without_endpoint = add_raw(db, desc("Pista."), endpoint=None)
    ok = add_raw(db, desc("Texto."))
    assert normalize_cli(db) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines()[2:] == [
        "pendentes: 4",
        "normalizados: 1",
        "duplicados: 0",
        "sem texto: 0",
        "não suportados: 3",
        "com falha: 0",
    ]
    assert captured.err == ""
    assert [doc["raw_item_id"] for doc in documents(db)] == [ok]
    assert runs(db)[0]["stats"] == {
        "items": [
            {
                "raw_item_id": html,
                "result": "unsupported",
                "reason": "sem regra de extracção para endpoint_type html_page",
            },
            {
                "raw_item_id": manual,
                "result": "unsupported",
                "reason": "sem regra de extracção para endpoint_type manual",
            },
            {"raw_item_id": without_endpoint, "result": "unsupported", "reason": "sem endpoint"},
        ],
        "totals": {
            "pending": 4,
            "normalized": 1,
            "duplicates": 0,
            "without_text": 0,
            "unsupported": 3,
            "failed": 0,
        },
    }
    assert runs(db)[0]["status"] == "success"

    # Continuam pendentes e são contados de novo.
    assert normalize_cli(db) == 0
    totals = runs(db)[1]["stats"]["totals"]
    assert (totals["pending"], totals["unsupported"], totals["normalized"]) == (3, 3, 0)


# --- failed, partial e atomicidade ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_content", "reason"),
    [
        (
            "<item><title>x</title>",
            "raw_content: XML malformado: no element found: line 1, column 22",
        ),
        ("<!DOCTYPE item><item/>", "raw_content: DOCTYPE não permitido"),
        ("<rss><channel/></rss>", "raw_content: raiz não suportada: rss"),
    ],
)
def test_unreadable_raw_content_fails_without_document(db, capsys, raw_content, reason):
    bad = add_raw(db, raw_content)
    assert normalize_cli(db) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines()[0] == f"normalize: ERRO — {db}"
    assert captured.out.splitlines()[-1] == "com falha: 1"
    assert captured.err.splitlines() == [f"- raw_item {bad}: {reason}"]
    assert documents(db) == []
    run = runs(db)[0]
    assert (run["status"], run["finished_at"]) == ("failed", T0_ISO)
    assert run["stats"]["items"] == [{"raw_item_id": bad, "result": "failed", "reason": reason}]


def test_failure_does_not_affect_other_items_and_is_partial(db, capsys):
    before = add_raw(db, desc("Antes."))
    bad = add_raw(db, "<item>")
    after = add_raw(db, desc("Depois."))
    assert normalize_cli(db) == 2
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"normalize: PARCIAL — {db}",
        "run: 1",
        "pendentes: 3",
        "normalizados: 2",
        "duplicados: 0",
        "sem texto: 0",
        "não suportados: 0",
        "com falha: 1",
    ]
    assert captured.err.splitlines()[0].startswith(f"- raw_item {bad}: raw_content: XML malformado")
    assert [doc["raw_item_id"] for doc in documents(db)] == [before, after]
    assert runs(db)[0]["status"] == "partial"


def test_domain_validation_error_is_an_item_failure(db, capsys):
    execute(db, "UPDATE source_registry SET tier = 'T9' WHERE id = 'fonte_t2'")
    bad_tier = add_raw(db, desc("Texto."), endpoint="feed_t2")
    blank_title = add_raw(db, desc("Outro."), title="   ")
    assert normalize_cli(db) == 1
    assert capsys.readouterr().err.splitlines() == [
        f"- raw_item {bad_tier}: source_tier tem de ser SourceTier: 'T9'",
        f"- raw_item {blank_title}: title é obrigatório e não pode ser vazio",
    ]
    assert documents(db) == []


def test_only_unsupported_and_failed_without_documents_is_failed(db):
    add_raw(db, "x", endpoint="pagina")
    add_raw(db, "<item>")
    assert normalize_cli(db) == 1
    assert runs(db)[0]["status"] == "failed"


def test_failed_items_are_retried(db):
    bad = add_raw(db, "<item>")
    normalize_cli(db)
    execute(db, "UPDATE raw_item SET raw_content = ? WHERE id = ?", (desc("Corrigido."), bad))
    assert normalize_cli(db) == 0
    assert document_for(db, bad)["text"] == "Corrigido."
    assert document_for(db, bad)["created_in_run"] == 2


def test_storage_error_interrupts_the_run_and_keeps_committed_documents(db, monkeypatch, capsys):
    first = add_raw(db, desc("Primeiro."))
    second = add_raw(db, desc("Segundo."))
    third = add_raw(db, desc("Terceiro."))
    original = normalize_command.insert_source_document

    def failing(conn, document, run_id, at):
        if document.raw_item_id == second:
            # Erro SQLite real dentro da transacção do item: a FK de `created_in_run` falha.
            return original(conn, document, 999, at)
        return original(conn, document, run_id, at)

    monkeypatch.setattr(normalize_command, "insert_source_document", failing)
    assert normalize_cli(db) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"normalize: ERRO — {db}",
        f"- a gravação do documento do raw_item {second} falhou: FOREIGN KEY constraint failed",
    ]
    assert [doc["raw_item_id"] for doc in documents(db)] == [first]
    run = runs(db)[0]
    assert (run["finished_at"], run["status"], run["stats"]) == (None, None, None)
    assert third not in [doc["raw_item_id"] for doc in documents(db)]


def test_storage_error_on_insert_rolls_back(db):
    conn = connect(db)
    try:
        document = SourceDocument(
            raw_item_id=999, title="T", source_tier=SourceTier.T4, status=DocumentStatus.NORMALIZED
        )
        with pytest.raises(StorageError, match="raw_item 999 falhou"):
            insert_source_document(conn, document, start_run(conn, "normalize", T0), T0)
        assert conn.in_transaction is False
    finally:
        conn.close()
    assert documents(db) == []


# --- Idempotência, ordem e determinismo --------------------------------------------------


def test_second_run_without_new_items_changes_nothing(db, capsys):
    for text in ("Um.", "Dois.", "Um."):
        add_raw(db, desc(text))
    add_raw(db, item_xml())
    assert normalize_cli(db) == 0
    before = {t: table_snapshot(db, t) for t in ("source_document", "raw_item")}
    capsys.readouterr()

    assert normalize_cli(db) == 0
    assert capsys.readouterr().out.splitlines()[1:3] == ["run: 2", "pendentes: 0"]
    for table, rows in before.items():
        assert table_snapshot(db, table) == rows
    assert [run["command"] for run in runs(db)] == ["normalize", "normalize"]


def test_items_are_processed_in_id_order(db):
    ids = [add_raw(db, f"<item>{n}", endpoint="feed") for n in range(3)]
    add_raw(db, "x", endpoint="pagina")
    normalize_cli(db)
    assert [item["raw_item_id"] for item in runs(db)[0]["stats"]["items"]] == sorted(
        [*ids, ids[-1] + 1]
    )


def test_same_database_and_clock_give_same_documents(tmp_path):
    results = []
    for name in ("a", "b"):
        db = tmp_path / name / "tde.sqlite3"
        init_database(db, now=fixed_now)
        seed(db)
        for position, text in enumerate(("Um.", "Dois.", "Um.")):
            add_raw(db, desc(text), url=f"https://feed.example.org/{position}")
        add_raw(db, "<item>", url="https://feed.example.org/mau")
        run_normalize(db, fixed_now)
        results.append((documents(db), runs(db)))
    assert results[0] == results[1]


def test_pending_items_are_read_in_batches_without_rereading(db):
    ids = [add_raw(db, desc(f"Texto {n}.")) for n in range(5)]
    conn = connect(db)
    try:
        run_id = start_run(conn, "normalize", T0)
        seen = []
        for pending in pending_raw_items(conn, batch_size=2):
            seen.append(pending.id)
            if pending.id == ids[0]:
                add_raw(db, desc("Chegou depois."))  # posterior ao início da leitura
            if pending.id % 2:  # só metade passa a ter documento; a outra continua pendente
                insert_source_document(
                    conn,
                    SourceDocument(
                        raw_item_id=pending.id,
                        source_id="fonte_t1",
                        title="T",
                        source_tier=SourceTier.T1,
                        status=DocumentStatus.NORMALIZED,
                    ),
                    run_id,
                    T0,
                )
    finally:
        conn.close()
    assert seen == ids


def test_pending_item_carries_endpoint_and_source_state(db):
    raw_id = add_raw(db, desc("Texto."), endpoint="feed_candidato", published_at_raw=None)
    conn = connect(db)
    try:
        (pending,) = list(pending_raw_items(conn))
    finally:
        conn.close()
    assert (pending.id, pending.source_endpoint_id, pending.endpoint_type) == (
        raw_id,
        "feed_candidato",
        "rss",
    )
    assert (pending.source_id, pending.tier, pending.registry_status) == (
        "fonte_candidata",
        "T1",
        "candidate",
    )
    assert pending.published_at_raw is None


# --- tde collect && tde normalize ------------------------------------------------------


def test_collect_then_normalize_with_fake_transport(tmp_path, monkeypatch, capsys):
    db = tmp_path / "db" / "tde.sqlite3"
    init_database(db)
    validated = {"validated_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC), "validated_by": "editor"}
    source = SourceRegistry(
        id="fonte_sintetica",
        name="Fonte sintética",
        entity_type=EntityType.PUBLIC_BODY,
        tier=SourceTier.T1,
        domains=(HOST,),
        registry_status=RegistryStatus.VALIDATED,
        **validated,
    )
    endpoint = SourceEndpoint(
        id="feed_sintetico",
        source_id="fonte_sintetica",
        endpoint_type=EndpointType.RSS,
        url=FEED_URL,
        endpoint_status=EndpointStatus.ACTIVE,
        **validated,
    )
    sync_sources(db, [source], [endpoint], now=fixed_now)
    server = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/rss.xml"): feed((RSS_FIXTURES / "valid.xml").read_bytes()),
        }
    )
    registry = CollectorRegistry([RssCollector(server.transport(), now=fixed_now)])
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    assert cli.main(["--db", str(db), "collect"]) == 0
    raw_before = table_snapshot(db, "raw_item")
    capsys.readouterr()

    assert normalize_cli(db) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"normalize: OK — {db}",
        "run: 2",
        "pendentes: 3",
        "normalizados: 3",
        "duplicados: 0",
        "sem texto: 1",
        "não suportados: 0",
        "com falha: 0",
    ]
    assert table_snapshot(db, "raw_item") == raw_before
    raw_ids = [row[0] for row in raw_before]
    docs = documents(db)
    assert [doc["raw_item_id"] for doc in docs] == raw_ids
    assert [doc["created_in_run"] for doc in docs] == [2, 2, 2]
    assert [doc["title"] for doc in docs] == [
        "Primeira notícia",
        "Segunda notícia",
        "Terceira notícia",
    ]
    assert [doc["text"] for doc in docs] == ["Resumo da primeira notícia.", "Corpo completo.", None]
    assert {doc["canonical_url"] for doc in docs} == {None}
    assert {doc["published_at"] for doc in docs} == {None}  # pubDate RFC 822 (D13)
    assert {doc["language"] for doc in docs} == {None}
    assert {doc["source_tier"] for doc in docs} == {"T1"}
    assert {doc["source_id"] for doc in docs} == {"fonte_sintetica"}

    assert normalize_cli(db) == 0
    assert len(documents(db)) == 3


# --- CLI e isolamento ---------------------------------------------------------------


def test_help_lists_normalize_without_own_options(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "normalize" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["normalize", "--help"])
    out = capsys.readouterr().out
    assert out.startswith("usage: tde normalize [-h]\n")
    for option in ("--source", "--since", "--dry-run", "--no-llm"):
        assert option not in out
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["normalize", option])
        assert excinfo.value.code == 2


def imported(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_orchestration_has_no_sql_collectors_sources_or_network():
    modules = imported(PACKAGE_DIR / "normalize_command.py")
    assert "sqlite3" not in modules
    assert not any(m.startswith("tensdireito_content_engine.collectors") for m in modules)
    assert not any(m.startswith("tensdireito_content_engine.sources") for m in modules)
    assert not any(m.split(".")[0] in {"socket", "ssl", "http", "urllib"} for m in modules)


def test_normalize_layer_has_no_storage_sqlite_collectors_or_network():
    for path in sorted((PACKAGE_DIR / "normalize").rglob("*.py")):
        for module in imported(path):
            assert module.split(".")[0] not in {"sqlite3", "socket", "ssl", "http", "urllib"}
            assert not module.startswith("tensdireito_content_engine.storage")
            assert not module.startswith("tensdireito_content_engine.collectors")


def test_storage_does_not_import_normalize_collectors_or_sources():
    for path in sorted((PACKAGE_DIR / "storage").rglob("*.py")):
        for module in imported(path):
            for layer in ("normalize", "collectors", "sources", "normalize_command"):
                assert not module.startswith(f"tensdireito_content_engine.{layer}"), (path, module)


def test_repository_sources_yaml_contains_validated_dre_source():
    import yaml

    text = (REPO_ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")
    sources = yaml.safe_load(text)
    assert "dre" in [source["id"] for source in sources]
    assert sources[0]["registry_status"] == "VALIDATED"
