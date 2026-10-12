"""Testes do M2.8: `tde collect`, ciclo de vida de `run`, `raw_item` e contrato `Collector`.

ROADMAP.md M2.8; DEC-031. Offline: bases de dados em directórios temporários e collectors
falsos, sem rede, sem IA e sem fontes nem URLs reais (TLD reservado `.invalid`). Nenhum
teste escreve em `data/` do repositório.
"""

import json
import re
import sqlite3
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import tensdireito_content_engine
from tensdireito_content_engine import cli
from tensdireito_content_engine.collect import CollectError, run_collect
from tensdireito_content_engine.collectors import Collector, CollectorRegistry, default_registry
from tensdireito_content_engine.collectors.rss import RssCollector
from tensdireito_content_engine.domain import (
    EndpointStatus,
    EndpointType,
    EntityType,
    RawItem,
    RegistryStatus,
    SourceEndpoint,
    SourceRegistry,
    SourceTier,
)
from tensdireito_content_engine.storage import StorageError, init_database, sync_sources

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
VALIDATED = {"validated_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC), "validated_by": "editor"}
PACKAGE_DIR = Path(tensdireito_content_engine.__file__).parent

SOURCES = [
    SourceRegistry(
        id="fonte_a",
        name="Fonte A fictícia",
        entity_type=EntityType.PUBLIC_BODY,
        tier=SourceTier.T1,
        domains=("a.invalid",),
        registry_status=RegistryStatus.VALIDATED,
        **VALIDATED,
    ),
    SourceRegistry(
        id="fonte_b",
        name="Fonte B fictícia",
        entity_type=EntityType.SPECIALISED,
        tier=SourceTier.T2,
        domains=("b.invalid",),
        registry_status=RegistryStatus.VALIDATED,
        **VALIDATED,
    ),
    SourceRegistry(
        id="fonte_c",
        name="Fonte C fictícia",
        entity_type=EntityType.PRESS,
        tier=SourceTier.T3,
    ),
]


def _endpoint(endpoint_id, source_id, endpoint_type, status, url=None) -> SourceEndpoint:
    validated = VALIDATED if status in (EndpointStatus.VALIDATED, EndpointStatus.ACTIVE) else {}
    return SourceEndpoint(
        id=endpoint_id,
        source_id=source_id,
        endpoint_type=endpoint_type,
        url=url,
        endpoint_status=status,
        **validated,
    )


ENDPOINTS = [
    # Ordem propositadamente diferente da ordem por `id`.
    _endpoint("b_feed", "fonte_b", EndpointType.RSS, EndpointStatus.ACTIVE, "https://b.invalid/f"),
    _endpoint("a_pagina", "fonte_a", EndpointType.HTML_PAGE, EndpointStatus.ACTIVE, "https://a.invalid/p"),
    _endpoint("a_feed", "fonte_a", EndpointType.RSS, EndpointStatus.ACTIVE, "https://a.invalid/f"),
    _endpoint("a_candidato", "fonte_a", EndpointType.RSS, EndpointStatus.CANDIDATE),
    _endpoint("a_validado", "fonte_a", EndpointType.RSS, EndpointStatus.VALIDATED, "https://a.invalid/v"),
    _endpoint("a_inactivo", "fonte_a", EndpointType.RSS, EndpointStatus.INACTIVE, "https://a.invalid/i"),
    _endpoint("c_manual", "fonte_c", EndpointType.MANUAL, EndpointStatus.CANDIDATE),
]  # fmt: skip
ACTIVE_IDS = ["a_feed", "a_pagina", "b_feed"]


def item(endpoint_id: str, n: int, content: str | None = None) -> RawItem:
    return RawItem(
        url=f"https://exemplo.invalid/{endpoint_id}/{n}",
        title=f"Título {n}",
        raw_content=content if content is not None else f"<p>conteúdo {endpoint_id} {n}</p>",
        fetched_at=T0,
        source_endpoint_id=endpoint_id,
        external_id=f"guid-{n}",
        published_at_raw="7 de outubro de 2026",
    )


class FakeCollector:
    """Collector falso: devolve o que `produce` gerar para cada endpoint e regista chamadas."""

    def __init__(
        self,
        endpoint_type: EndpointType,
        produce: Callable[[SourceEndpoint], Iterable[RawItem]] | None = None,
    ) -> None:
        self.endpoint_type = endpoint_type
        self.produce = produce or (lambda endpoint: [item(endpoint.id, 1), item(endpoint.id, 2)])
        self.calls: list[tuple[str, datetime | None]] = []

    def fetch(self, endpoint: SourceEndpoint, since: datetime | None) -> Iterable[RawItem]:
        self.calls.append((endpoint.id, since))
        return self.produce(endpoint)


class Clock:
    """Relógio determinista: cada chamada avança um segundo."""

    def __init__(self, start: datetime = T0) -> None:
        self.current = start

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def registry_of(*collectors: Collector) -> CollectorRegistry:
    return CollectorRegistry(collectors)


def both(rss=None, html=None) -> tuple[FakeCollector, FakeCollector, CollectorRegistry]:
    rss_collector = FakeCollector(EndpointType.RSS, rss)
    html_collector = FakeCollector(EndpointType.HTML_PAGE, html)
    return rss_collector, html_collector, registry_of(rss_collector, html_collector)


def failing_midway(endpoint: SourceEndpoint) -> Iterable[RawItem]:
    yield item(endpoint.id, 1)
    raise RuntimeError("ligação perdida")


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "db" / "tde.sqlite3"
    init_database(path)
    sync_sources(path, SOURCES, ENDPOINTS, now=lambda: T0)
    return path


def query(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def execute(db: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def runs(db: Path) -> list[dict]:
    columns = ("id", "command", "started_at", "finished_at", "status", "stats", "outcome")
    rows = query(db, f"SELECT {', '.join(columns)}, report_path FROM run ORDER BY id")
    return [dict(zip((*columns, "report_path"), row, strict=True)) for row in rows]


def raw_items(db: Path) -> list[tuple]:
    return query(db, "SELECT * FROM raw_item ORDER BY id")


def endpoint_state(db: Path, endpoint_id: str) -> tuple:
    return query(
        db,
        "SELECT last_success_at, last_error, updated_at FROM source_endpoint WHERE id = ?",
        (endpoint_id,),
    )[0]


def mirror(db: Path) -> list[tuple]:
    """`source_registry` e campos não operacionais de `source_endpoint`."""
    return query(db, "SELECT * FROM source_registry ORDER BY id") + query(
        db,
        "SELECT id, source_id, endpoint_type, url, fetch, endpoint_status, validated_at, "
        "validated_by, created_at, updated_at FROM source_endpoint ORDER BY id",
    )


def run_cli(monkeypatch, db: Path, *args: str, registry: CollectorRegistry | None = None) -> int:
    monkeypatch.setattr(cli, "default_registry", lambda: registry or CollectorRegistry())
    return cli.main(["--db", str(db), "collect", *args])


# --- Contrato Collector e registo ------------------------------------------------


def test_production_registry_has_only_the_rss_collector():
    # M2.9 (DEC-032): `rss` é o primeiro e único collector concreto de produção.
    registry = default_registry()
    assert isinstance(registry.get(EndpointType.RSS), RssCollector)
    assert registry.get(EndpointType.HTML_PAGE) is None
    assert registry.get(EndpointType.MANUAL) is None


def test_registry_rejects_two_collectors_for_the_same_type():
    with pytest.raises(ValueError, match="repetido"):
        registry_of(FakeCollector(EndpointType.RSS), FakeCollector(EndpointType.RSS))


def test_collectors_package_has_only_rss_news_sitemap_and_their_transport():
    names = sorted(path.name for path in (PACKAGE_DIR / "collectors").glob("*.py"))
    assert names == ["__init__.py", "base.py", "http.py", "news_sitemap.py", "rss.py"]


def test_default_registry_has_rss_and_news_sitemap():
    from tensdireito_content_engine.domain import EndpointType

    registry = default_registry()
    assert registry.get(EndpointType.RSS) is not None
    assert registry.get(EndpointType.NEWS_SITEMAP) is not None
    assert registry.get(EndpointType.HTML_PAGE) is None


# --- Zero endpoints e sucesso ---------------------------------------------------


# DEC-070: contagens do transporte em `run.stats`.
NO_TRANSPORT_EVENTS = {
    "limitação": 0,
    "nova tentativa": 0,
    "redirect seguido": 0,
    "redirect recusado": 0,
}


def test_zero_active_endpoints_is_success(tmp_path):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    result = run_collect(db, CollectorRegistry(), now=Clock())
    assert result.status == "success"
    assert result.endpoints == ()
    [run] = runs(db)
    assert run["command"] == "collect"
    assert run["status"] == "success"
    assert run["finished_at"] is not None
    assert run["outcome"] is None and run["report_path"] is None
    assert json.loads(run["stats"])["totals"] == {
        "selected": 0,
        "succeeded": 0,
        "failed": 0,
        "new": 0,
        "existing": 0,
        "transport": NO_TRANSPORT_EVENTS,
        "states": {"ok": 0, "vazio": 0, "suspeito": 0, "falha": 0},
    }
    assert raw_items(db) == []


def test_success_with_fake_collectors(db):
    rss, html, registry = both()
    result = run_collect(db, registry, now=Clock())
    assert result.status == "success"
    assert [outcome.id for outcome in result.endpoints] == ACTIVE_IDS
    assert (result.new, result.existing, result.failed) == (6, 0, 0)
    assert rss.calls == [("a_feed", None), ("b_feed", None)]  # `since` é sempre None
    assert html.calls == [("a_pagina", None)]
    [run] = runs(db)
    assert (run["status"], run["finished_at"] is not None) == ("success", True)


def test_raw_items_are_stored_with_created_in_run(db):
    _, _, registry = both()
    result = run_collect(db, registry, now=Clock())
    rows = query(
        db,
        "SELECT source_endpoint_id, url, external_id, title, raw_content, fetched_at, "
        "published_at_raw, content_hash, manual_note, created_in_run, created_at, updated_at "
        "FROM raw_item WHERE source_endpoint_id = 'a_feed' ORDER BY id",
    )
    expected = item("a_feed", 1)
    first = rows[0]
    assert first[:10] == (
        "a_feed",
        expected.url,
        "guid-1",
        "Título 1",
        expected.raw_content,
        "2026-10-07T12:00:00.000000+00:00",
        "7 de outubro de 2026",
        expected.content_hash,
        None,
        result.run_id,
    )
    assert first[10] == first[11]
    assert query(db, "SELECT DISTINCT created_in_run FROM raw_item") == [(result.run_id,)]


def test_success_sets_last_success_at_and_clears_last_error(db):
    execute(db, "UPDATE source_endpoint SET last_error = 'erro antigo' WHERE id = 'a_feed'")
    _, _, registry = both()
    run_collect(db, registry, now=Clock())
    last_success_at, last_error, _ = endpoint_state(db, "a_feed")
    assert last_success_at is not None and last_success_at.endswith("+00:00")
    assert last_error is None


def test_collect_does_not_touch_projected_fields_or_updated_at(db):
    before = mirror(db)
    _, _, registry = both()
    run_collect(db, registry, now=Clock())
    run_collect(db, registry_of(FakeCollector(EndpointType.RSS, failing_midway)), now=Clock())
    assert mirror(db) == before


# --- Idempotência ---------------------------------------------------------------


def test_repeated_collect_is_idempotent(db):
    _, _, registry = both()
    first = run_collect(db, registry, now=Clock())
    stored = raw_items(db)
    second = run_collect(db, registry, now=Clock(T0 + timedelta(hours=1)))
    assert second.run_id != first.run_id
    assert (second.new, second.existing) == (0, 6)
    assert raw_items(db) == stored  # incluindo created_in_run do primeiro run
    assert [run["status"] for run in runs(db)] == ["success", "success"]
    assert endpoint_state(db, "a_feed")[0].startswith("2026-10-07T13:")


def test_duplicate_within_same_fetch_counts_as_existing(db):
    def repeated(endpoint):
        return [item(endpoint.id, 1), item(endpoint.id, 1), item(endpoint.id, 2)]

    result = run_collect(db, registry_of(FakeCollector(EndpointType.RSS, repeated)), "fonte_b")
    [outcome] = result.endpoints
    assert (outcome.new, outcome.existing) == (2, 1)
    assert len(raw_items(db)) == 2


def test_same_url_with_new_content_is_a_new_item(db):
    collector = FakeCollector(EndpointType.RSS, lambda e: [item(e.id, 1, "v1")])
    run_collect(db, registry_of(collector), "fonte_b", now=Clock())
    collector.produce = lambda e: [item(e.id, 1, "v2")]
    result = run_collect(db, registry_of(collector), "fonte_b", now=Clock())
    assert (result.new, result.existing) == (1, 0)
    assert len(raw_items(db)) == 2


# --- Falhas ---------------------------------------------------------------------


def test_isolated_failure_is_partial_and_rolled_back(db):
    _, _, registry = both()
    run_collect(db, registry, now=Clock())
    before_items = query(db, "SELECT * FROM raw_item WHERE source_endpoint_id = 'a_feed'")
    before_success = endpoint_state(db, "a_feed")[0]

    def a_feed_fails(endpoint):
        if endpoint.id == "a_feed":
            return failing_midway(endpoint)
        return [item(endpoint.id, 3)]

    _, _, registry = both(rss=a_feed_fails)
    result = run_collect(db, registry, now=Clock(T0 + timedelta(hours=1)))
    assert result.status == "partial"
    by_id = {outcome.id: outcome for outcome in result.endpoints}
    assert by_id["a_feed"].result == "failed"
    assert (by_id["a_feed"].new, by_id["a_feed"].existing) == (0, 0)
    assert by_id["a_feed"].error == "o collector falhou: RuntimeError: ligação perdida"
    assert (by_id["b_feed"].result, by_id["b_feed"].new) == ("success", 1)
    # Nenhum item do endpoint que falhou foi gravado; os anteriores estão intactos.
    assert query(db, "SELECT * FROM raw_item WHERE source_endpoint_id = 'a_feed'") == before_items
    last_success_at, last_error, _ = endpoint_state(db, "a_feed")
    assert last_success_at == before_success
    assert last_error == "o collector falhou: RuntimeError: ligação perdida"
    assert runs(db)[-1]["status"] == "partial"


def test_collector_raising_on_call_is_endpoint_failure(db):
    def boom(endpoint):
        raise ValueError("resposta inválida")

    result = run_collect(db, registry_of(FakeCollector(EndpointType.RSS, boom)), "fonte_b")
    assert result.status == "failed"
    assert endpoint_state(db, "b_feed")[1] == "o collector falhou: ValueError: resposta inválida"


def test_all_endpoints_failing_is_failed(db):
    def boom(endpoint):
        raise RuntimeError("falhou")

    _, _, registry = both(rss=boom, html=boom)
    result = run_collect(db, registry, now=Clock())
    assert result.status == "failed"
    [run] = runs(db)
    assert run["status"] == "failed"
    assert run["finished_at"] is not None
    assert json.loads(run["stats"])["totals"]["failed"] == 3
    assert raw_items(db) == []


def test_endpoint_without_collector_is_endpoint_failure(db):
    rss = FakeCollector(EndpointType.RSS)
    result = run_collect(db, registry_of(rss), now=Clock())
    assert result.status == "partial"
    by_id = {outcome.id: outcome for outcome in result.endpoints}
    assert by_id["a_pagina"].error == "sem collector para endpoint_type html_page"
    assert endpoint_state(db, "a_pagina")[1] == "sem collector para endpoint_type html_page"
    assert endpoint_state(db, "a_pagina")[0] is None
    assert (by_id["a_feed"].new, by_id["b_feed"].new) == (2, 2)


def test_production_registry_fails_endpoints_without_collector(db):
    # Os endpoints `rss` do registo fictício (`.invalid`) chegam ao transporte real, que
    # esbarra na salvaguarda de rede dos testes (conftest.py); `html_page` não tem collector.
    result = run_collect(db, default_registry(), now=Clock())
    assert result.status == "failed"
    errors = {outcome.id: outcome.error for outcome in result.endpoints}
    assert errors["a_pagina"] == "sem collector para endpoint_type html_page"
    assert "NetworkAccessError" in errors["a_feed"]
    assert "NetworkAccessError" in errors["b_feed"]


@pytest.mark.parametrize(
    ("produce", "error"),
    [
        (
            lambda e: [item(e.id, 1), item("a_pagina", 2)],
            "item 2: source_endpoint_id a_pagina diferente do endpoint b_feed",
        ),
        (
            lambda e: [RawItem(**{**_rebenta("b_feed"), "source_endpoint_id": None})],
            "item 1: source_endpoint_id None diferente do endpoint b_feed",
        ),
        (lambda e: [item(e.id, 1), {"url": "https://x.invalid"}], "item 2: não é um RawItem"),
    ],
)  # fmt: skip
def test_wrong_provenance_fails_endpoint_without_writing(db, produce, error):
    result = run_collect(db, registry_of(FakeCollector(EndpointType.RSS, produce)), "fonte_b")
    assert result.status == "failed"
    assert result.endpoints[0].error == error
    assert raw_items(db) == []
    assert endpoint_state(db, "b_feed")[1] == error


def test_wrong_provenance_does_not_stop_other_endpoints(db):
    def a_feed_lies(endpoint):
        owner = "b_feed" if endpoint.id == "a_feed" else endpoint.id
        return [item(owner, 1)]

    _, _, registry = both(rss=a_feed_lies)
    result = run_collect(db, registry, now=Clock())
    assert result.status == "partial"
    assert [o.result for o in result.endpoints] == ["failed", "success", "success"]
    assert query(db, "SELECT DISTINCT source_endpoint_id FROM raw_item ORDER BY 1") == [
        ("a_pagina",),
        ("b_feed",),
    ]


# --- Selecção -------------------------------------------------------------------


def test_only_active_endpoints_are_collected_in_id_order(db):
    seen: list[str] = []

    def record(endpoint):
        assert endpoint.endpoint_status is EndpointStatus.ACTIVE
        seen.append(endpoint.id)
        return []

    _, _, registry = both(rss=record, html=record)
    run_collect(db, registry, now=Clock())
    assert seen == ACTIVE_IDS
    for endpoint_id in ("a_candidato", "a_validado", "a_inactivo", "c_manual"):
        assert endpoint_state(db, endpoint_id)[:2] == (None, None)


def test_source_option_restricts_to_that_source(db):
    rss, html, registry = both()
    result = run_collect(db, registry, "fonte_a", now=Clock())
    assert [outcome.id for outcome in result.endpoints] == ["a_feed", "a_pagina"]
    assert rss.calls == [("a_feed", None)] and html.calls == [("a_pagina", None)]
    assert endpoint_state(db, "b_feed")[0] is None


def test_source_without_active_endpoints_is_success(db):
    result = run_collect(db, both()[2], "fonte_c", now=Clock())
    assert (result.status, result.endpoints) == ("success", ())
    assert runs(db)[0]["status"] == "success"


def test_unknown_source_fails_without_run(db):
    with pytest.raises(CollectError, match="fonte_x não existe"):
        run_collect(db, both()[2], "fonte_x")
    assert runs(db) == []


# --- Pré-condições --------------------------------------------------------------


def test_missing_database_fails_without_creating_anything(tmp_path, monkeypatch, capsys):
    db = tmp_path / "nada" / "tde.sqlite3"
    assert run_cli(monkeypatch, db) == 1
    err = capsys.readouterr().err
    assert f"collect: ERRO — {db}" in err
    assert "execute `tde init`" in err
    assert not db.parent.exists()


def test_pending_migrations_fail_without_migrating(tmp_path, monkeypatch, capsys):
    db = tmp_path / "tde.sqlite3"
    sqlite3.connect(db).close()
    assert run_cli(monkeypatch, db) == 1
    err = capsys.readouterr().err
    assert (
        "esquema não conforme: migrações pendentes: 0001_init, 0002_source_document, "
        "0003_whatsapp_draft, 0004_candidate, 0005_endpoint_redirects; "
        "execute `tde init`"
    ) in err
    assert query(db, "SELECT name FROM sqlite_master") == []


def test_non_sqlite_file_fails_asking_for_init(tmp_path, monkeypatch, capsys):
    db = tmp_path / "tde.sqlite3"
    db.write_text("isto não é SQLite", encoding="utf-8")
    assert run_cli(monkeypatch, db) == 1
    err = capsys.readouterr().err
    assert "esquema não conforme" in err and "execute `tde init`" in err
    assert db.read_text(encoding="utf-8") == "isto não é SQLite"


def test_changed_migration_checksum_fails_without_run(db, monkeypatch, capsys):
    execute(db, "UPDATE schema_migration SET checksum = 'x'")
    assert run_cli(monkeypatch, db, registry=both()[2]) == 1
    assert "checksum diferente" in capsys.readouterr().err
    assert runs(db) == []


def test_unknown_source_via_cli_exits_one(db, monkeypatch, capsys):
    assert run_cli(monkeypatch, db, "--source", "fonte_x", registry=both()[2]) == 1
    captured = capsys.readouterr()
    assert captured.err.splitlines() == [
        f"collect: ERRO — {db}",
        "- a fonte fonte_x não existe em source_registry",
    ]
    assert captured.out == ""
    assert runs(db) == []


# --- Erro da storage ------------------------------------------------------------


def test_storage_error_leaves_run_unfinished(db, monkeypatch, capsys):
    execute(
        db,
        "CREATE TRIGGER falha_injectada BEFORE INSERT ON raw_item "
        "WHEN NEW.url LIKE '%/rebenta' BEGIN SELECT RAISE(ABORT, 'falha injectada'); END",
    )

    def explode_on_b(endpoint):
        if endpoint.id == "b_feed":
            return [item("b_feed", 1), RawItem(**_rebenta("b_feed"))]
        return [item(endpoint.id, 1)]

    _, _, registry = both(rss=explode_on_b, html=explode_on_b)
    with pytest.raises(StorageError, match="falha injectada") as exc:
        run_collect(db, registry, now=Clock())
    assert isinstance(exc.value.__cause__, sqlite3.Error)  # excepção original encadeada
    [run] = runs(db)
    assert (run["finished_at"], run["status"], run["stats"]) == (None, None, None)
    # Os endpoints anteriores foram gravados; nada da transacção interrompida ficou.
    stored = query(db, "SELECT source_endpoint_id FROM raw_item ORDER BY id")
    assert stored == [("a_feed",), ("a_pagina",)]
    assert endpoint_state(db, "b_feed")[:2] == (None, None)

    assert run_cli(monkeypatch, db, registry=registry) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith(f"collect: ERRO — {db}\n- ")
    assert "falha injectada" in captured.err
    assert [r["finished_at"] for r in runs(db)] == [None, None]


def _rebenta(endpoint_id: str) -> dict:
    return {
        "url": "https://exemplo.invalid/rebenta",
        "title": "t",
        "raw_content": "c",
        "fetched_at": T0,
        "source_endpoint_id": endpoint_id,
    }


# --- stats ----------------------------------------------------------------------


def test_stats_structure_is_deterministic(db):
    def a_feed_fails(endpoint):
        if endpoint.id == "a_feed":
            raise RuntimeError("falhou")
        return [item(endpoint.id, 1), item(endpoint.id, 1)]

    _, _, registry = both(rss=a_feed_fails, html=a_feed_fails)
    run_collect(db, registry, now=Clock())
    [run] = runs(db)
    assert run["stats"] == json.dumps(
        {
            "endpoints": [
                {
                    "id": "a_feed",
                    "result": "failed",
                    "new": 0,
                    "existing": 0,
                    "error": "o collector falhou: RuntimeError: falhou",
                    "notes": [],
                    "state": "falha",
                    "warning": None,
                },
                {
                    "id": "a_pagina",
                    "result": "success",
                    "new": 1,
                    "existing": 1,
                    "error": None,
                    "notes": [],
                    "state": "ok",
                    "warning": None,
                },
                {
                    "id": "b_feed",
                    "result": "success",
                    "new": 1,
                    "existing": 1,
                    "error": None,
                    "notes": [],
                    "state": "ok",
                    "warning": None,
                },
            ],
            "totals": {
                "selected": 3,
                "succeeded": 2,
                "failed": 1,
                "new": 2,
                "existing": 2,
                "transport": NO_TRANSPORT_EVENTS,
                "states": {"ok": 2, "vazio": 0, "suspeito": 0, "falha": 1},
            },
        },
        ensure_ascii=False,
    )


def test_run_timestamps_are_utc_and_ordered(db):
    run_collect(db, both()[2], now=Clock())
    [run] = runs(db)
    assert run["started_at"] == "2026-10-07T12:00:01.000000+00:00"
    assert run["started_at"] < run["finished_at"]


# --- CLI ------------------------------------------------------------------------


def test_cli_success_output_and_exit_zero(db, monkeypatch, capsys):
    assert run_cli(monkeypatch, db, registry=both()[2]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"collect: OK — {db}",
        "run: 1",
        "endpoints: 3",
        "com sucesso: 3",
        "com falha: 0",
        "itens novos: 6",
        "itens existentes: 0",
    ]
    assert captured.err == ""


def test_cli_partial_output_and_exit_two(db, monkeypatch, capsys):
    rss = FakeCollector(EndpointType.RSS)
    assert run_cli(monkeypatch, db, registry=registry_of(rss)) == 2
    captured = capsys.readouterr()
    assert captured.out.splitlines()[0] == f"collect: PARCIAL — {db}"
    assert "com falha: 1" in captured.out
    assert captured.err.splitlines() == ["- a_pagina: sem collector para endpoint_type html_page"]


def test_cli_all_failed_output_and_exit_one(db, monkeypatch, capsys):
    assert run_cli(monkeypatch, db) == 1  # registo vazio: todos os endpoints falham
    captured = capsys.readouterr()
    assert captured.out.splitlines()[0] == f"collect: ERRO — {db}"
    assert "com falha: 3" in captured.out
    assert len(captured.err.splitlines()) == 3
    assert runs(db)[0]["status"] == "failed"


def test_cli_zero_active_endpoints_exit_zero(tmp_path, monkeypatch, capsys):
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    assert run_cli(monkeypatch, db) == 0
    assert capsys.readouterr().out.splitlines()[:3] == [
        f"collect: OK — {db}",
        "run: 1",
        "endpoints: 0",
    ]


def test_cli_uses_tde_db_path(db, monkeypatch, capsys):
    monkeypatch.setenv("TDE_DB_PATH", str(db))
    monkeypatch.setattr(cli, "default_registry", lambda: both()[2])
    assert cli.main(["collect"]) == 0
    assert capsys.readouterr().out.startswith(f"collect: OK — {db}")


def test_cli_help_lists_collect_with_source_and_without_since(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "collect" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["collect", "--help"])
    out = capsys.readouterr().out
    assert "--source" in out and "--since" not in out and "--dry-run" not in out
    with pytest.raises(SystemExit) as exc:
        cli.main(["collect", "--since", "2026-10-01"])
    assert exc.value.code == 2


def test_collect_does_not_read_or_change_sources_yaml(db, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    yaml_file = config / "sources.yaml"
    yaml_file.write_text("isto: [não é um registo válido\n", encoding="utf-8")
    before = yaml_file.read_bytes()
    monkeypatch.setattr(cli, "default_registry", lambda: both()[2])
    assert cli.main(["--config", str(config), "--db", str(db), "collect"]) == 0
    assert yaml_file.read_bytes() == before


# --- Camadas e SQL --------------------------------------------------------------

ORCHESTRATION_FILES = [PACKAGE_DIR / "collect.py", PACKAGE_DIR / "cli.py"] + sorted(
    (PACKAGE_DIR / "collectors").glob("*.py")
)


@pytest.mark.parametrize("path", ORCHESTRATION_FILES, ids=lambda path: path.name)
def test_no_sql_in_orchestration_or_collectors(path):
    sql = re.compile(
        r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|SELECT\s+.+\s+FROM|BEGIN|COMMIT|"
        r"ROLLBACK)\b"
    )
    assert not sql.search(path.read_text(encoding="utf-8")), path


def test_no_upsert_constructs_anywhere_in_package():
    forbidden = re.compile(r"\b(INSERT\s+OR\s+IGNORE|INSERT\s+OR\s+REPLACE|ON\s+CONFLICT)\b", re.I)
    for path in sorted(PACKAGE_DIR.rglob("*")):
        if path.suffix in {".py", ".sql"}:
            code = path.read_text(encoding="utf-8")
            if path.suffix == ".py":
                code = re.sub(r'""".*?"""', "", code, flags=re.DOTALL)  # docstrings citam-nos
            assert not forbidden.search(code), path


def test_schema_unchanged_by_collect(db):
    before = query(db, "SELECT type, name, sql FROM sqlite_master ORDER BY name")
    run_collect(db, both()[2], now=Clock())
    assert query(db, "SELECT type, name, sql FROM sqlite_master ORDER BY name") == before
