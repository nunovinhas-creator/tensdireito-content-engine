import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tensdireito_content_engine.cli import main
from tensdireito_content_engine.domain.enums import VerificationStatus
from tensdireito_content_engine.github_issues import (
    GitHubIssueError,
    sync_draft_issues,
)
from tensdireito_content_engine.storage import (
    DraftIssueData,
    approve_draft,
    init_database,
    persist_pending_drafts,
)

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
SOURCE_URL = "https://example.org/story"
MESSAGE = "📢 *Notícia útil*\n\n• Resumo por validar\n• Confirme os factos"


def database_with_unverified_draft(tmp_path: Path) -> Path:
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
                SOURCE_URL,
                "Notícia útil",
                "<item>Texto</item>",
                NOW.isoformat(),
                "a" * 64,
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    assert persist_pending_drafts(db, [(1, 72.5, MESSAGE)], NOW) == 1
    return db


def test_sync_creates_labeled_issue_with_review_details(monkeypatch, tmp_path):
    db = database_with_unverified_draft(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        assert kwargs["text"] is True
        commands.append(command)
        if command[:3] == ["gh", "label", "list"]:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        if command[:3] == ["gh", "label", "create"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(
                returncode=0,
                stdout='[{"number": 9, "body": null}]',
                stderr="",
            )
        if command[:3] == ["gh", "issue", "create"]:
            return SimpleNamespace(
                returncode=0, stdout="https://github.com/example/repo/issues/42\n", stderr=""
            )
        raise AssertionError(command)

    monkeypatch.setattr("tensdireito_content_engine.github_issues.subprocess.run", fake_run)
    result = sync_draft_issues(db)

    assert result.created == ("https://github.com/example/repo/issues/42",)
    assert result.already_present == 0
    create_args = commands[-1]
    assert create_args[create_args.index("--title") + 1] == "[Rascunho WhatsApp] Notícia útil"
    assert create_args[create_args.index("--label") + 1] == "draft-whatsapp"
    body = create_args[create_args.index("--body") + 1]
    assert MESSAGE in body
    assert "Score de relevância:** 72.5/100" in body
    assert f"Fonte original:** {SOURCE_URL}" in body
    assert "Copie o texto para o WhatsApp e feche a issue após publicação." in body
    assert SOURCE_URL in body


@pytest.mark.parametrize(
    ("state", "wrapped_url"),
    [("OPEN", SOURCE_URL), ("CLOSED", SOURCE_URL), ("OPEN", f"```{SOURCE_URL}```")],
)
def test_sync_is_idempotent_when_source_issue_already_exists(
    monkeypatch, tmp_path, state, wrapped_url
):
    db = database_with_unverified_draft(tmp_path)
    existing_issue_body = f"Earlier review\n<!-- tensdireito-draft-source: {wrapped_url} -->"
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        assert kwargs["text"] is True
        commands.append(command)
        if command[:3] == ["gh", "label", "list"]:
            return SimpleNamespace(
                returncode=0, stdout=json.dumps([{"name": "draft-whatsapp"}]), stderr=""
            )
        if command[:3] == ["gh", "issue", "list"]:
            issue = {"number": 42, "body": existing_issue_body, "state": state}
            return SimpleNamespace(returncode=0, stdout=json.dumps([issue]), stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("tensdireito_content_engine.github_issues.subprocess.run", fake_run)

    result = sync_draft_issues(db)

    assert result.created == ()
    assert result.already_present == 1
    assert not any(command[:3] == ["gh", "issue", "create"] for command in commands)
    assert commands[-1][commands[-1].index("--state") + 1] == "all"


def test_sync_does_not_require_github_when_there_are_no_drafts(monkeypatch, tmp_path):
    db = database_with_unverified_draft(tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM whatsapp_draft")

    def unexpected_gh_call(*args, **kwargs):
        raise AssertionError(f"gh não deve ser chamado sem rascunhos pendentes: {args}, {kwargs}")

    monkeypatch.setattr(
        "tensdireito_content_engine.github_issues.subprocess.run", unexpected_gh_call
    )

    assert sync_draft_issues(db).created == ()


def test_sync_does_not_include_approved_drafts(monkeypatch, tmp_path):
    db = database_with_unverified_draft(tmp_path)
    assert approve_draft(db, 1, VerificationStatus.VERIFIED_EDITORIAL, NOW)

    def unexpected_gh_call(*args, **kwargs):
        raise AssertionError(
            f"gh não deve ser chamado sem rascunhos não verificados: {args}, {kwargs}"
        )

    monkeypatch.setattr(
        "tensdireito_content_engine.github_issues.subprocess.run", unexpected_gh_call
    )

    assert sync_draft_issues(db).created == ()


def test_sync_creates_at_most_one_issue_per_source_reference(monkeypatch, tmp_path):
    db = database_with_unverified_draft(tmp_path)
    commands: list[list[str]] = []

    def draft_rows(path):
        assert path == db
        return (
            DraftIssueData(1, 72.5, MESSAGE, "Notícia útil", SOURCE_URL),
            DraftIssueData(2, 73.0, MESSAGE, "Notícia útil atualizada", SOURCE_URL),
        )

    monkeypatch.setattr(
        "tensdireito_content_engine.github_issues.list_unverified_drafts_for_issues",
        draft_rows,
    )

    def fake_run(command, **kwargs):
        assert kwargs["text"] is True
        commands.append(command)
        if command[:3] == ["gh", "label", "list"]:
            return SimpleNamespace(returncode=0, stdout='[{"name":"draft-whatsapp"}]', stderr="")
        if command[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        if command[:3] == ["gh", "issue", "create"]:
            return SimpleNamespace(returncode=0, stdout="issue-1\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("tensdireito_content_engine.github_issues.subprocess.run", fake_run)

    result = sync_draft_issues(db)

    assert result.created == ("issue-1",)
    assert result.already_present == 1
    assert len([command for command in commands if command[:3] == ["gh", "issue", "create"]]) == 1


def test_sync_reports_github_errors_in_cli(monkeypatch, tmp_path, capsys):
    db = database_with_unverified_draft(tmp_path)

    def failed_run(command, **kwargs):
        assert command[:3] == ["gh", "label", "list"]
        assert kwargs["text"] is True
        return SimpleNamespace(returncode=1, stdout="", stderr="not authenticated")

    monkeypatch.setattr("tensdireito_content_engine.github_issues.subprocess.run", failed_run)

    assert main(["--db", str(db), "drafts", "sync-issues"]) == 1
    assert "not authenticated" in capsys.readouterr().err


def test_sync_rejects_invalid_github_json(monkeypatch, tmp_path):
    db = database_with_unverified_draft(tmp_path)

    def invalid_json(command, **kwargs):
        assert command[0] == "gh"
        assert kwargs["text"] is True
        return SimpleNamespace(returncode=0, stdout="{", stderr="")

    monkeypatch.setattr(
        "tensdireito_content_engine.github_issues.subprocess.run",
        invalid_json,
    )

    with pytest.raises(GitHubIssueError, match="JSON inválido"):
        sync_draft_issues(db)


def test_sync_adds_area_labels_and_creates_missing_ones(monkeypatch, tmp_path):
    from tensdireito_content_engine.topics import Area, TopicMap

    db = database_with_unverified_draft(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:3] == ["gh", "label", "list"]:
            return SimpleNamespace(
                returncode=0, stdout=json.dumps([{"name": "draft-whatsapp"}]), stderr=""
            )
        if command[:3] in (["gh", "label", "create"], ["gh", "issue", "list"]):
            out = "[]" if command[:3] == ["gh", "issue", "list"] else ""
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        if command[:3] == ["gh", "issue", "create"]:
            return SimpleNamespace(returncode=0, stdout="https://x/issues/1\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("tensdireito_content_engine.github_issues.subprocess.run", fake_run)
    topic_map = TopicMap(
        areas=(Area("familia", "Família", ("noticia util",)), Area("x", "Outra", ("zzz",)))
    )
    sync_draft_issues(db, topic_map)

    created = [c for c in commands if c[:3] == ["gh", "label", "create"]]
    assert [c[3] for c in created] == ["área: Família"]
    create = commands[-1]
    labels = [create[i + 1] for i, arg in enumerate(create) if arg == "--label"]
    assert labels == ["draft-whatsapp", "área: Família"]
    issue_list = next(c for c in commands if c[:3] == ["gh", "issue", "list"])
    assert issue_list[issue_list.index("--limit") + 1] == "1000000"


def test_close_stale_closes_only_issues_older_than_the_limit(monkeypatch):
    from tensdireito_content_engine.github_issues import close_stale_draft_issues

    commands: list[list[str]] = []
    issues = [
        {"number": 5, "createdAt": "2026-10-05T10:00:00Z"},
        {"number": 7, "createdAt": "2026-10-08T13:00:00Z"},
        {"number": 6, "createdAt": "2026-10-01T10:00:00Z"},
    ]

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:3] == ["gh", "issue", "list"]:
            assert command[command.index("--state") + 1] == "open"
            assert command[command.index("--label") + 1] == "draft-whatsapp"
            return SimpleNamespace(returncode=0, stdout=json.dumps(issues), stderr="")
        if command[:3] == ["gh", "issue", "close"]:
            assert command[command.index("--reason") + 1] == "not planned"
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("tensdireito_content_engine.github_issues.subprocess.run", fake_run)
    result = close_stale_draft_issues(3, now=datetime(2026, 10, 11, 12, tzinfo=UTC))

    assert result.closed == (5, 6)
    assert [c[3] for c in commands if c[:3] == ["gh", "issue", "close"]] == ["5", "6"]


def test_close_stale_rejects_invalid_days():
    from tensdireito_content_engine.github_issues import close_stale_draft_issues

    with pytest.raises(ValueError):
        close_stale_draft_issues(0)


def test_area_label_has_no_commas_and_fits_github_limit():
    from tensdireito_content_engine.github_issues import area_label

    assert area_label("Idosos, Incapacidade e Cuidadores") == (
        "área: Idosos / Incapacidade e Cuidadores"
    )
    assert len(area_label("x" * 80)) == 50
