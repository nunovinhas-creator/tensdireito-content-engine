"""Limpeza de itens antigos na base persistida (DEC-061)."""

import sqlite3
from datetime import timedelta

from test_github_issues import NOW, database_with_unverified_draft

from tensdireito_content_engine.cli import main, prune
from tensdireito_content_engine.storage import prune_raw_items


def counts(db):
    with sqlite3.connect(db) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("raw_item", "whatsapp_draft")
        )


def test_recent_items_are_kept(tmp_path):
    db = database_with_unverified_draft(tmp_path)
    assert prune_raw_items(db, NOW - timedelta(days=1)) == 0
    assert counts(db) == (1, 1)


def test_old_items_and_their_drafts_are_removed(tmp_path):
    db = database_with_unverified_draft(tmp_path)
    assert prune_raw_items(db, NOW + timedelta(days=1)) == 1
    assert counts(db) == (0, 0)


def test_cli_prune_without_database_is_ok(tmp_path):
    ok, lines = prune(tmp_path / "nao-existe.sqlite3", 60)
    assert ok and "nada a limpar" in lines[0]
    assert prune(tmp_path / "x.sqlite3", 0)[0] is False


def test_cli_prune_command(tmp_path, capsys):
    db = database_with_unverified_draft(tmp_path)
    assert main(["--db", str(db), "prune", "--days", "60"]) == 0
    assert "0 itens" in capsys.readouterr().out
