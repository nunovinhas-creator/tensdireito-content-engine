"""Fase 2c (DEC-070): redirects (DEC-065) e novas tentativas separadas (DEC-066).

Testes de aceitação da §9 da especificação das fases 2–4: segurança dos redirects,
`Retry-After` em 429/503 e a separação entre redirect e falha transitória. Offline, com
o servidor falso de `_fake_http.py`.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from _fake_http import FEED_URL, HOST, NO_ROBOTS, FakeServer, Reply, feed, robots

from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.collectors.http import (
    LIMITATION,
    REDIRECT,
    RETRY,
    TransportError,
    retry_after_seconds,
)
from tensdireito_content_engine.collectors.news_sitemap import NewsSitemapCollector
from tensdireito_content_engine.collectors.rss import RssCollector
from tensdireito_content_engine.domain import (
    DomainValidationError,
    EndpointStatus,
    EndpointType,
    SourceEndpoint,
)

BODY = b"<rss><channel/></rss>"
DEST_HOST = "destino.example.org"
DEST_URL = f"https://{DEST_HOST}/rss.xml"
WALL = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def redirect(status: int = 302, location: str = DEST_URL) -> Reply:
    return Reply(status, {"Location": location})


def unavailable(status: int = 503, **headers: str) -> Reply:
    return Reply(status, {"Content-Type": "text/plain", **headers})


def server(feed_reply, dest_reply=None, dest_robots=NO_ROBOTS, **kwargs) -> FakeServer:
    routes = {(HOST, "/robots.txt"): NO_ROBOTS, (HOST, "/rss.xml"): feed_reply}
    if dest_reply is not None:
        routes[(DEST_HOST, "/robots.txt")] = dest_robots
        routes[(DEST_HOST, "/rss.xml")] = dest_reply
    return FakeServer(routes, **kwargs)


def refusal(srv: FakeServer, **options) -> str:
    with pytest.raises(TransportError) as info:
        srv.transport().fetch_feed(FEED_URL, **options)
    return str(info.value)


def dest_requests(srv: FakeServer) -> list[str]:
    return [path for path in srv.paths() if path.startswith(DEST_HOST)]


# --- Redirects autorizados (DEC-065) -------------------------------------------------


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_to_an_approved_host_is_followed_once(status):
    srv = server(redirect(status), feed(BODY))
    transport = srv.transport()
    assert transport.fetch_feed(FEED_URL, redirect_hosts=[DEST_HOST]).body == BODY
    assert srv.paths() == [
        f"{HOST}/robots.txt",
        f"{HOST}/rss.xml",
        f"{DEST_HOST}/robots.txt",  # o destino é revalidado como um pedido novo
        f"{DEST_HOST}/rss.xml",
    ]
    assert [(e.kind, e.url, e.detail) for e in transport.drain_events()] == [
        (REDIRECT, FEED_URL, f"→ {DEST_URL}")
    ]
    assert transport.drain_events() == []


def test_relative_location_resolves_against_the_original_url():
    srv = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/rss.xml"): redirect(301, "/novo.xml"),
            (HOST, "/novo.xml"): feed(BODY),
        }
    )
    response = srv.transport().fetch_feed(FEED_URL, redirect_hosts=[HOST])
    assert response.body == BODY
    assert srv.paths()[-1] == f"{HOST}/novo.xml"


def test_redirect_hosts_are_exact_hosts_not_domains():
    srv = server(redirect(302, f"https://www.{DEST_HOST}/rss.xml"), feed(BODY))
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == (
        f"redirect recusado: 302 para https://www.{DEST_HOST}/rss.xml: "
        "anfitrião fora de redirect_hosts"
    )


def test_destination_outside_redirect_hosts_is_refused_without_contacting_it():
    srv = server(redirect(302), feed(BODY))
    assert refusal(srv, redirect_hosts=["outro.example.org"]) == (
        f"redirect recusado: 302 para {DEST_URL}: anfitrião fora de redirect_hosts"
    )
    assert dest_requests(srv) == []
    assert DEST_HOST not in srv.resolved


def test_second_redirect_is_refused():
    srv = server(redirect(302), redirect(302, "https://terceiro.example.org/rss.xml"))
    assert refusal(srv, redirect_hosts=[DEST_HOST, "terceiro.example.org"]) == (
        f"redirect recusado: segundo redirect (302) depois de {DEST_URL}"
    )
    assert "terceiro.example.org" not in srv.resolved


def test_https_to_http_is_refused():
    srv = server(redirect(301, f"http://{DEST_HOST}/rss.xml"), feed(BODY))
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == (
        f"redirect recusado: 301 para http://{DEST_HOST}/rss.xml: esquema não permitido: http"
    )
    assert dest_requests(srv) == []


@pytest.mark.parametrize(
    "location",
    [
        f"https://{DEST_HOST}:8443/rss.xml",
        f"https://utilizador@{DEST_HOST}/rss.xml",
        "https://127.0.0.1/rss.xml",
        "https://[::1]/rss.xml",
    ],
    ids=["porta", "credenciais", "ip-literal-v4", "ip-literal-v6"],
)
def test_destination_url_is_checked_like_a_new_request(location):
    srv = server(redirect(302, location), feed(BODY))
    message = refusal(srv, redirect_hosts=[DEST_HOST, "127.0.0.1", "::1"])
    assert message.startswith(f"redirect recusado: 302 para {location}: ")
    assert dest_requests(srv) == []


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.7", "::1", "169.254.169.254"])
def test_destination_resolving_to_an_internal_address_is_refused(address):
    srv = server(redirect(302), feed(BODY), addresses={DEST_HOST: [address]})
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == (
        f"redirect recusado: 302 para {DEST_URL}: destino não público"
    )
    assert dest_requests(srv) == []
    assert all(request.address != address for request in srv.requests)


def test_destination_with_one_internal_address_among_public_ones_is_refused():
    srv = server(redirect(302), feed(BODY), addresses={DEST_HOST: ["9.9.9.9", "10.0.0.7"]})
    assert refusal(srv, redirect_hosts=[DEST_HOST]).endswith(": destino não público")
    assert dest_requests(srv) == []


def test_destination_whose_robots_txt_forbids_is_refused():
    srv = server(
        redirect(302), feed(BODY), dest_robots=robots("User-agent: *\nDisallow: /rss.xml\n")
    )
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == (
        f"redirect recusado: 302 para {DEST_URL}: robots.txt não permite"
    )
    assert dest_requests(srv) == [f"{DEST_HOST}/robots.txt"]


def test_long_location_is_shortened_in_the_message():
    location = f"https://{DEST_HOST}/" + "a" * 500
    srv = server(redirect(302, location), feed(BODY))
    message = refusal(srv)
    assert location[:200] + "…" in message
    assert len(message) < 300


def test_redirect_without_location_is_refused():
    srv = server(Reply(302, {}))
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == "redirect recusado: 302 sem Location"


def test_destination_failure_is_reported_as_the_destination_status():
    srv = server(redirect(302), Reply(404, {"Content-Type": "text/html"}))
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == "HTTP 404"


def test_destination_response_keeps_the_size_limit():
    from tensdireito_content_engine.collectors.http import FEED_MAX_BYTES

    srv = server(redirect(302), feed(b"x" * (FEED_MAX_BYTES + 1)))
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == "resposta excede 5 MiB"


# --- Excepção do Bing: `redirect_is_throttle` (DEC-066) ------------------------------


@pytest.mark.parametrize("status", [302, 307])
def test_throttle_redirect_is_retried_once_and_counted_as_limitation(status):
    srv = server([redirect(status), feed(BODY)])
    transport = srv.transport()
    assert transport.fetch_feed(FEED_URL, redirect_is_throttle=True).body == BODY
    assert srv.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml", f"{HOST}/rss.xml"]
    assert 20.0 in srv.clock.sleeps
    assert [e.kind for e in transport.drain_events()] == [LIMITATION]
    assert dest_requests(srv) == []


@pytest.mark.parametrize("status", [302, 307])
def test_persistent_throttle_fails_after_one_retry_without_following(status):
    srv = server(redirect(status))
    assert refusal(srv, redirect_is_throttle=True) == f"redirect não seguido: {status}"
    assert srv.paths().count(f"{HOST}/rss.xml") == 2
    assert dest_requests(srv) == []


@pytest.mark.parametrize("status", [301, 308])
def test_permanent_redirect_on_a_throttle_endpoint_is_not_repeated(status):
    srv = server(redirect(status))
    assert refusal(srv, redirect_is_throttle=True) == f"redirect não seguido: {status}"
    assert srv.paths().count(f"{HOST}/rss.xml") == 1


def test_redirect_hosts_and_throttle_do_not_combine():
    with pytest.raises(TransportError, match="não se combinam"):
        server(feed(BODY)).transport().fetch_feed(
            FEED_URL, redirect_hosts=[DEST_HOST], redirect_is_throttle=True
        )


# --- 429/503 e Retry-After (DEC-066) -------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ({"Retry-After": "7"}, 7.0),
        ({"Retry-After": "0"}, 0.0),
        ({"Retry-After": "120"}, 60.0),
        ({"Retry-After": format_datetime(WALL + timedelta(seconds=30), usegmt=True)}, 30.0),
        ({"Retry-After": format_datetime(WALL + timedelta(hours=2), usegmt=True)}, 60.0),
        ({"Retry-After": format_datetime(WALL - timedelta(minutes=5), usegmt=True)}, 0.0),
        ({"Retry-After": "amanhã"}, 20.0),
        ({"Retry-After": "-5"}, 20.0),
        ({"Retry-After": "2.5"}, 20.0),
        ({}, 20.0),
    ],
    ids=[
        "segundos",
        "zero",
        "acima-do-maximo",
        "data-http",
        "data-acima-do-maximo",
        "data-passada",
        "invalido",
        "negativo",
        "decimal",
        "sem-cabecalho",
    ],
)
@pytest.mark.parametrize("status", [429, 503])
def test_retry_after_is_respected_up_to_60_seconds(status, header, expected):
    srv = server([unavailable(status, **header), feed(BODY)])
    transport = srv.transport()
    assert transport.fetch_feed(FEED_URL).body == BODY
    assert srv.paths().count(f"{HOST}/rss.xml") == 2
    # Antes da nova tentativa: a espera do Retry-After; depois, só o intervalo por
    # anfitrião que ainda faltar (5 s), nunca mais do que isso.
    first_wait = srv.clock.sleeps[1]  # o primeiro é o intervalo entre robots.txt e o feed
    assert first_wait == expected
    assert sum(srv.clock.sleeps[1:]) == max(expected, 5.0)
    [event] = transport.drain_events()
    assert (event.kind, event.detail) == (RETRY, f"HTTP {status}; espera {expected:g} s")


@pytest.mark.parametrize("status", [429, 503])
def test_only_one_retry_for_429_and_503(status):
    srv = server([unavailable(status), unavailable(status), feed(BODY)])
    assert refusal(srv) == f"HTTP {status}"
    assert srv.paths().count(f"{HOST}/rss.xml") == 2


@pytest.mark.parametrize("status", [429, 503])
def test_429_and_503_are_never_treated_as_redirects(status):
    reply = Reply(status, {"Content-Type": "text/plain", "Location": DEST_URL})
    srv = server([reply, reply], feed(BODY))
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == f"HTTP {status}"
    assert dest_requests(srv) == []


def test_retry_then_redirect_is_followed_but_no_second_retry_at_the_destination():
    srv = server([unavailable(503), redirect(302)], [unavailable(503), feed(BODY)])
    assert refusal(srv, redirect_hosts=[DEST_HOST]) == "HTTP 503"
    assert dest_requests(srv) == [f"{DEST_HOST}/robots.txt", f"{DEST_HOST}/rss.xml"]


def test_destination_429_gets_the_one_retry_when_none_was_used():
    srv = server(redirect(302), [unavailable(429, **{"Retry-After": "6"}), feed(BODY)])
    transport = srv.transport()
    assert transport.fetch_feed(FEED_URL, redirect_hosts=[DEST_HOST]).body == BODY
    assert [e.kind for e in transport.drain_events()] == [RETRY, REDIRECT]


def test_retry_after_seconds_function():
    assert retry_after_seconds(None, WALL) == 20.0
    assert retry_after_seconds(" 12 ", WALL) == 12.0
    assert retry_after_seconds("Mon, 12 Oct 2026 09:00:45 GMT", WALL) == 45.0
    assert retry_after_seconds("Mon, 12 Oct 2026 09:00:45", WALL) == 45.0  # sem zona: GMT
    assert retry_after_seconds("١٢", WALL) == 20.0  # dígitos não ASCII


# --- Configuração por endpoint -------------------------------------------------------


def endpoint(**fields) -> SourceEndpoint:
    return SourceEndpoint(
        id="ep",
        source_id="fonte",
        endpoint_type=fields.pop("endpoint_type", EndpointType.RSS),
        url=FEED_URL,
        endpoint_status=EndpointStatus.ACTIVE,
        validated_at=WALL,
        validated_by="nuno",
        **fields,
    )


@pytest.mark.parametrize(
    "hosts",
    [
        ("https://jn.pt",),
        ("jn.pt:443",),
        ("JN.pt",),
        ("jn.pt/feed",),
        ("10.0.0.1",),
        ("jn",),
        ("jn.pt", "jn.pt"),
    ],
)
def test_redirect_hosts_must_be_plain_lowercase_host_names(hosts):
    with pytest.raises(DomainValidationError):
        endpoint(redirect_hosts=hosts)


def test_endpoint_cannot_combine_redirect_hosts_and_throttle():
    with pytest.raises(DomainValidationError, match="não se combinam"):
        endpoint(redirect_hosts=("www.jn.pt",), redirect_is_throttle=True)


class OptionsTransport:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.calls: list[tuple[str, tuple[str, ...], bool]] = []

    def fetch_feed(self, url, *, redirect_hosts=(), redirect_is_throttle=False):
        from tensdireito_content_engine.collectors.http import Response

        self.calls.append((url, tuple(redirect_hosts), redirect_is_throttle))
        return Response(status=200, content_type="application/xml", body=self.bodies[url])


def test_collectors_pass_the_endpoint_redirect_options_to_the_transport():
    rss = OptionsTransport({FEED_URL: BODY})
    RssCollector(rss).fetch(endpoint(redirect_is_throttle=True), None)
    assert rss.calls == [(FEED_URL, (), True)]

    sm = "http://www.sitemaps.org/schemas/sitemap/0.9"
    child = f"https://{HOST}/news-1.xml"
    index = (
        f'<?xml version="1.0"?><sitemapindex xmlns="{sm}">'
        f"<sitemap><loc>{child}</loc></sitemap></sitemapindex>"
    ).encode()
    urlset = f'<?xml version="1.0"?><urlset xmlns="{sm}"/>'.encode()
    sitemap = OptionsTransport({FEED_URL: index, child: urlset})
    NewsSitemapCollector(sitemap).fetch(
        endpoint(endpoint_type=EndpointType.NEWS_SITEMAP, redirect_hosts=(DEST_HOST,)), None
    )
    assert sitemap.calls == [(FEED_URL, (DEST_HOST,), False), (child, (DEST_HOST,), False)]


def test_registry_drains_events_from_its_transport():
    events = [["a"], []]
    registry = CollectorRegistry([], events=lambda: events.pop(0))
    assert registry.drain_events() == ["a"]
    assert registry.drain_events() == []
    assert CollectorRegistry().drain_events() == []


# --- Do YAML ao resumo ---------------------------------------------------------------

FEED_FIXTURE = (Path(__file__).parent / "fixtures" / "rss" / "valid.xml").read_bytes()

REGISTRY_YAML = """\
- id: fonte
  name: Fonte sintética
  entity_type: press
  tier: T3
  registry_status: VALIDATED
  validated_at: '2026-10-12T00:00:00Z'
  validated_by: nuno
  domains: [feed.example.org]
  endpoints:
  - id: a_limitado
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/limitado.xml'
    redirect_is_throttle: true
  - id: b_mudou
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/antigo.xml'
    redirect_hosts: [destino.example.org]
  - id: c_recusado
    endpoint_type: rss
    endpoint_status: ACTIVE
    validated_at: '2026-10-12T00:00:00Z'
    validated_by: nuno
    url: 'https://feed.example.org/recusado.xml'
"""


def collected(tmp_path):
    from tensdireito_content_engine.collect import run_collect
    from tensdireito_content_engine.sources import load_sources
    from tensdireito_content_engine.storage import init_database, sync_sources

    config = tmp_path / "sources.yaml"
    config.write_text(REGISTRY_YAML, encoding="utf-8")
    loaded = load_sources(config)
    db = tmp_path / "tde.sqlite3"
    init_database(db)
    sync_sources(db, loaded.sources, loaded.endpoints, now=lambda: WALL)
    srv = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/limitado.xml"): [redirect(307), feed(FEED_FIXTURE)],
            (HOST, "/antigo.xml"): redirect(301),
            (HOST, "/recusado.xml"): redirect(302),
            (DEST_HOST, "/robots.txt"): NO_ROBOTS,
            (DEST_HOST, "/rss.xml"): feed(FEED_FIXTURE),
        }
    )
    transport = srv.transport()
    registry = CollectorRegistry([RssCollector(transport)], events=transport.drain_events)
    return db, loaded, run_collect(db, registry, now=lambda: WALL)


def test_yaml_options_reach_the_transport_and_the_run_stats(tmp_path):
    import json
    import sqlite3

    db, loaded, result = collected(tmp_path)
    by_id = {endpoint.id: endpoint for endpoint in loaded.endpoints}
    assert by_id["a_limitado"].redirect_is_throttle is True
    assert by_id["b_mudou"].redirect_hosts == (DEST_HOST,)
    assert by_id["c_recusado"].redirect_hosts == ()

    outcomes = {outcome.id: outcome for outcome in result.endpoints}
    assert outcomes["a_limitado"].result == "success"
    assert outcomes["a_limitado"].notes == ("limitação: HTTP 307; espera 20 s",)
    assert outcomes["b_mudou"].result == "success"
    assert outcomes["b_mudou"].notes == (f"redirect seguido: → {DEST_URL}",)
    assert outcomes["c_recusado"].result == "failed"
    assert outcomes["c_recusado"].error == (
        "o collector falhou: TransportError: redirect recusado: 302 para "
        f"{DEST_URL}: endpoint sem redirect_hosts"
    )
    assert result.transport_counts() == {
        "limitação": 1,
        "nova tentativa": 0,
        "redirect seguido": 1,
        "redirect recusado": 1,
    }
    with sqlite3.connect(db) as conn:
        (stats,) = conn.execute("SELECT stats FROM run").fetchone()
        stored = dict(
            conn.execute(
                "SELECT id, redirect_hosts || '/' || redirect_is_throttle FROM source_endpoint"
            ).fetchall()
        )
    run_stats = json.loads(stats)
    assert run_stats["totals"]["transport"] == result.transport_counts()
    assert [e["notes"] for e in run_stats["endpoints"]] == [
        ["limitação: HTTP 307; espera 20 s"],
        [f"redirect seguido: → {DEST_URL}"],
        [],
    ]
    assert stored == {
        "a_limitado": "[]/1",
        "b_mudou": '["destino.example.org"]/0',
        "c_recusado": "[]/0",
    }


def test_summary_and_annotation_line_show_the_transport_events(tmp_path):
    from tensdireito_content_engine.cli import _transport_line, daily_summary_markdown
    from tensdireito_content_engine.daily import DailyResult

    db, _, collection = collected(tmp_path)
    assert _transport_line(collection) == (
        "TRANSPORTE: limitações 1; novas tentativas 0; redirects seguidos 1; redirects recusados 1"
    )
    result = DailyResult(
        day=WALL.date(),
        collection=collection,
        normalized=0,
        duplicates=0,
        articles=(),
        report_path=tmp_path / "r.txt",
        drafts_created=0,
    )
    summary = daily_summary_markdown(result)
    assert "### Limitações, novas tentativas e redirects" in summary
    assert "| `a_limitado` | limitação: HTTP 307; espera 20 s |" in summary
    assert f"| `b_mudou` | redirect seguido: → {DEST_URL} |" in summary


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("redirect_hosts", "destino.example.org", "redirect_hosts tem de ser uma lista"),
        ("redirect_hosts", [1], "redirect_hosts só pode conter texto"),
        ("redirect_is_throttle", "sim", "redirect_is_throttle tem de ser booleano"),
    ],
)
def test_yaml_rejects_badly_typed_redirect_options(tmp_path, field, value, message):
    import yaml

    from tensdireito_content_engine.sources import SourceRegistryError, load_sources

    data = yaml.safe_load(REGISTRY_YAML)
    data[0]["endpoints"][2][field] = value
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SourceRegistryError, match=message):
        load_sources(config)


def test_endpoints_not_yet_synced_after_0005_read_as_the_most_restrictive(tmp_path):
    import sqlite3

    from tensdireito_content_engine.storage import active_endpoints, init_database

    db = tmp_path / "tde.sqlite3"
    init_database(db)
    with sqlite3.connect(db) as conn:
        stamp = "2026-10-12T09:00:00.000000+00:00"
        conn.execute(
            "INSERT INTO source_registry (id, name, entity_type, tier, categories, domains, "
            "registry_status, validated_at, validated_by, created_at, updated_at) "
            "VALUES ('s', 'S', 'press', 'T3', '[]', '[]', 'validated', ?, 'nuno', ?, ?)",
            (stamp, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO source_endpoint (id, source_id, endpoint_type, url, endpoint_status, "
            "validated_at, validated_by, created_at, updated_at) "
            "VALUES ('e', 's', 'rss', 'https://s.example/f', 'active', ?, 'nuno', ?, ?)",
            (stamp, stamp, stamp),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE source_endpoint SET redirect_is_throttle = 2")
    conn = sqlite3.connect(db)
    try:
        [endpoint] = active_endpoints(conn)
    finally:
        conn.close()
    assert (endpoint.redirect_hosts, endpoint.redirect_is_throttle) == ((), False)


# --- Configuração versionada ---------------------------------------------------------


def test_bing_searches_are_the_only_throttle_endpoints_and_no_redirect_is_enabled():
    """DEC-066 (3) e (4): a excepção é só do Bing; nenhum `redirect_hosts` activo ainda."""
    from tensdireito_content_engine.config import DEFAULT_CONFIG_DIR, sources_path
    from tensdireito_content_engine.sources import load_sources

    loaded = load_sources(sources_path(DEFAULT_CONFIG_DIR))
    throttle = {e.id for e in loaded.endpoints if e.redirect_is_throttle}
    bing = {e.id for e in loaded.endpoints if e.url and "www.bing.com/news/search" in e.url}
    assert bing and throttle == bing
    assert [e.id for e in loaded.endpoints if e.redirect_hosts] == []
