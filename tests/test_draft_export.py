import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.cli import main
from tensdireito_content_engine.domain.enums import VerificationStatus
from tensdireito_content_engine.storage import (
    approve_draft,
    export_approved_drafts,
    init_database,
    list_drafts,
    persist_pending_drafts,
)

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
MESSAGE = "📢 *Apoio às famílias*\n\n• Pode pedir online\n• Prazo até junho"


def database_with_approved_drafts(tmp_path: Path) -> Path:
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
        for index in range(3):
            connection.execute(
                "INSERT INTO raw_item (source_endpoint_id, url, title, raw_content, fetched_at, "
                "content_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "endpoint",
                    f"https://example.org/story-{index}",
                    f"Notícia {index}",
                    "<item>Texto</item>",
                    NOW.isoformat(),
                    f"{index:064x}",
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )

    persist_pending_drafts(
        db,
        [(index + 1, 70.0, f"{MESSAGE} {index}") for index in range(3)],
        NOW,
    )
    assert approve_draft(db, 1, VerificationStatus.VERIFIED_EDITORIAL, NOW)
    assert approve_draft(db, 2, VerificationStatus.VERIFIED_OFFICIAL, NOW)
    return db


def test_export_filters_approved_drafts_by_verification_status(tmp_path):
    db = database_with_approved_drafts(tmp_path)

    drafts = export_approved_drafts(
        db, (VerificationStatus.VERIFIED_OFFICIAL,), NOW
    )

    assert [draft.id for draft in drafts] == [2]
    assert drafts[0].verification_status is VerificationStatus.VERIFIED_OFFICIAL
    assert drafts[0].status == "approved"


def test_export_formats_ready_to_copy_whatsapp_text(tmp_path, capsys):
    db = database_with_approved_drafts(tmp_path)

    assert main(["--db", str(db), "drafts", "export"]) == 0

    assert capsys.readouterr().out == (
        f"{MESSAGE} 0\n\n{MESSAGE} 1\n"
    )


def test_export_formats_json_and_markdown(tmp_path, capsys):
    db = database_with_approved_drafts(tmp_path)

    assert main(["--db", str(db), "drafts", "export", "--format", "json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in exported] == [1, 2]
    assert exported[0]["message"] == f"{MESSAGE} 0"

    assert main(["--db", str(db), "drafts", "export", "--format", "markdown"]) == 0
    markdown = capsys.readouterr().out
    assert "## Rascunho 1" in markdown
    assert "- Verificação: `verified_editorial`" in markdown
    assert f"{MESSAGE} 1" in markdown


def test_mark_published_updates_only_exported_drafts_and_prevents_reexport(
    tmp_path, capsys
):
    db = database_with_approved_drafts(tmp_path)
    args = [
        "--db",
        str(db),
        "drafts",
        "export",
        "--verification-status",
        "verified_official",
        "--mark-published",
    ]

    assert main(args) == 0
    assert f"{MESSAGE} 1" in capsys.readouterr().out

    saved = {draft.id: draft.status for draft in list_drafts(db, status=None)}
    assert saved == {1: "approved", 2: "published", 3: "pending"}

    assert main(args) == 0
    assert capsys.readouterr().out == "nenhum rascunho aprovado elegível para exportação\n"

    assert main([*args[:-1], "--format", "json", "--mark-published"]) == 0
    assert capsys.readouterr().out == "[]\n"
