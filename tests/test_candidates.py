"""Fase 2a (DEC-068): registo persistente de candidatos.

Critérios de aceitação da §9 (fase 2) da especificação que cabem no 2a: uma notícia
encontrada por dois métodos é um candidato com duas descobertas; dois runs seguidos não
criam candidatos nem transições; nenhum estado muda sem transição; a migração não perde
dados; a base recusa valores inválidos; transições com compare-and-set; `prune` respeita
as chaves; um run interrompido é retomado sem duplicar.
"""

import shutil
import sqlite3
from datetime import UTC, datetime

import pytest
from test_daily import DAY, FakeRss, config_dir, invoke_daily, item

from tensdireito_content_engine import cli
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.domain.enums import VerificationStatus
from tensdireito_content_engine.storage import candidates as candidate_storage
from tensdireito_content_engine.storage import init_database, prune_raw_items
from tensdireito_content_engine.storage.candidates import TransitionError, transition
from tensdireito_content_engine.storage.database import connect, transaction
from tensdireito_content_engine.storage.drafts import approve_draft
from tensdireito_content_engine.storage.migrator import default_migrations_dir

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def rows(db, sql, params=()):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def with_search_endpoint(sources):
    """Torna o segundo endpoint numa pesquisa do Bing (método `search`)."""
    path = sources / "sources.yaml"
    text = path.read_text(encoding="utf-8").replace(
        "https://source1.example/feed.xml",
        "https://www.bing.com/news/search?q=abono&format=rss",
    )
    path.write_text(text, encoding="utf-8")
    return sources


def daily_with_summary(monkeypatch, tmp_path, sources, collector):
    monkeypatch.setattr(cli, "default_registry", lambda: CollectorRegistry([collector]))
    db = tmp_path / "tde.sqlite3"
    summary = tmp_path / "summary.md"
    summary.write_text("", encoding="utf-8")
    code = cli.main(
        [
            "--config",
            str(sources),
            "--db",
            str(db),
            "daily",
            "--date",
            DAY.isoformat(),
            "--report-dir",
            str(tmp_path / "reports"),
            "--summary-md",
            str(summary),
        ]
    )
    return code, db, summary.read_text(encoding="utf-8")


def mixed_day(endpoint_id):
    """Uma notícia de cada destino da fase 2a."""
    return [
        item(
            endpoint_id,
            title="Segurança Social paga hoje subsídio de desemprego",
            url="https://news.example/alta",
            raw="<item><description>Texto alta.</description></item>",
        ),
        item(
            endpoint_id,
            title="Segurança Social paga hoje o subsídio de desemprego aos beneficiários",
            url="https://news.example/mesmo-tema",
            raw="<item><description>Texto mesmo tema.</description></item>",
        ),
        item(
            endpoint_id,
            title="Agricultores exigem pacote de apoios de 140 milhões",
            url="https://news.example/rever",
            raw="<item><description>Texto rever.</description></item>",
        ),
        item(
            endpoint_id,
            title="Benfica vence em Braga e reforça liderança",
            url="https://news.example/baixa",
            raw="<item><description>Texto baixa.</description></item>",
        ),
        item(
            endpoint_id,
            title="Abono de família sobe em janeiro",
            url="https://news.example/ontem",
            published="2026-10-08T10:00:00+01:00",
            raw="<item><description>Texto ontem.</description></item>",
        ),
    ]


def test_same_article_by_feed_and_search_is_one_candidate_with_two_discoveries(
    monkeypatch, tmp_path, capsys
):
    sources = with_search_endpoint(config_dir(tmp_path / "config", "feed_a", "search_b"))
    urls = {
        "feed_a": "https://news.example/abono",
        "search_b": "https://NEWS.example/abono/?utm_source=bing",
    }
    collector = FakeRss(
        lambda endpoint_id: [
            item(
                endpoint_id,
                title="Abono de família sobe em janeiro",
                url=urls[endpoint_id],
                raw=f"<item><description>Texto {endpoint_id}.</description></item>",
            )
        ]
    )
    code, db, summary = daily_with_summary(monkeypatch, tmp_path, sources, collector)
    capsys.readouterr()
    assert code == 0
    assert rows(db, "SELECT COUNT(*) FROM candidate") == [(1,)]
    assert sorted(rows(db, "SELECT method FROM candidate_discovery")) == [("rss",), ("search",)]
    assert "### Registo de candidatos" in summary
    assert "| rss | 1 | 0 | 1 | 0 | 1 |" in summary
    assert "| search | 1 | 0 | 1 | 0 | 1 |" in summary


def test_each_phase_1_decision_becomes_a_state(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    code, db, _ = invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    assert code == 0
    states = dict(rows(db, "SELECT url, state FROM candidate"))
    # As duas notícias do mesmo tema dão um rascunho (a de maior score) e um membro do grupo.
    same_topic = {
        states.pop("https://news.example/alta"),
        states.pop("https://news.example/mesmo-tema"),
    }
    assert same_topic == {"rascunho", "no_grupo"}
    assert states == {
        "https://news.example/rever": "descoberto",
        "https://news.example/baixa": "arquivado",
        "https://news.example/ontem": "fora_do_dia",
    }
    groups = rows(db, "SELECT DISTINCT group_id FROM candidate WHERE group_id IS NOT NULL")
    assert len(groups) == 1
    # O rascunho fica ligado à notícia que o originou.
    linked = rows(
        db,
        "SELECT c.state FROM whatsapp_draft d JOIN candidate c ON c.id = d.candidate_id",
    )
    assert linked == [("rascunho",)]
    # A prioridade e o motivo da fase 1 ficam no candidato.
    assert rows(db, "SELECT priority FROM candidate WHERE url LIKE '%/rever'") == [("rever",)]


def test_no_state_without_a_transition(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    for candidate_id, state in rows(
        db := tmp_path / "tde.sqlite3", "SELECT id, state FROM candidate"
    ):
        history = rows(
            db,
            "SELECT from_state, to_state, reason FROM candidate_transition "
            "WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        )
        assert history[0][0] is None and history[0][1] == "descoberto"
        assert history[-1][1] == state
        assert all(reason.strip() for _, _, reason in history)
        for (_, previous, _), (start, _, _) in zip(history, history[1:], strict=False):
            assert start == previous


def test_two_runs_do_not_create_candidates_or_transitions(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    db = tmp_path / "tde.sqlite3"
    before = {
        table: rows(db, f"SELECT COUNT(*) FROM {table}")
        for table in ("candidate", "candidate_discovery", "candidate_transition", "candidate_group")
    }
    code, _, _ = invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    assert code == 0
    after = {table: rows(db, f"SELECT COUNT(*) FROM {table}") for table in before}
    assert after == before


def test_interrupted_run_is_resumed_without_duplicates(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    original = candidate_storage._upsert_discovery
    calls = {"n": 0}

    def failing(conn, candidate_id, obs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise sqlite3.OperationalError("interrupção simulada")
        return original(conn, candidate_id, obs)

    monkeypatch.setattr(candidate_storage, "_upsert_discovery", failing)
    code, db, _ = invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    assert code == 1
    assert "interrupção simulada" in capsys.readouterr().err
    # A transacção foi desfeita: nada ficou a meio.
    assert rows(db, "SELECT COUNT(*) FROM candidate") == [(0,)]
    assert rows(db, "SELECT COUNT(*) FROM candidate_transition") == [(0,)]

    monkeypatch.setattr(candidate_storage, "_upsert_discovery", original)
    code, _, _ = invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    assert code == 0
    assert rows(db, "SELECT COUNT(*) FROM candidate") == [(5,)]
    assert rows(db, "SELECT COUNT(*) FROM candidate_discovery") == [(5,)]
    assert rows(db, "SELECT COUNT(DISTINCT url_key) FROM candidate") == [(5,)]


def test_database_rejects_values_outside_the_enumerations(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    db = tmp_path / "tde.sqlite3"
    for column, value in (("state", "inventado"), ("priority", "urgente")):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            with sqlite3.connect(db) as conn:
                conn.execute(f"UPDATE candidate SET {column} = ?", (value,))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE candidate_discovery SET method = 'telepatia'")


def test_transition_is_compare_and_set(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    db = tmp_path / "tde.sqlite3"
    (candidate_id,) = rows(db, "SELECT id FROM candidate WHERE url LIKE '%/rever'")[0]
    before = rows(db, "SELECT COUNT(*) FROM candidate_transition")
    conn = connect(db)
    try:
        with transaction(conn, "teste"):
            # Estado esperado errado: nada muda, nada é gravado.
            assert not transition(conn, candidate_id, "arquivado", "descoberto", "x", None, NOW)
        assert rows(db, "SELECT COUNT(*) FROM candidate_transition") == before
        with pytest.raises(TransitionError):
            transition(conn, candidate_id, "descoberto", "rascunho", "salto", None, NOW)
        with pytest.raises(TransitionError):
            transition(conn, candidate_id, "descoberto", "arquivado", "  ", None, NOW)
        with transaction(conn, "teste"):
            assert transition(conn, candidate_id, "descoberto", "arquivado", "teste", None, NOW)
            # Uma segunda transição concorrente sobre o mesmo estado já não se aplica.
            assert not transition(conn, candidate_id, "descoberto", "arquivado", "dup", None, NOW)
    finally:
        conn.close()
    assert rows(db, "SELECT state FROM candidate WHERE id = ?", (candidate_id,)) == [("arquivado",)]


def test_migration_0004_keeps_raw_items_and_drafts(tmp_path):
    db = tmp_path / "tde.sqlite3"
    first_three = tmp_path / "m3"
    first_three.mkdir()
    for name in ("0001_init.sql", "0002_source_document.sql", "0003_whatsapp_draft.sql"):
        shutil.copy(default_migrations_dir() / name, first_three / name)
    init_database(db, first_three)
    stamp = "2026-10-09T08:00:00.000000+00:00"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO source_registry (id, name, entity_type, tier, categories, domains, "
            "registry_status, created_at, updated_at) "
            "VALUES ('s', 'S', 'press', 'T3', '[]', '[]', 'validated', ?, ?)",
            (stamp, stamp),
        )
        conn.execute(
            "INSERT INTO source_endpoint (id, source_id, endpoint_type, url, endpoint_status, "
            "created_at, updated_at) "
            "VALUES ('e', 's', 'rss', 'https://s.example/f', 'ACTIVE', ?, ?)",
            (stamp, stamp),
        )
        conn.execute(
            "INSERT INTO raw_item (source_endpoint_id, url, title, raw_content, fetched_at, "
            "content_hash, created_at, updated_at) "
            "VALUES ('e', 'https://s.example/a', 'T', '<item/>', ?, 'h', ?, ?)",
            (stamp, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO whatsapp_draft (raw_item_id, editorial_score, verification_status, "
            "status, message, created_at, updated_at) VALUES (1, 10, 'unverified', 'pending', "
            "'m', ?, ?)",
            (stamp, stamp),
        )
        before = {
            table: conn.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("raw_item", "whatsapp_draft")
        }
    assert init_database(db).applied == ("0004_candidate",)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM raw_item").fetchall() == before["raw_item"]
        # O rascunho ganha só a coluna nova, nula.
        assert conn.execute("SELECT * FROM whatsapp_draft").fetchall() == [
            (*row, None) for row in before["whatsapp_draft"]
        ]


def test_prune_respects_keys_and_keeps_approved_drafts(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    invoke_daily(monkeypatch, tmp_path, sources, FakeRss(mixed_day))
    capsys.readouterr()
    db = tmp_path / "tde.sqlite3"
    (draft_id,) = rows(db, "SELECT id FROM whatsapp_draft")[0]
    assert approve_draft(db, draft_id, VerificationStatus.VERIFIED_EDITORIAL, NOW)
    removed = prune_raw_items(db, datetime(2030, 1, 1, tzinfo=UTC))
    assert removed == 4
    assert rows(db, "PRAGMA foreign_key_check") == []
    # Fica só o que o rascunho aprovado precisa.
    assert rows(db, "SELECT state FROM candidate") == [("rascunho",)]
    assert rows(db, "SELECT COUNT(*) FROM raw_item") == [(1,)]
    assert rows(db, "SELECT COUNT(*) FROM whatsapp_draft") == [(1,)]
    assert rows(db, "SELECT COUNT(*) FROM candidate_group") == [(1,)]


def test_empty_and_failed_endpoints_look_different_in_the_summary(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "vazio", "em_erro")

    def produce(endpoint_id):
        if endpoint_id == "em_erro":
            raise OSError("feed indisponível")
        return []

    code, _, summary = daily_with_summary(monkeypatch, tmp_path, sources, FakeRss(produce))
    capsys.readouterr()
    assert code == 2
    assert "| `vazio` | 0 | 0 | ok |" in summary
    assert "| `em_erro` | 0 | 0 | falha |" in summary
    assert "### Fontes com falha" in summary and "feed indisponível" in summary
