import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.cli import main
from tensdireito_content_engine.domain.enums import VerificationStatus
from tensdireito_content_engine.storage import init_database, list_drafts, persist_pending_drafts

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def database_with_item(tmp_path: Path) -> Path:
    db = tmp_path / "tde.sqlite3"
    init_database(db, now=lambda: NOW)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO source_registry (id, name, entity_type, tier, categories, domains, "
            "registry_status, created_at, updated_at) "
            "VALUES ('source', 'Fonte', 'press', 'T3', '[]', '[]', 'validated', ?, ?)",
            (NOW.isoformat(), NOW.isoformat()),
        )
        connection.execute(
            "INSERT INTO source_endpoint (id, source_id, endpoint_type, endpoint_status, "
            "created_at, updated_at) VALUES ('endpoint', 'source', 'rss', 'active', ?, ?)",
            (NOW.isoformat(), NOW.isoformat()),
        )
        connection.execute(
            "INSERT INTO raw_item (source_endpoint_id, url, title, raw_content, fetched_at, "
            "content_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "endpoint",
                "https://example.org/story",
                "Notícia útil",
                "<item>Texto</item>",
                NOW.isoformat(),
                "a" * 64,
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    return db


def test_pending_draft_persistence_is_idempotent_and_unverified(tmp_path):
    db = database_with_item(tmp_path)
    draft = (1, 70.0, "📢 *Notícia útil*")

    assert persist_pending_drafts(db, [draft], NOW) == 1
    assert persist_pending_drafts(db, [draft], NOW) == 0

    saved = list_drafts(db)
    assert len(saved) == 1
    assert saved[0].verification_status is VerificationStatus.UNVERIFIED
    assert saved[0].status == "pending"
    assert saved[0].message == draft[2]


def test_cli_lists_pending_draft_and_approves_with_explicit_verification(
    tmp_path, capsys
):
    db = database_with_item(tmp_path)
    persist_pending_drafts(db, [(1, 70.0, "📢 *Notícia útil*")], NOW)
    db_arg = ["--db", str(db)]

    assert main([*db_arg, "drafts", "list"]) == 0
    output = capsys.readouterr().out
    assert "rascunhos pendentes: 1" in output
    assert "[1] score=70 verificação=unverified estado=pending" in output
    assert "📢 *Notícia útil*" in output

    assert main(
        [
            *db_arg,
            "drafts",
            "approve",
            "1",
            "--verification-status",
            "verified_official",
        ]
    ) == 0
    approved = capsys.readouterr().out
    assert "rascunho 1: aprovado" in approved
    assert "verificação: verified_official" in approved
    assert list_drafts(db) == ()

    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT verification_status, status, approved_at FROM whatsapp_draft WHERE id = 1"
        ).fetchone()
    assert row[:2] == ("verified_official", "approved")
    assert datetime.fromisoformat(row[2]).tzinfo is UTC


def test_cli_cannot_approve_an_unverified_draft(tmp_path, capsys):
    db = database_with_item(tmp_path)
    persist_pending_drafts(db, [(1, 70.0, "draft")], NOW)

    import pytest

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--db",
                str(db),
                "drafts",
                "approve",
                "1",
                "--verification-status",
                "unverified",
            ]
        )
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_approval_is_not_repeatable(tmp_path, capsys):
    db = database_with_item(tmp_path)
    persist_pending_drafts(db, [(1, 70.0, "draft")], NOW)
    args = [
        "--db",
        str(db),
        "drafts",
        "approve",
        "1",
        "--verification-status",
        "verified_editorial",
    ]

    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 1
    assert "inexistente, não elegível ou não pendente" in capsys.readouterr().err
