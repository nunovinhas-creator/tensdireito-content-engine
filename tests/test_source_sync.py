"""Testes do M2.7: `tde sources sync` (ROADMAP.md M2.7; DEC-027, DEC-028, DEC-029, DEC-030).

Offline: bases de dados e registos fictícios em directórios temporários, sem rede e sem
IA. Nenhum teste escreve em `data/` do repositório nem usa fontes ou URLs reais (os
domínios usam o TLD reservado `.invalid`).
"""

import ast
import copy
import hashlib
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from tensdireito_content_engine.cli import main
from tensdireito_content_engine.sources import load_sources
from tensdireito_content_engine.storage import (
    SourceSyncError,
    StorageError,
    SyncCounts,
    init_database,
    source_sync,
    sync_sources,
)

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)
T0_ISO = "2026-10-07T12:00:00.000000+00:00"
T1_ISO = "2026-10-07T13:00:00.000000+00:00"

REGISTRY = [
    {
        "id": "fonte_a",
        "name": "Fonte A fictícia",
        "entity_type": "public_body",
        "tier": "T1",
        "categories": ["seguranca_social"],
        "registry_status": "CANDIDATE",
        "notes": "Por validar.",
        "endpoints": [
            {
                "id": "fonte_a_pagina",
                "endpoint_type": "html_page",
                "endpoint_status": "CANDIDATE",
                "fetch": {"frequency": "daily"},
            },
            {"id": "fonte_a_manual", "endpoint_type": "manual", "endpoint_status": "CANDIDATE"},
        ],
    },
    {
        "id": "fonte_b",
        "name": "Fonte B fictícia",
        "entity_type": "specialised",
        "tier": "T2",
        "categories": ["consumo", "energia_agua"],
        "domains": ["exemplo.invalid"],
        "registry_status": "VALIDATED",
        "validated_at": "2026-10-01T09:00:00Z",
        "validated_by": "editor_ficticio",
        "endpoints": [
            {
                "id": "fonte_b_feed",
                "endpoint_type": "rss",
                "url": "https://exemplo.invalid/feed",
                "endpoint_status": "ACTIVE",
                "fetch": {"frequency": "daily"},
                "validated_at": "2026-10-01T10:00:00+01:00",
                "validated_by": "editor_ficticio",
            }
        ],
    },
    {
        "id": "fonte_c",
        "name": "Imprensa C fictícia",
        "entity_type": "press",
        "tier": "T3",
        "registry_status": "INACTIVE",
    },
]

SOURCE_IDS = ["fonte_a", "fonte_b", "fonte_c"]
ENDPOINT_IDS = ["fonte_a_manual", "fonte_a_pagina", "fonte_b_feed"]


# --- Auxiliares -------------------------------------------------------------------


def registry() -> list[dict]:
    return copy.deepcopy(REGISTRY)


def write_registry(config: Path, data: object) -> Path:
    config.mkdir(parents=True, exist_ok=True)
    path = config / "sources.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def sync(db: Path, config_file: Path, at: datetime = T0):
    loaded = load_sources(config_file)
    return sync_sources(db, loaded.sources, loaded.endpoints, now=lambda: at)


def rows(db: Path, table: str) -> dict[str, dict[str, object]]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return {
            row["id"]: dict(row)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        }


def snapshot(db: Path) -> dict[str, list[tuple]]:
    """Conteúdo integral de todas as tabelas e do esquema, para comparar antes/depois."""
    with sqlite3.connect(db) as conn:
        names = [
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ]
        data = {name: conn.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() for name in names}
        data["__schema__"] = conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    return data


def add_raw_item(db: Path, endpoint_id: str) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO raw_item (source_endpoint_id, url, title, raw_content, fetched_at, "
            "content_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                endpoint_id,
                f"https://exemplo.invalid/{endpoint_id}",
                "Título fictício",
                "Conteúdo fictício",
                T0_ISO,
                "hash",
                T0_ISO,
                T0_ISO,
            ),
        )


def set_operational_state(db: Path, endpoint_id: str) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE source_endpoint SET last_success_at = ?, last_error = ? WHERE id = ?",
            (T0_ISO, "erro fictício", endpoint_id),
        )


def endpoints_of(data: list[dict]) -> dict[str, dict]:
    return {ep["id"]: ep for source in data for ep in source.get("endpoints", [])}


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "db" / "tde.sqlite3"
    init_database(path, now=lambda: T0)
    return path


@pytest.fixture
def config(tmp_path) -> Path:
    return tmp_path / "config"


@pytest.fixture
def synced(db, config) -> Path:
    """Base com o registo de referência já sincronizado em T0."""
    sync(db, write_registry(config, registry()), T0)
    return db


def run_cli(config: Path, db: Path) -> int:
    return main(["--config", str(config), "--db", str(db), "sources", "sync"])


# --- Pré-condições ----------------------------------------------------------------


def test_missing_database_fails_without_creating_file_or_directory(tmp_path, config, capsys):
    write_registry(config, registry())
    db = tmp_path / "nao_existe" / "tde.sqlite3"
    assert run_cli(config, db) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"sources sync: ERRO — {db}",
        "- a base de dados não existe; execute `tde init` para a criar",
    ]
    assert not db.exists()
    assert not db.parent.exists()


def test_missing_database_in_existing_directory_is_not_created(tmp_path, config):
    write_registry(config, registry())
    db = tmp_path / "tde.sqlite3"
    assert run_cli(config, db) == 1
    assert not db.exists()


def test_missing_database_via_storage_raises(tmp_path):
    with pytest.raises(StorageError, match="tde init"):
        sync_sources(tmp_path / "tde.sqlite3", (), ())
    assert not (tmp_path / "tde.sqlite3").exists()


def test_empty_file_without_schema_fails_and_applies_nothing(tmp_path, config, capsys):
    write_registry(config, registry())
    db = tmp_path / "tde.sqlite3"
    db.write_bytes(b"")
    assert run_cli(config, db) == 1
    assert (
        "esquema não conforme: migrações pendentes: 0001_init, 0002_source_document, "
        "0003_whatsapp_draft, 0004_candidate; "
        "execute `tde init`"
    ) in capsys.readouterr().err
    assert db.read_bytes() == b""


def test_non_sqlite_file_fails(tmp_path, config, capsys):
    write_registry(config, registry())
    db = tmp_path / "tde.sqlite3"
    db.write_text("isto não é SQLite", encoding="utf-8")
    assert run_cli(config, db) == 1
    assert "o ficheiro não é uma base de dados SQLite" in capsys.readouterr().err
    assert db.read_text(encoding="utf-8") == "isto não é SQLite"


def test_pending_migration_fails_without_migrating(db, config, capsys):
    write_registry(config, registry())
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM schema_migration")
    before = snapshot(db)
    assert run_cli(config, db) == 1
    assert (
        "migrações pendentes: 0001_init, 0002_source_document, 0003_whatsapp_draft, "
        "0004_candidate; "
        "execute `tde init`"
    ) in (
        capsys.readouterr().err
    )
    assert snapshot(db) == before


def test_unknown_migration_fails(db, config, capsys):
    write_registry(config, registry())
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO schema_migration (version, checksum, applied_at) VALUES (9, 'x', ?)",
            (T0_ISO,),
        )
    before = snapshot(db)
    assert run_cli(config, db) == 1
    err = capsys.readouterr().err
    assert "esquema não conforme: a base de dados tem a migração 0009" in err
    assert "execute `tde init`" in err
    assert snapshot(db) == before


def test_changed_checksum_fails(db, config, capsys):
    write_registry(config, registry())
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE schema_migration SET checksum = 'outro' WHERE version = 1")
    before = snapshot(db)
    assert run_cli(config, db) == 1
    err = capsys.readouterr().err
    assert "esquema não conforme: a migração 0001_init foi alterada" in err
    assert snapshot(db) == before


def test_init_does_not_sync_sources(tmp_path, config):
    write_registry(config, registry())
    db = tmp_path / "tde.sqlite3"
    assert main(["--config", str(config), "--db", str(db), "init"]) == 0
    assert rows(db, "source_registry") == {}
    assert rows(db, "source_endpoint") == {}


# --- Validação do YAML -----------------------------------------------------------


def test_invalid_yaml_reports_validate_errors_and_leaves_db_untouched(synced, config, capsys):
    data = registry()
    data[0]["tier"] = "T9"
    del data[1]["name"]
    write_registry(config, data)
    before = snapshot(synced)

    assert main(["--config", str(config), "sources", "validate"]) == 1
    validate_errors = capsys.readouterr().err.splitlines()[1:]

    assert run_cli(config, synced) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert lines[0] == f"sources sync: ERRO — {config / 'sources.yaml'}"
    assert lines[1:] == validate_errors
    assert len(validate_errors) == 2
    assert snapshot(synced) == before


@pytest.mark.parametrize("status", ["CANDIDATE", "INACTIVE"])
def test_dec_035_active_endpoint_in_non_validated_source_fails_and_leaves_db_untouched(
    synced, config, capsys, status
):
    # DEC-035 vive na validação do registo; o sync recusa-o por DEC-028 (3), sem regra própria.
    data = registry()
    data[1]["registry_status"] = status
    data[1]["domains"] = []  # uma fonte CANDIDATE não pode ter domains (M2.2): isola DEC-035
    write_registry(config, data)
    before = snapshot(synced)

    assert run_cli(config, synced) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"sources sync: ERRO — {config / 'sources.yaml'}",
        "- sources[1].endpoints[0] (id=fonte_b_feed): "
        f"um endpoint ACTIVE exige fonte VALIDATED (fonte fonte_b: {status})",
    ]
    assert snapshot(synced) == before


def test_invalid_yaml_does_not_require_database(tmp_path, config):
    write_registry(config, [{"id": "x"}])
    db = tmp_path / "tde.sqlite3"
    assert run_cli(config, db) == 1
    assert not db.exists()


def test_missing_yaml_fails(db, tmp_path, capsys):
    before = snapshot(db)
    assert run_cli(tmp_path / "sem_config", db) == 1
    assert "ficheiro não encontrado" in capsys.readouterr().err
    assert snapshot(db) == before


def test_empty_registry_on_empty_database_is_a_no_op(db, config, capsys):
    write_registry(config, [])
    before = snapshot(db)
    assert run_cli(config, db) == 0
    assert capsys.readouterr().out.splitlines()[1:] == [
        "inseridos: 0",
        "actualizados: 0",
        "inalterados: 0",
        "removidos: 0",
    ]
    assert snapshot(db) == before


def test_empty_registry_removes_unreferenced_entries(synced, config):
    # DEC-029, *Impacto*: um YAML esvaziado é válido e remove as entradas não referenciadas.
    result = sync(synced, write_registry(config, []), T1)
    assert result.sources == SyncCounts(removed=3)
    assert result.endpoints == SyncCounts(removed=3)
    assert rows(synced, "source_registry") == {}
    assert rows(synced, "source_endpoint") == {}


def test_empty_registry_with_referenced_entries_fails(synced, config):
    add_raw_item(synced, "fonte_b_feed")
    before = snapshot(synced)
    with pytest.raises(SourceSyncError) as excinfo:
        sync(synced, write_registry(config, []), T1)
    assert excinfo.value.errors == (
        "endpoint fonte_b_feed: retirado do YAML, mas é referenciado por raw_item; "
        "mantenha-o no YAML (ex.: como INACTIVE)",
        "fonte fonte_b: retirada do YAML, mas é referenciada por raw_item através de "
        "fonte_b_feed; mantenha-a no YAML (ex.: como INACTIVE)",
    )
    assert snapshot(synced) == before


# --- Sincronização inicial -------------------------------------------------------


def test_initial_sync_inserts_everything(db, config):
    result = sync(db, write_registry(config, registry()), T0)
    assert result.path == db
    assert result.sources == SyncCounts(inserted=3)
    assert result.endpoints == SyncCounts(inserted=3)
    assert sorted(rows(db, "source_registry")) == SOURCE_IDS
    assert sorted(rows(db, "source_endpoint")) == ENDPOINT_IDS


def test_initial_sync_persists_projected_source_fields(db, config):
    sync(db, write_registry(config, registry()), T0)
    sources = rows(db, "source_registry")
    assert sources["fonte_a"] == {
        "id": "fonte_a",
        "name": "Fonte A fictícia",
        "entity_type": "public_body",
        "tier": "T1",
        "categories": '["seguranca_social"]',
        "domains": "[]",
        "registry_status": "candidate",
        "validated_at": None,
        "validated_by": None,
        "notes": "Por validar.",
        "created_at": T0_ISO,
        "updated_at": T0_ISO,
    }
    assert sources["fonte_b"]["categories"] == '["consumo", "energia_agua"]'
    assert sources["fonte_b"]["domains"] == '["exemplo.invalid"]'
    assert sources["fonte_b"]["registry_status"] == "validated"
    assert sources["fonte_b"]["validated_at"] == "2026-10-01T09:00:00.000000+00:00"
    assert sources["fonte_b"]["validated_by"] == "editor_ficticio"
    assert sources["fonte_c"]["registry_status"] == "inactive"


def test_initial_sync_persists_projected_endpoint_fields(db, config):
    sync(db, write_registry(config, registry()), T0)
    endpoints = rows(db, "source_endpoint")
    assert endpoints["fonte_b_feed"] == {
        "id": "fonte_b_feed",
        "source_id": "fonte_b",
        "endpoint_type": "rss",
        "url": "https://exemplo.invalid/feed",
        "fetch": None,  # fora da projecção do M2.7 (DEC-028)
        "endpoint_status": "active",
        "validated_at": "2026-10-01T09:00:00.000000+00:00",  # +01:00 convertido para UTC
        "validated_by": "editor_ficticio",
        "last_success_at": None,
        "last_error": None,
        "created_at": T0_ISO,
        "updated_at": T0_ISO,
    }
    assert endpoints["fonte_a_pagina"]["url"] is None
    assert endpoints["fonte_a_pagina"]["endpoint_status"] == "candidate"
    assert endpoints["fonte_a_manual"]["endpoint_type"] == "manual"


def test_initial_sync_respects_foreign_keys(db, config):
    sync(db, write_registry(config, registry()), T0)
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    endpoints = rows(db, "source_endpoint")
    assert {ep_id: ep["source_id"] for ep_id, ep in endpoints.items()} == {
        "fonte_a_manual": "fonte_a",
        "fonte_a_pagina": "fonte_a",
        "fonte_b_feed": "fonte_b",
    }


def test_repository_fixture_syncs(db):
    fixture = Path(__file__).parent / "fixtures" / "sources" / "sources.yaml"
    result = sync(db, fixture, T0)
    assert result.total == SyncCounts(inserted=6)


# --- Idempotência ----------------------------------------------------------------


def test_second_sync_is_idempotent(synced, config):
    before = snapshot(synced)
    result = sync(synced, config / "sources.yaml", T1)
    assert result.sources == SyncCounts(unchanged=3)
    assert result.endpoints == SyncCounts(unchanged=3)
    assert snapshot(synced) == before  # nem updated_at nem created_at mudam


def test_second_sync_does_not_modify_database_file(synced, config):
    digest = hashlib.sha256(synced.read_bytes()).hexdigest()
    sync(synced, config / "sources.yaml", T1)
    assert hashlib.sha256(synced.read_bytes()).hexdigest() == digest


def test_second_sync_preserves_operational_state(synced, config):
    set_operational_state(synced, "fonte_b_feed")
    sync(synced, config / "sources.yaml", T1)
    endpoint = rows(synced, "source_endpoint")["fonte_b_feed"]
    assert endpoint["last_success_at"] == T0_ISO
    assert endpoint["last_error"] == "erro fictício"
    assert endpoint["updated_at"] == T0_ISO


# --- Actualizações ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "stored"),
    [
        ("name", "Fonte A renomeada", "Fonte A renomeada"),
        ("entity_type", "government", "government"),
        ("tier", "T2", "T2"),
        ("categories", ["seguranca_social", "consumo"], '["seguranca_social", "consumo"]'),
        ("notes", None, None),
    ],
)
def test_projected_source_field_change_is_an_update(synced, config, field, value, stored):
    data = registry()
    data[0][field] = value
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(updated=1, unchanged=2)
    assert result.endpoints == SyncCounts(unchanged=3)
    sources = rows(synced, "source_registry")
    assert sources["fonte_a"][field] == stored
    assert sources["fonte_a"]["updated_at"] == T1_ISO
    assert sources["fonte_a"]["created_at"] == T0_ISO
    assert sources["fonte_b"]["updated_at"] == T0_ISO
    assert sources["fonte_c"]["updated_at"] == T0_ISO


def test_source_validation_change_is_an_update(synced, config):
    data = registry()
    data[2].update(
        registry_status="VALIDATED",
        validated_at="2026-10-05T08:00:00+00:00",
        validated_by="editor_ficticio",
        domains=["outro.invalid"],
    )
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(updated=1, unchanged=2)
    source = rows(synced, "source_registry")["fonte_c"]
    assert source["registry_status"] == "validated"
    assert source["validated_at"] == "2026-10-05T08:00:00.000000+00:00"
    assert source["validated_by"] == "editor_ficticio"
    assert source["domains"] == '["outro.invalid"]'


def test_projected_endpoint_field_change_is_an_update(synced, config):
    data = registry()
    endpoints_of(data)["fonte_b_feed"]["url"] = "https://exemplo.invalid/outro-feed"
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(unchanged=3)
    assert result.endpoints == SyncCounts(updated=1, unchanged=2)
    endpoints = rows(synced, "source_endpoint")
    assert endpoints["fonte_b_feed"]["url"] == "https://exemplo.invalid/outro-feed"
    assert endpoints["fonte_b_feed"]["updated_at"] == T1_ISO
    assert endpoints["fonte_b_feed"]["created_at"] == T0_ISO
    assert endpoints["fonte_a_pagina"]["updated_at"] == T0_ISO


def test_fetch_only_change_is_unchanged(synced, config):
    data = registry()
    endpoints_of(data)["fonte_b_feed"]["fetch"] = {"frequency": "hourly", "max_items": 10}
    endpoints_of(data)["fonte_a_manual"]["fetch"] = {"frequency": "weekly"}
    before = snapshot(synced)
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(unchanged=3)
    assert snapshot(synced) == before
    assert rows(synced, "source_endpoint")["fonte_b_feed"]["fetch"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"url": "https://exemplo.invalid/novo"},
        {"endpoint_status": "INACTIVE"},
        {"endpoint_status": "VALIDATED", "validated_at": "2026-10-06T00:00:00Z"},
    ],
)
def test_update_preserves_operational_state(synced, config, change):
    set_operational_state(synced, "fonte_b_feed")
    data = registry()
    endpoints_of(data)["fonte_b_feed"].update(change)
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(updated=1, unchanged=2)
    endpoint = rows(synced, "source_endpoint")["fonte_b_feed"]
    assert endpoint["last_success_at"] == T0_ISO
    assert endpoint["last_error"] == "erro fictício"
    assert endpoint["updated_at"] == T1_ISO


def test_update_does_not_touch_fetch_column(synced, config):
    # `fetch` está fora da projecção: o sync não o escreve nem o anula.
    with sqlite3.connect(synced) as conn:
        conn.execute("UPDATE source_endpoint SET fetch = '{}' WHERE id = 'fonte_b_feed'")
    data = registry()
    endpoints_of(data)["fonte_b_feed"]["endpoint_status"] = "INACTIVE"
    sync(synced, write_registry(config, data), T1)
    assert rows(synced, "source_endpoint")["fonte_b_feed"]["fetch"] == "{}"


def test_manual_edit_of_projected_field_is_reverted(synced, config):
    with sqlite3.connect(synced) as conn:
        conn.execute("UPDATE source_registry SET name = 'editado à mão' WHERE id = 'fonte_a'")
        conn.execute("UPDATE source_endpoint SET url = 'x' WHERE id = 'fonte_b_feed'")
    result = sync(synced, config / "sources.yaml", T1)
    assert result.total == SyncCounts(updated=2, unchanged=4)
    assert rows(synced, "source_registry")["fonte_a"]["name"] == "Fonte A fictícia"
    assert rows(synced, "source_endpoint")["fonte_b_feed"]["url"] == (
        "https://exemplo.invalid/feed"
    )


def test_sync_never_writes_yaml(synced, config):
    path = config / "sources.yaml"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(synced) as conn:
        conn.execute("UPDATE source_registry SET name = 'editado à mão' WHERE id = 'fonte_a'")
    assert run_cli(config, synced) == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


# --- Inserções -------------------------------------------------------------------


def test_new_source_is_inserted(synced, config):
    data = registry()
    data.append({"id": "fonte_d", "name": "D", "entity_type": "other", "tier": "T4"})
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(inserted=1, unchanged=3)
    source = rows(synced, "source_registry")["fonte_d"]
    assert source["created_at"] == source["updated_at"] == T1_ISO
    assert source["registry_status"] == "candidate"


def test_new_endpoint_is_inserted(synced, config):
    data = registry()
    data[2]["endpoints"] = [{"id": "fonte_c_manual", "endpoint_type": "manual"}]
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(unchanged=3)
    assert result.endpoints == SyncCounts(inserted=1, unchanged=3)
    endpoint = rows(synced, "source_endpoint")["fonte_c_manual"]
    assert endpoint["source_id"] == "fonte_c"
    assert endpoint["created_at"] == endpoint["updated_at"] == T1_ISO


def test_new_source_with_new_endpoint_is_inserted_in_fk_order(synced, config):
    data = registry()
    data.append(
        {
            "id": "fonte_d",
            "name": "D",
            "entity_type": "other",
            "tier": "T4",
            "endpoints": [{"id": "fonte_d_manual", "endpoint_type": "manual"}],
        }
    )
    result = sync(synced, write_registry(config, data), T1)
    assert result.total == SyncCounts(inserted=2, unchanged=6)
    assert rows(synced, "source_endpoint")["fonte_d_manual"]["source_id"] == "fonte_d"


def test_changing_an_id_removes_old_and_inserts_new(synced, config):
    data = registry()
    endpoints_of(data)["fonte_a_manual"]["id"] = "fonte_a_manual_v2"
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(inserted=1, unchanged=2, removed=1)
    assert sorted(rows(synced, "source_endpoint")) == [
        "fonte_a_manual_v2",
        "fonte_a_pagina",
        "fonte_b_feed",
    ]


# --- Remoções (DEC-029) ----------------------------------------------------------


def test_removed_endpoint_without_raw_item_is_deleted(synced, config):
    data = registry()
    data[0]["endpoints"] = data[0]["endpoints"][:1]
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(unchanged=2, removed=1)
    assert "fonte_a_manual" not in rows(synced, "source_endpoint")


def test_removed_source_with_endpoints_without_raw_item_is_deleted(synced, config):
    data = registry()
    del data[0]
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(unchanged=2, removed=1)
    assert result.endpoints == SyncCounts(unchanged=1, removed=2)
    assert sorted(rows(synced, "source_registry")) == ["fonte_b", "fonte_c"]
    assert sorted(rows(synced, "source_endpoint")) == ["fonte_b_feed"]


def test_removed_endpoint_with_raw_item_fails_and_rolls_back(synced, config):
    add_raw_item(synced, "fonte_a_manual")
    data = registry()
    data[0]["endpoints"] = data[0]["endpoints"][:1]
    data[0]["name"] = "Alteração que não pode ficar"
    data.append({"id": "fonte_d", "name": "D", "entity_type": "other", "tier": "T4"})
    write_registry(config, data)
    before = snapshot(synced)
    with pytest.raises(SourceSyncError) as excinfo:
        sync(synced, config / "sources.yaml", T1)
    assert excinfo.value.errors == (
        "endpoint fonte_a_manual: retirado do YAML, mas é referenciado por raw_item; "
        "mantenha-o no YAML (ex.: como INACTIVE)",
    )
    assert snapshot(synced) == before


def test_removed_source_with_referenced_endpoint_fails(synced, config, capsys):
    add_raw_item(synced, "fonte_a_pagina")
    data = registry()
    del data[0]
    write_registry(config, data)
    before = snapshot(synced)
    assert run_cli(config, synced) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"sources sync: ERRO — {synced}",
        "- endpoint fonte_a_pagina: retirado do YAML, mas é referenciado por raw_item; "
        "mantenha-o no YAML (ex.: como INACTIVE)",
        "- fonte fonte_a: retirada do YAML, mas é referenciada por raw_item através de "
        "fonte_a_pagina; mantenha-a no YAML (ex.: como INACTIVE)",
    ]
    assert snapshot(synced) == before


def test_entry_kept_as_inactive_is_the_way_to_retire_a_used_endpoint(synced, config):
    add_raw_item(synced, "fonte_a_manual")
    data = registry()
    endpoints_of(data)["fonte_a_manual"]["endpoint_status"] = "INACTIVE"
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(updated=1, unchanged=2)
    assert rows(synced, "source_endpoint")["fonte_a_manual"]["endpoint_status"] == "inactive"


# --- Alterações estruturais (DEC-029) --------------------------------------------


def move_endpoint(data: list[dict], endpoint_id: str, source_index: int) -> None:
    for source in data:
        endpoints = source.get("endpoints", [])
        for endpoint in endpoints:
            if endpoint["id"] == endpoint_id:
                endpoints.remove(endpoint)
                data[source_index].setdefault("endpoints", []).append(endpoint)
                return
    raise AssertionError(endpoint_id)


def test_source_id_change_without_raw_item_is_applied(synced, config):
    data = registry()
    move_endpoint(data, "fonte_a_manual", 2)
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(updated=1, unchanged=2)
    endpoint = rows(synced, "source_endpoint")["fonte_a_manual"]
    assert endpoint["source_id"] == "fonte_c"
    assert endpoint["updated_at"] == T1_ISO


def test_source_id_change_to_new_source_and_old_source_removed(synced, config):
    data = registry()
    data.append({"id": "fonte_d", "name": "D", "entity_type": "other", "tier": "T4"})
    move_endpoint(data, "fonte_a_manual", 3)
    move_endpoint(data, "fonte_a_pagina", 3)
    del data[0]
    result = sync(synced, write_registry(config, data), T1)
    assert result.sources == SyncCounts(inserted=1, unchanged=2, removed=1)
    assert result.endpoints == SyncCounts(updated=2, unchanged=1)
    endpoints = rows(synced, "source_endpoint")
    assert endpoints["fonte_a_manual"]["source_id"] == "fonte_d"
    assert endpoints["fonte_a_pagina"]["source_id"] == "fonte_d"


def test_source_id_change_with_raw_item_fails(synced, config):
    add_raw_item(synced, "fonte_a_manual")
    data = registry()
    move_endpoint(data, "fonte_a_manual", 2)
    write_registry(config, data)
    before = snapshot(synced)
    with pytest.raises(SourceSyncError) as excinfo:
        sync(synced, config / "sources.yaml", T1)
    assert excinfo.value.errors == (
        "endpoint fonte_a_manual: source_id mudou (fonte_a → fonte_c), mas o endpoint é "
        "referenciado por raw_item; represente-o como um endpoint novo, com id novo",
    )
    assert snapshot(synced) == before


def test_endpoint_type_change_without_raw_item_is_applied(synced, config):
    data = registry()
    endpoints_of(data)["fonte_a_pagina"]["endpoint_type"] = "rss"
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(updated=1, unchanged=2)
    assert rows(synced, "source_endpoint")["fonte_a_pagina"]["endpoint_type"] == "rss"


def test_endpoint_type_change_with_raw_item_fails(synced, config):
    add_raw_item(synced, "fonte_a_pagina")
    data = registry()
    endpoints_of(data)["fonte_a_pagina"]["endpoint_type"] = "rss"
    write_registry(config, data)
    before = snapshot(synced)
    with pytest.raises(SourceSyncError) as excinfo:
        sync(synced, config / "sources.yaml", T1)
    assert excinfo.value.errors == (
        "endpoint fonte_a_pagina: endpoint_type mudou (html_page → rss), mas o endpoint é "
        "referenciado por raw_item; represente-o como um endpoint novo, com id novo",
    )
    assert snapshot(synced) == before


def test_other_changes_to_referenced_endpoint_are_applied(synced, config):
    add_raw_item(synced, "fonte_b_feed")
    set_operational_state(synced, "fonte_b_feed")
    data = registry()
    endpoints_of(data)["fonte_b_feed"]["url"] = "https://exemplo.invalid/novo"
    result = sync(synced, write_registry(config, data), T1)
    assert result.endpoints == SyncCounts(updated=1, unchanged=2)
    endpoint = rows(synced, "source_endpoint")["fonte_b_feed"]
    assert endpoint["url"] == "https://exemplo.invalid/novo"
    assert endpoint["last_error"] == "erro fictício"


def test_all_conflicts_are_reported_together(synced, config):
    add_raw_item(synced, "fonte_a_manual")
    add_raw_item(synced, "fonte_a_pagina")
    add_raw_item(synced, "fonte_b_feed")
    data = registry()
    endpoints_of(data)["fonte_a_pagina"]["endpoint_type"] = "rss"
    move_endpoint(data, "fonte_a_pagina", 2)
    data[0]["endpoints"] = []
    del data[1]
    write_registry(config, data)
    before = snapshot(synced)
    with pytest.raises(SourceSyncError) as excinfo:
        sync(synced, config / "sources.yaml", T1)
    assert [error.split(":")[0] for error in excinfo.value.errors] == [
        "endpoint fonte_a_pagina",
        "endpoint fonte_a_pagina",
        "endpoint fonte_a_manual",
        "endpoint fonte_b_feed",
        "fonte fonte_b",
    ]
    assert snapshot(synced) == before


# --- Atomicidade -----------------------------------------------------------------


def test_failure_in_the_middle_of_writes_rolls_back_everything(synced, config):
    # Falha injectada: as fontes já foram escritas quando a inserção do endpoint falha.
    with sqlite3.connect(synced) as conn:
        conn.execute(
            "CREATE TRIGGER falha_injectada BEFORE INSERT ON source_endpoint "
            "BEGIN SELECT RAISE(ABORT, 'falha injectada'); END"
        )
    data = registry()
    data[0]["name"] = "Alterada"
    data.append(
        {
            "id": "fonte_d",
            "name": "D",
            "entity_type": "other",
            "tier": "T4",
            "endpoints": [{"id": "fonte_d_manual", "endpoint_type": "manual"}],
        }
    )
    del data[2]
    write_registry(config, data)
    before = snapshot(synced)
    with pytest.raises(StorageError, match="a sincronização falhou: falha injectada"):
        sync(synced, config / "sources.yaml", T1)
    assert snapshot(synced) == before


def test_failure_on_first_sync_leaves_tables_empty(db, config, capsys):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TRIGGER falha_injectada BEFORE INSERT ON source_endpoint "
            "WHEN NEW.id = 'fonte_b_feed' BEGIN SELECT RAISE(ABORT, 'falha injectada'); END"
        )
    write_registry(config, registry())
    assert run_cli(config, db) == 1
    assert capsys.readouterr().err.splitlines() == [
        f"sources sync: ERRO — {db}",
        "- a sincronização falhou: falha injectada",
    ]
    assert rows(db, "source_registry") == {}
    assert rows(db, "source_endpoint") == {}


def test_database_is_usable_after_rollback(synced, config):
    add_raw_item(synced, "fonte_a_manual")
    data = registry()
    del data[0]
    with pytest.raises(SourceSyncError):
        sync(synced, write_registry(config, data), T1)
    result = sync(synced, write_registry(config, registry()), T2)
    assert result.total == SyncCounts(unchanged=6)


# --- Sem `run` nem alterações de esquema -----------------------------------------


def test_sync_creates_no_run_and_keeps_schema(db, config):
    schema_before = snapshot(db)["__schema__"]
    migrations_before = snapshot(db)["schema_migration"]
    sync(db, write_registry(config, registry()), T0)
    after = snapshot(db)
    assert after["run"] == []
    assert after["raw_item"] == []
    assert after["__schema__"] == schema_before
    assert after["schema_migration"] == migrations_before


def code_strings(path: Path) -> str:
    """Literais de texto do código (sem docstrings nem comentários): onde vive o SQL."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return "\n".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    )


def test_sync_queries_avoid_sqlite_only_constructs():
    # DEC-013: só SELECT/INSERT/UPDATE/DELETE simples; sem INSERT OR REPLACE nem PRAGMA.
    sql = code_strings(Path(source_sync.__file__))
    assert "INSERT INTO" in sql and "UPDATE" in sql and "DELETE FROM" in sql
    for construct in (
        r"\bINSERT\s+OR\b",
        r"\bREPLACE\b",
        r"\bUPSERT\b",
        r"\bPRAGMA\b",
        r"\bON\s+CONFLICT\b",
        r"\bRETURNING\b",
    ):
        assert not re.search(construct, sql, re.IGNORECASE), construct


# --- CLI -------------------------------------------------------------------------


def test_cli_first_and_second_sync_output(db, config, capsys):
    write_registry(config, registry())
    assert run_cli(config, db) == 0
    first = capsys.readouterr()
    assert first.err == ""
    assert first.out.splitlines() == [
        f"sources sync: OK — {db}",
        "inseridos: 6",
        "actualizados: 0",
        "inalterados: 0",
        "removidos: 0",
    ]
    assert run_cli(config, db) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"sources sync: OK — {db}",
        "inseridos: 0",
        "actualizados: 0",
        "inalterados: 6",
        "removidos: 0",
    ]


def test_cli_counts_mixed_changes(synced, config, capsys):
    data = registry()
    data[0]["name"] = "Alterada"
    data[0]["endpoints"] = data[0]["endpoints"][:1]
    data.append({"id": "fonte_d", "name": "D", "entity_type": "other", "tier": "T4"})
    write_registry(config, data)
    assert run_cli(config, synced) == 0
    assert capsys.readouterr().out.splitlines()[1:] == [
        "inseridos: 1",
        "actualizados: 1",
        "inalterados: 4",
        "removidos: 1",
    ]


def test_cli_uses_db_env_when_no_option(db, config, monkeypatch, capsys):
    write_registry(config, registry())
    monkeypatch.setenv("TDE_DB_PATH", str(db))
    assert main(["--config", str(config), "sources", "sync"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"sources sync: OK — {db}"


def test_cli_default_paths_are_relative_to_working_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TDE_DB_PATH", raising=False)
    write_registry(tmp_path / "config", registry())
    assert main(["sources", "sync"]) == 1
    assert "execute `tde init`" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()
    assert main(["init"]) == 0
    assert main(["sources", "sync"]) == 0
    assert "inseridos: 6" in capsys.readouterr().out


def test_sync_appears_in_sources_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["sources", "--help"])
    assert excinfo.value.code == 0
    assert "sync" in capsys.readouterr().out
