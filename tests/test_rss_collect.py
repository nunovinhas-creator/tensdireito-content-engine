"""Testes do M2.9: collector `rss` integrado no `tde collect` do M2.8 (ROADMAP.md M2.9).

DEC-031, DEC-032, DEC-033. Offline: o collector usa o transporte real (`HttpsTransport`)
com resolução, ligação, relógio e espera falsos (`_fake_http.py`); bases de dados em
directórios temporários; fixtures sintéticas com domínios reservados (RFC 2606). Nenhum
teste escreve em `data/` nem depende de endpoints reais em `config/sources.yaml`.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from _fake_http import FEED_URL, HOST, NO_ROBOTS, FakeServer, Reply, feed, robots

import tensdireito_content_engine
from tensdireito_content_engine import cli
from tensdireito_content_engine.collect import run_collect
from tensdireito_content_engine.collectors import CollectorRegistry, default_registry
from tensdireito_content_engine.collectors.http import TransportError
from tensdireito_content_engine.collectors.rss import FeedError, RssCollector
from tensdireito_content_engine.domain import (
    EndpointStatus,
    EndpointType,
    EntityType,
    RegistryStatus,
    SourceEndpoint,
    SourceRegistry,
    SourceTier,
)
from tensdireito_content_engine.storage import init_database, sync_sources

FIXTURES = Path(__file__).parent / "fixtures" / "rss"
REPO_ROOT = Path(tensdireito_content_engine.__file__).parents[2]
T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
FETCHED = datetime(2026, 10, 7, 12, 30, 0, tzinfo=UTC)
VALIDATED = {"validated_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC), "validated_by": "editor"}

SOURCES = [
    SourceRegistry(
        id="fonte_sintetica",
        name="Fonte sintética",
        entity_type=EntityType.PUBLIC_BODY,
        tier=SourceTier.T1,
        domains=(HOST,),
        registry_status=RegistryStatus.VALIDATED,
        **VALIDATED,
    )
]
ENDPOINTS = [
    SourceEndpoint(
        id="feed_sintetico",
        source_id="fonte_sintetica",
        endpoint_type=EndpointType.RSS,
        url=FEED_URL,
        endpoint_status=EndpointStatus.ACTIVE,
        **VALIDATED,
    ),
    SourceEndpoint(
        id="pagina_sintetica",
        source_id="fonte_sintetica",
        endpoint_type=EndpointType.HTML_PAGE,
        url=f"https://{HOST}/pagina",
        endpoint_status=EndpointStatus.ACTIVE,
        **VALIDATED,
    ),
]
RSS_ONLY = ENDPOINTS[:1]


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "db" / "tde.sqlite3"
    init_database(path)
    sync_sources(path, SOURCES, RSS_ONLY, now=lambda: T0)
    return path


def registry_for(server: FakeServer) -> CollectorRegistry:
    return CollectorRegistry([RssCollector(server.transport(), now=lambda: FETCHED)])


def serving(body: bytes | Reply) -> FakeServer:
    reply = body if isinstance(body, Reply) else feed(body)
    return FakeServer({(HOST, "/robots.txt"): NO_ROBOTS, (HOST, "/rss.xml"): reply})


def collect_cli(monkeypatch, db: Path, server: FakeServer) -> int:
    # Como em produção: um registo (e um transporte) novo por execução de `tde collect`.
    monkeypatch.setattr(cli, "default_registry", lambda: registry_for(server))
    return cli.main(["--db", str(db), "collect"])


def query(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def raw_items(db: Path) -> list[dict]:
    columns = (
        "source_endpoint_id",
        "url",
        "title",
        "external_id",
        "published_at_raw",
        "fetched_at",
        "manual_note",
        "raw_content",
        "content_hash",
        "created_in_run",
    )
    rows = query(db, f"SELECT {', '.join(columns)} FROM raw_item ORDER BY id")
    return [dict(zip(columns, row, strict=True)) for row in rows]


def endpoint_state(db: Path) -> tuple:
    return query(
        db,
        "SELECT last_success_at, last_error, updated_at FROM source_endpoint WHERE id = ?",
        ("feed_sintetico",),
    )[0]


def run_stats(db: Path) -> list[dict]:
    return [json.loads(row[0]) for row in query(db, "SELECT stats FROM run ORDER BY id")]


INVALID_SECOND_ITEM = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>F</title>'
    b"<item><title>Bom</title><link>https://feed.example.org/1</link></item>"
    b"<item><title>Sem link</title></item>"
    b"</channel></rss>"
)


# --- Registo de produção --------------------------------------------------------


def test_production_registry_registers_rss_with_the_real_transport():
    registry = default_registry()
    collector = registry.get(EndpointType.RSS)
    assert isinstance(collector, RssCollector)
    assert collector.endpoint_type is EndpointType.RSS


def test_endpoint_types_without_collector_still_fail_as_in_m28(tmp_path):
    path = tmp_path / "tde.sqlite3"
    init_database(path)
    sync_sources(path, SOURCES, ENDPOINTS, now=lambda: T0)
    server = serving(fixture("valid.xml"))
    result = run_collect(path, registry_for(server), now=lambda: T0)
    outcomes = {outcome.id: outcome for outcome in result.endpoints}
    assert result.status == "partial"
    assert outcomes["feed_sintetico"].new == 3
    assert outcomes["pagina_sintetica"].error == "sem collector para endpoint_type html_page"
    assert server.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml"]


def test_production_collect_without_synced_sources_makes_no_request(tmp_path, monkeypatch):
    # `collect` lê o espelho SQLite; sem sincronizar o YAML, não há endpoints na base.
    path = tmp_path / "tde.sqlite3"
    init_database(path)
    assert cli.main(["--db", str(path), "collect"]) == 0


def test_repository_sources_yaml_has_active_official_rss_endpoint():
    text = (REPO_ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")
    sources = yaml.safe_load(text)
    assert len(sources) >= 1
    assert sources[0]["id"] == "dre"
    endpoint = sources[0]["endpoints"][0]
    assert endpoint["id"] == "dre-serie1-rss"
    assert endpoint["endpoint_type"] == "rss"
    assert endpoint["url"] == "https://files.diariodarepublica.pt/rss/serie1-html.xml"
    assert endpoint["endpoint_status"] == "ACTIVE"


# --- tde collect com endpoint rss ------------------------------------------------


def test_cli_collect_with_rss_endpoint(db, monkeypatch, capsys):
    server = serving(fixture("valid.xml"))
    assert collect_cli(monkeypatch, db, server) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"collect: OK — {db}",
        "run: 1",
        "endpoints: 1",
        "com sucesso: 1",
        "com falha: 0",
        "itens novos: 3",
        "itens existentes: 0",
    ]
    assert server.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml"]


def test_new_items_are_persisted_with_the_rss_mapping(db, monkeypatch):
    assert collect_cli(monkeypatch, db, serving(fixture("valid.xml"))) == 0
    rows = raw_items(db)
    assert [row["url"] for row in rows] == [
        "https://feed.example.org/noticias/1?utm_source=rss#topo",
        "https://feed.example.org/noticias/2",
        "http://feed.example.org/noticias/3",
    ]
    first, second, third = rows
    assert first["title"] == "Primeira notícia"
    assert first["external_id"] == "id-0001"
    assert first["published_at_raw"] == "Wed, 07 Oct 2026 10:00:00 +0100"
    assert first["raw_content"].startswith("<item>")
    assert second["external_id"] == "https://feed.example.org/noticias/2"
    assert (third["external_id"], third["published_at_raw"]) == (None, None)
    assert {row["source_endpoint_id"] for row in rows} == {"feed_sintetico"}
    assert {row["fetched_at"] for row in rows} == {"2026-10-07T12:30:00.000000+00:00"}
    assert {row["manual_note"] for row in rows} == {None}
    assert {row["created_in_run"] for row in rows} == {1}


def test_repeated_collect_counts_existing_items(db, monkeypatch, capsys):
    body = fixture("valid.xml")
    assert collect_cli(monkeypatch, db, serving(body)) == 0
    assert collect_cli(monkeypatch, db, serving(body)) == 0
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "itens novos: 0",
        "itens existentes: 3",
    ]
    assert len(raw_items(db)) == 3
    assert {row["created_in_run"] for row in raw_items(db)} == {1}
    assert len(run_stats(db)) == 2


def test_changed_item_content_creates_a_new_raw_item(db, monkeypatch):
    body = fixture("valid.xml")
    collect_cli(monkeypatch, db, serving(body))
    collect_cli(monkeypatch, db, serving(body.replace(b"Resumo da primeira", b"Resumo novo da")))
    rows = raw_items(db)
    assert len(rows) == 4
    assert rows[3]["url"] == rows[0]["url"]
    assert rows[3]["created_in_run"] == 2


def test_empty_feed_is_success_with_zero_items(db, monkeypatch):
    assert collect_cli(monkeypatch, db, serving(fixture("empty.xml"))) == 0
    assert raw_items(db) == []
    last_success_at, last_error, _ = endpoint_state(db)
    assert last_success_at is not None and last_error is None


# --- Falhas e estado operacional ------------------------------------------------


def test_invalid_item_fails_endpoint_without_partial_items(db, monkeypatch, capsys):
    assert collect_cli(monkeypatch, db, serving(fixture("valid.xml"))) == 0
    before_items = raw_items(db)
    before_state = endpoint_state(db)
    capsys.readouterr()

    assert collect_cli(monkeypatch, db, serving(INVALID_SECOND_ITEM)) == 1
    assert capsys.readouterr().err.splitlines() == [
        "- feed_sintetico: o collector falhou: FeedError: item 2: sem link"
    ]
    # Atomicidade (M2.8): nem o primeiro item, válido, é gravado.
    assert raw_items(db) == before_items
    last_success_at, last_error, updated_at = endpoint_state(db)
    assert last_success_at == before_state[0]
    assert last_error == "o collector falhou: FeedError: item 2: sem link"
    assert updated_at == before_state[2]


def test_first_failure_writes_nothing(db, monkeypatch):
    assert collect_cli(monkeypatch, db, serving(INVALID_SECOND_ITEM)) == 1
    assert raw_items(db) == []
    assert endpoint_state(db)[0] is None


@pytest.mark.parametrize(
    ("server_reply", "error"),
    [
        (Reply(404, {"Content-Type": "text/html"}), "TransportError: HTTP 404"),
        (Reply(301, {"Location": "https://x.test/"}), "TransportError: redirect não seguido: 301"),
        (feed(b"<html/>", "text/html"), "TransportError: Content-Type não aceite: text/html"),
        (feed(b"", **{"Content-Encoding": "gzip"}), "TransportError: compressão não aceite: gzip"),
        (Reply(error=TimeoutError("timed out")), "TransportError: tempo esgotado"),
        (feed(b"<rss><channel>"), "FeedError: XML malformado: no element found: line 1, column 14"),
        (feed(fixture("atom.xml")), "FeedError: formato não suportado: {http://www.w3.org/2005/Atom}feed"),
        (
            feed(b'<!DOCTYPE r [<!ENTITY a "b">]><rss><channel/></rss>'),
            "FeedError: DOCTYPE não permitido",
        ),
    ],
)  # fmt: skip
def test_rss_failure_sets_last_error_and_keeps_last_success_at(
    db, monkeypatch, server_reply, error
):
    assert collect_cli(monkeypatch, db, serving(fixture("valid.xml"))) == 0
    success_at, _, updated_at = endpoint_state(db)
    assert collect_cli(monkeypatch, db, serving(server_reply)) == 1
    assert endpoint_state(db) == (success_at, f"o collector falhou: {error}", updated_at)
    assert len(raw_items(db)) == 3


def test_robots_disallow_is_an_endpoint_failure_without_feed_request(db, monkeypatch):
    server = FakeServer(
        {
            (HOST, "/robots.txt"): robots("User-agent: *\nDisallow: /"),
            (HOST, "/rss.xml"): feed(fixture("valid.xml")),
        }
    )
    assert collect_cli(monkeypatch, db, server) == 1
    assert endpoint_state(db)[1] == "o collector falhou: TransportError: robots.txt não permite"
    assert server.paths() == [f"{HOST}/robots.txt"]
    assert raw_items(db) == []


def test_non_public_destination_is_an_endpoint_failure_without_connection(db, monkeypatch):
    server = serving(fixture("valid.xml"))
    server.addresses[HOST] = ["192.168.0.10"]
    assert collect_cli(monkeypatch, db, server) == 1
    assert endpoint_state(db)[1] == "o collector falhou: TransportError: destino não público"
    assert server.requests == []


def test_doctype_in_http_response_is_rejected_by_the_parser(db, monkeypatch):
    body = fixture("valid.xml").replace(
        b"<rss ", b'<!DOCTYPE rss SYSTEM "https://feed.example.org/x.dtd">\n<rss '
    )
    assert collect_cli(monkeypatch, db, serving(body)) == 1
    assert endpoint_state(db)[1] == "o collector falhou: FeedError: DOCTYPE não permitido"


def test_success_clears_last_error(db, monkeypatch):
    collect_cli(monkeypatch, db, serving(Reply(500, {"Content-Type": "text/plain"})))
    assert endpoint_state(db)[1] == "o collector falhou: TransportError: HTTP 500"
    assert collect_cli(monkeypatch, db, serving(fixture("valid.xml"))) == 0
    assert endpoint_state(db)[1] is None


def test_last_success_at_only_changes_on_success(db, monkeypatch):
    clock = iter(T0 + timedelta(minutes=n) for n in range(100))

    def now():
        return next(clock)

    def collect_with(body):
        return run_collect(db, registry_for(serving(body)), now=now)

    collect_with(fixture("valid.xml"))
    first = endpoint_state(db)[0]
    collect_with(INVALID_SECOND_ITEM)
    assert endpoint_state(db)[0] == first
    collect_with(fixture("empty.xml"))
    assert endpoint_state(db)[0] > first


def test_updated_at_keeps_m28_semantics(db, monkeypatch):
    updated_at = endpoint_state(db)[2]
    collect_cli(monkeypatch, db, serving(fixture("valid.xml")))
    collect_cli(monkeypatch, db, serving(INVALID_SECOND_ITEM))
    assert endpoint_state(db)[2] == updated_at == "2026-10-07T12:00:00.000000+00:00"


def test_run_stats_keep_the_dec031_structure(db, monkeypatch):
    collect_cli(monkeypatch, db, serving(fixture("valid.xml")))
    collect_cli(monkeypatch, db, serving(INVALID_SECOND_ITEM))
    assert run_stats(db) == [
        {
            "endpoints": [
                {
                    "id": "feed_sintetico",
                    "result": "success",
                    "new": 3,
                    "existing": 0,
                    "error": None,
                }
            ],
            "totals": {"selected": 1, "succeeded": 1, "failed": 0, "new": 3, "existing": 0},
        },
        {
            "endpoints": [
                {
                    "id": "feed_sintetico",
                    "result": "failed",
                    "new": 0,
                    "existing": 0,
                    "error": "o collector falhou: FeedError: item 2: sem link",
                }
            ],
            "totals": {"selected": 1, "succeeded": 0, "failed": 1, "new": 0, "existing": 0},
        },
    ]


# --- Collector ------------------------------------------------------------------


class RecordingTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.urls: list[str] = []

    def fetch_feed(self, url: str):
        from tensdireito_content_engine.collectors.http import Response

        self.urls.append(url)
        return Response(status=200, content_type="application/rss+xml", body=self.body)


def test_collector_fetches_the_endpoint_url_and_ignores_since():
    transport = RecordingTransport(fixture("valid.xml"))
    collector = RssCollector(transport, now=lambda: FETCHED)
    items = collector.fetch(ENDPOINTS[0], since=T0)
    assert transport.urls == [FEED_URL]
    assert len(items) == 3
    assert {item.fetched_at for item in items} == {FETCHED}


def test_collector_without_url_fails_without_transport():
    transport = RecordingTransport(b"")
    endpoint = SourceEndpoint(
        id="sem_url",
        source_id="fonte_sintetica",
        endpoint_type=EndpointType.RSS,
        endpoint_status=EndpointStatus.ACTIVE,
        **VALIDATED,
    )
    with pytest.raises(TransportError, match="URL ausente"):
        RssCollector(transport).fetch(endpoint, None)
    assert transport.urls == []


def test_collector_errors_are_the_two_collector_types():
    assert issubclass(FeedError, Exception) and issubclass(TransportError, Exception)
    assert not issubclass(FeedError, TransportError)


def test_schema_is_unchanged(db, monkeypatch):
    tables = query(db, "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    collect_cli(monkeypatch, db, serving(fixture("valid.xml")))
    assert query(db, "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name") == tables
    assert [row[0] for row in query(db, "SELECT version FROM schema_migration")] == [1, 2, 3, 4]
