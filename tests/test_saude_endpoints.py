"""Saúde de cada endpoint (DEC-072; especificação §3.3 e §5): ok, vazio, suspeito, falha."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from _fake_http import HOST, NO_ROBOTS, FakeServer, Reply, feed

from tensdireito_content_engine.collect import EndpointOutcome, _with_health, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.collectors.rss import RssCollector
from tensdireito_content_engine.domain import (
    DomainValidationError,
    EndpointStatus,
    EndpointType,
    SourceEndpoint,
)
from tensdireito_content_engine.sources import SourceRegistryError, load_sources
from tensdireito_content_engine.storage import (
    init_database,
    previous_run_stats,
    start_run,
    sync_sources,
)

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
FEED_FIXTURE = (Path(__file__).parent / "fixtures" / "rss" / "valid.xml").read_bytes()  # 3 itens
EMPTY_FEED = b"<rss><channel><title>t</title></channel></rss>"
NOT_FOUND = Reply(404, {"Content-Type": "text/html"})


def outcome(result="success", new=0, existing=0, error=None) -> EndpointOutcome:
    return EndpointOutcome(id="ep", result=result, new=new, existing=existing, error=error)


# --- Regras -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "previous", "minimum", "state", "warning"),
    [
        (outcome(new=3), None, None, "ok", None),
        (outcome(), None, None, "vazio", None),
        (outcome(), ("success", 5), None, "vazio", None),
        (outcome("failed", error="HTTP 404"), None, None, "falha", None),
        (outcome("failed", error="HTTP 404"), ("success", 5), None, "falha", None),
        (
            outcome("failed", error="HTTP 404"),
            ("failed", 0),
            None,
            "falha",
            "falha em 2 runs seguidos",
        ),
        # abaixo do mínimo só no primeiro run: ainda não é suspeito
        (outcome(new=2), None, 10, "ok", None),
        (outcome(new=2), ("success", 12), 10, "ok", None),
        (outcome(), ("success", 12), 10, "vazio", None),
        # abaixo do mínimo em 2 runs seguidos
        (
            outcome(new=1, existing=1),
            ("success", 4),
            10,
            "suspeito",
            "abaixo do mínimo esperado (2 < 10) em 2 runs seguidos",
        ),
        (
            outcome(),
            ("success", 0),
            10,
            "suspeito",
            "abaixo do mínimo esperado (0 < 10) em 2 runs seguidos",
        ),
        # uma falha no run anterior não conta como "abaixo do mínimo"
        (outcome(new=2), ("failed", 0), 10, "ok", None),
        (outcome(new=10), ("success", 2), 10, "ok", None),
    ],
)
def test_health_rules(current, previous, minimum, state, warning):
    minimums = {} if minimum is None else {"ep": minimum}
    result = _with_health(current, previous, minimums)
    assert (result.state, result.warning) == (state, warning)


# --- Do YAML ao run.stats e ao resumo -----------------------------------------------

REGISTRY_YAML = """\
- id: fonte
  name: Fonte sintética
  entity_type: press
  tier: T3
  registry_status: VALIDATED
  validated_at: '2026-10-12T00:00:00Z'
  validated_by: nuno
  endpoints:
  - id: a_normal
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/normal.xml'
    expect_min_items: 2
  - id: b_magro
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/magro.xml'
    expect_min_items: 5
  - id: c_vazio
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/vazio.xml'
  - id: d_em_erro
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/erro.xml'
"""


def setup(tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text(REGISTRY_YAML, encoding="utf-8")
    loaded = load_sources(config)
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    sync_sources(db, loaded.sources, loaded.endpoints, now=lambda: T0)
    minimums = {e.id: e.expect_min_items for e in loaded.endpoints if e.expect_min_items}
    return db, minimums


def collect_once(db, minimums, at):
    srv = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/normal.xml"): feed(FEED_FIXTURE),
            (HOST, "/magro.xml"): feed(FEED_FIXTURE),
            (HOST, "/vazio.xml"): feed(EMPTY_FEED),
            (HOST, "/erro.xml"): NOT_FOUND,
        }
    )
    registry = CollectorRegistry([RssCollector(srv.transport())])
    return run_collect(db, registry, now=lambda: at, expect_min_items=minimums)


def test_states_over_two_runs_reach_run_stats(tmp_path):
    db, minimums = setup(tmp_path)
    assert minimums == {"a_normal": 2, "b_magro": 5}

    first = collect_once(db, minimums, T0)
    assert {o.id: (o.state, o.warning) for o in first.endpoints} == {
        "a_normal": ("ok", None),
        "b_magro": ("ok", None),  # abaixo do mínimo, mas só num run
        "c_vazio": ("vazio", None),
        "d_em_erro": ("falha", None),
    }

    second = collect_once(db, minimums, T0 + timedelta(hours=5))
    assert {o.id: (o.state, o.warning) for o in second.endpoints} == {
        "a_normal": ("ok", None),
        "b_magro": ("suspeito", "abaixo do mínimo esperado (3 < 5) em 2 runs seguidos"),
        "c_vazio": ("vazio", None),
        "d_em_erro": ("falha", "falha em 2 runs seguidos"),
    }
    assert second.state_counts() == {"ok": 1, "vazio": 1, "suspeito": 1, "falha": 1}

    with sqlite3.connect(db) as conn:
        stats = json.loads(conn.execute("SELECT stats FROM run ORDER BY id DESC").fetchone()[0])
    assert stats["totals"]["states"] == {"ok": 1, "vazio": 1, "suspeito": 1, "falha": 1}
    assert [(e["id"], e["state"]) for e in stats["endpoints"]] == [
        ("a_normal", "ok"),
        ("b_magro", "suspeito"),
        ("c_vazio", "vazio"),
        ("d_em_erro", "falha"),
    ]


def test_summary_and_annotation_line(tmp_path):
    from tensdireito_content_engine.cli import _sources_line, daily_summary_markdown
    from tensdireito_content_engine.daily import DailyResult

    db, minimums = setup(tmp_path)
    collect_once(db, minimums, T0)
    collection = collect_once(db, minimums, T0 + timedelta(hours=5))
    assert _sources_line(collection) == (
        "FONTES: ok 1, vazias 1, suspeitas 1, com falha 1; avisos de 2 runs seguidos 2"
    )
    summary = daily_summary_markdown(
        DailyResult(
            day=T0.date(),
            collection=collection,
            normalized=0,
            duplicates=0,
            articles=(),
            report_path=tmp_path / "r.txt",
            drafts_created=0,
        )
    )
    assert "| Fontes consultadas | 4 (ok 1, vazias 1, suspeitas 1, com falha 1) |" in summary
    assert "### Fontes vazias, suspeitas ou com falha repetida" in summary
    assert "| `c_vazio` | vazio | respondeu sem itens |" in summary
    assert (
        "| `b_magro` | suspeito | abaixo do mínimo esperado (3 < 5) em 2 runs seguidos |" in summary
    )
    assert "| `d_em_erro` | falha | falha em 2 runs seguidos |" in summary
    assert "| `a_normal` | 0 | 3 | ok |" in summary  # segundo run: os 3 já existiam
    assert "| `c_vazio` | 0 | 0 | vazio |" in summary


def test_daily_passes_the_yaml_minimums(monkeypatch, tmp_path):
    from tensdireito_content_engine import daily as daily_module

    seen = {}

    def fake_collect(db_path, registry, now, expect_min_items):
        seen.update(expect_min_items)
        raise RuntimeError("parar aqui")

    config = tmp_path / "config"
    config.mkdir()
    (config / "sources.yaml").write_text(REGISTRY_YAML, encoding="utf-8")
    monkeypatch.setattr(daily_module, "run_collect", fake_collect)
    with pytest.raises(RuntimeError, match="parar aqui"):
        daily_module.run_daily(
            tmp_path / "tde.sqlite3",
            config / "sources.yaml",
            tmp_path / "reports",
            CollectorRegistry(),
            now=lambda: T0,
        )
    assert seen == {"a_normal": 2, "b_magro": 5}


# --- Run anterior --------------------------------------------------------------------


def test_previous_run_stats_is_the_last_finished_collect_run(tmp_path):
    db, minimums = setup(tmp_path)
    collect_once(db, minimums, T0)
    conn = sqlite3.connect(db)
    try:
        unfinished = start_run(conn, "collect", T0 + timedelta(hours=1))
        other = start_run(conn, "normalize", T0 + timedelta(hours=1))
        current = start_run(conn, "collect", T0 + timedelta(hours=2))
        stats = previous_run_stats(conn, "collect", current)
        assert stats is not None and len(stats["endpoints"]) == 4
        assert previous_run_stats(conn, "collect", 1) is None
        assert unfinished < other < current
        conn.execute("UPDATE run SET stats = 'não é json' WHERE id = 1")
        assert previous_run_stats(conn, "collect", current) is None
    finally:
        conn.close()


# --- Configuração --------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, True, 2.5])
def test_expect_min_items_must_be_a_positive_integer(value):
    with pytest.raises(DomainValidationError, match="expect_min_items"):
        SourceEndpoint(
            id="ep",
            source_id="fonte",
            endpoint_type=EndpointType.RSS,
            endpoint_status=EndpointStatus.CANDIDATE,
            expect_min_items=value,
        )


@pytest.mark.parametrize("value", ["10", 2.5, True, [1]])
def test_yaml_rejects_a_non_integer_minimum(tmp_path, value):
    data = yaml.safe_load(REGISTRY_YAML)
    data[0]["endpoints"][2]["expect_min_items"] = value
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SourceRegistryError, match="expect_min_items"):
        load_sources(config)
