"""Testes do M2.9: transporte HTTPS restrito (ROADMAP.md M2.9; DEC-033).

Offline: resolução de nomes, ligação, relógio e espera falsos (`_fake_http.py`);
domínios reservados (`example.org`, `.test`; RFC 2606). A salvaguarda de `conftest.py`
faz falhar qualquer acesso real à rede.
"""

import ast
import http.client
import socket
import ssl
from pathlib import Path

import pytest
from _fake_http import FEED_URL, HOST, NO_ROBOTS, PUBLIC_IP, FakeServer, Reply, feed, robots

import tensdireito_content_engine
from tensdireito_content_engine.collectors import http as transport_module
from tensdireito_content_engine.collectors.http import (
    FEED_MAX_BYTES,
    PROJECT_URL,
    ROBOTS_MAX_BYTES,
    USER_AGENT,
    HttpsTransport,
    TransportError,
)

PACKAGE_DIR = Path(tensdireito_content_engine.__file__).parent
BODY = b"<rss><channel/></rss>"


def server_with(feed_reply: Reply | list[Reply], robots_reply: Reply = NO_ROBOTS, **kwargs):
    return FakeServer(
        {(HOST, "/robots.txt"): robots_reply, (HOST, "/rss.xml"): feed_reply}, **kwargs
    )


def failure(server: FakeServer, url: str = FEED_URL) -> str:
    with pytest.raises(TransportError) as info:
        server.transport().fetch_feed(url)
    return str(info.value)


# --- URL ------------------------------------------------------------------------


def test_https_url_is_fetched():
    server = server_with(feed(BODY, "application/rss+xml; charset=ISO-8859-1"))
    response = server.transport().fetch_feed(FEED_URL)
    assert (response.status, response.content_type, response.body) == (
        200,
        "application/rss+xml",
        BODY,
    )
    assert server.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml"]
    assert all(request.method == "GET" for request in server.requests)


def test_explicit_port_443_and_query_are_accepted_without_fragment():
    server = FakeServer({(HOST, "/rss?a=1&b=2"): feed(BODY)})
    server.transport().fetch_feed(f"https://{HOST}:443/rss?a=1&b=2#fragmento")
    assert server.requests[-1].path == "/rss?a=1&b=2"


def test_empty_path_requests_root():
    server = FakeServer({(HOST, "/"): feed(BODY)})
    server.transport().fetch_feed(f"https://{HOST}")
    assert server.requests[-1].path == "/"


@pytest.mark.parametrize(
    ("url", "error"),
    [
        (f"http://{HOST}/rss.xml", "esquema não permitido: http"),
        (f"ftp://{HOST}/rss.xml", "esquema não permitido: ftp"),
        (f"//{HOST}/rss.xml", "esquema não permitido: (nenhum)"),
        (f"https://utilizador:segredo@{HOST}/rss.xml", "credenciais no URL não permitidas"),
        (f"https://utilizador@{HOST}/rss.xml", "credenciais no URL não permitidas"),
        (f"https://{HOST}:8443/rss.xml", "porta não permitida: 8443"),
        (f"https://{HOST}:80/rss.xml", "porta não permitida: 80"),
        (f"https://{HOST}:abc/rss.xml", "URL inválido"),
        ("https:///rss.xml", "URL sem anfitrião"),
        ("https://127.0.0.1/rss.xml", "IP literal não permitido"),
        ("https://9.9.9.9/rss.xml", "IP literal não permitido"),
        ("https://[::1]/rss.xml", "IP literal não permitido"),
        ("https://[2606:4700::1111]/rss.xml", "IP literal não permitido"),
        ("", "URL ausente"),
    ],
)
def test_invalid_urls_fail_before_any_resolution_or_connection(url, error):
    server = server_with(feed(BODY))
    assert failure(server, url) == error
    assert server.resolved == []
    assert server.requests == []


# --- Destino (SSRF) -------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.10.20.30",
        "::1",
        "::ffff:127.0.0.1",
    ],
)
def test_loopback_destination_is_rejected_before_connecting(address):
    server = server_with(feed(BODY), addresses={HOST: [address]})
    assert failure(server) == "destino não público"
    assert server.requests == []


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "100.64.0.1",  # espaço partilhado (CGNAT)
        "169.254.169.254",  # link-local (metadados de nuvem)
        "fe80::1%eth0",
        "fc00::1",  # IPv6 local único
        "224.0.0.1",  # multicast
        "ff02::1",
        "240.0.0.1",  # reservado
        "0.0.0.0",
        "::",
        "192.0.2.10",  # documentação
        "2001:db8::1",
        "::ffff:10.0.0.1",
        "não-é-ip",
    ],
)
def test_non_public_destination_is_rejected_before_connecting(address):
    server = server_with(feed(BODY), addresses={HOST: [address]})
    assert failure(server) == "destino não público"
    assert server.requests == []


def test_any_non_public_address_among_several_is_rejected():
    server = server_with(feed(BODY), addresses={HOST: [PUBLIC_IP, "10.0.0.1"]})
    assert failure(server) == "destino não público"
    assert server.requests == []


def test_connection_goes_to_the_verified_address_with_the_host_name():
    server = server_with(feed(BODY), addresses={HOST: ["2606:4700::1111", PUBLIC_IP]})
    server.transport().fetch_feed(FEED_URL)
    assert {(request.address, request.host) for request in server.requests} == {
        ("2606:4700::1111", HOST)
    }


def test_resolution_failure_is_a_transport_failure():
    def resolve(host, port):
        raise socket.gaierror(-2, "Name or service not known")

    transport = HttpsTransport(resolve=resolve, connect=FakeServer().connect)
    with pytest.raises(TransportError, match="^resolução de nomes falhou: gaierror$"):
        transport.fetch_feed(FEED_URL)


def test_resolution_without_addresses_fails():
    server = server_with(feed(BODY), addresses={HOST: []})
    assert failure(server) == "resolução de nomes falhou: sem endereços"


def test_default_resolver_rejects_name_resolving_to_internal_address(monkeypatch):
    def getaddrinfo(host, port, *args, **kwargs):
        assert (host, port) == ("interno.test", 443)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    transport = HttpsTransport(connect=FakeServer().connect)
    with pytest.raises(TransportError, match="^destino não público$"):
        transport.fetch_feed("https://interno.test/rss.xml")


def test_default_connection_is_pinned_to_the_verified_address(monkeypatch):
    connected = []

    def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 443))]

    def create_connection(address, timeout=None, *args, **kwargs):
        connected.append((address, timeout))
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    with pytest.raises(TransportError) as info:
        HttpsTransport().fetch_feed(FEED_URL)
    assert "ConnectionRefusedError" in str(info.value)
    # A ligação vai ao endereço verificado (não há segunda resolução), com o limite de 20 s.
    assert connected == [((PUBLIC_IP, 443), 20.0)]


def test_default_tls_context_verifies_certificates():
    connection = transport_module._open_connection(PUBLIC_IP, HOST, 20.0)
    context = connection._context
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert connection.host == HOST
    assert connection.port == 443


# --- Resposta -------------------------------------------------------------------


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_not_followed(status):
    redirect = Reply(status, {"Location": "https://outro.example.org/rss.xml"})
    server = server_with(redirect)
    assert failure(server) == f"redirect não seguido: {status}"
    assert server.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml"]


@pytest.mark.parametrize("status", [201, 203, 204, 206, 400, 403, 404, 410, 429, 500, 503])
def test_only_200_is_success(status):
    server = server_with(Reply(status, {"Content-Type": "application/rss+xml"}, BODY))
    assert failure(server) == f"HTTP {status}"


@pytest.mark.parametrize("content_type", ["application/rss+xml", "application/xml", "text/xml"])
def test_accepted_feed_content_types(content_type):
    server = server_with(feed(BODY, f"{content_type.upper()} ; charset=utf-8"))
    assert server.transport().fetch_feed(FEED_URL).content_type == content_type


@pytest.mark.parametrize(
    ("headers", "error"),
    [
        ({}, "Content-Type ausente"),
        ({"Content-Type": ""}, "Content-Type ausente"),
        ({"Content-Type": "; charset=utf-8"}, "Content-Type ausente"),
        ({"Content-Type": "text/html"}, "Content-Type não aceite: text/html"),
        ({"Content-Type": "application/atom+xml"}, "Content-Type não aceite: application/atom+xml"),
        ({"Content-Type": "application/json"}, "Content-Type não aceite: application/json"),
        ({"Content-Type": "text/plain"}, "Content-Type não aceite: text/plain"),
    ],
)
def test_invalid_content_type_fails(headers, error):
    server = server_with(Reply(200, headers, BODY))
    assert failure(server) == error


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "br", "GZIP", "identity, gzip"])
def test_compression_is_refused(encoding):
    server = server_with(feed(BODY, **{"Content-Encoding": encoding}))
    assert failure(server) == f"compressão não aceite: {encoding.lower()}"


def test_identity_encoding_is_accepted():
    server = server_with(feed(BODY, **{"Content-Encoding": "Identity"}))
    assert server.transport().fetch_feed(FEED_URL).body == BODY


def test_feed_at_the_size_limit_is_accepted():
    body = b"x" * FEED_MAX_BYTES
    server = server_with(feed(body, **{"Content-Length": str(FEED_MAX_BYTES)}))
    assert len(server.transport().fetch_feed(FEED_URL).body) == FEED_MAX_BYTES


def test_declared_content_length_above_limit_fails_without_reading():
    server = server_with(feed(b"", **{"Content-Length": str(FEED_MAX_BYTES + 1)}))
    assert failure(server) == "resposta excede 5 MiB"
    assert server.reads == 0


def test_body_exceeding_limit_while_reading_fails():
    server = server_with(feed(b"<rss>" + b"x" * FEED_MAX_BYTES))  # sem Content-Length
    assert failure(server) == "resposta excede 5 MiB"
    assert server.reads <= FEED_MAX_BYTES // (64 * 1024) + 2


def test_understated_content_length_does_not_bypass_limit():
    server = server_with(feed(b"x" * (FEED_MAX_BYTES + 10), **{"Content-Length": "10"}))
    assert failure(server) == "resposta excede 5 MiB"


@pytest.mark.parametrize("length", ["abc", "-1"])
def test_invalid_content_length_fails(length):
    server = server_with(feed(BODY, **{"Content-Length": length}))
    assert failure(server) == "Content-Length inválido"


def test_error_messages_never_include_the_body():
    secret = b"CONTEUDO-SECRETO-DA-RESPOSTA"
    for reply in (
        Reply(500, {"Content-Type": "text/plain"}, secret),
        Reply(200, {"Content-Type": "text/html"}, secret),
        feed(secret * (FEED_MAX_BYTES // len(secret) + 1)),
    ):
        assert "SECRETO" not in failure(server_with(reply))


def test_body_is_returned_as_bytes_without_interpretation():
    body = b'<?xml version="1.0" encoding="ISO-8859-1"?><rss>\xe7\xe3o<!DOCTYPE x></rss>'
    server = server_with(feed(body, "text/xml; charset=utf-8"))
    assert server.transport().fetch_feed(FEED_URL).body == body


# --- Tempo e erros de ligação ---------------------------------------------------


@pytest.mark.parametrize(
    ("where", "error"),
    [
        ("connect", TimeoutError("timed out")),
        ("getresponse", TimeoutError("timed out")),
        ("read", TimeoutError("The read operation timed out")),
        ("connect", TimeoutError("timed out")),
    ],
)
def test_timeout_is_a_transport_failure(where, error):
    if where == "connect":
        server = server_with(feed(BODY), connect_error=error)
        server.routes.pop((HOST, "/robots.txt"))
        transport = server.transport()
        transport._robots[HOST] = _allow_all()
    elif where == "getresponse":
        server = server_with(Reply(error=error))
        transport = server.transport()
    else:
        server = server_with(Reply(200, {"Content-Type": "text/xml"}, BODY, read_error=error))
        transport = server.transport()
    with pytest.raises(TransportError, match="^tempo esgotado$"):
        transport.fetch_feed(FEED_URL)


def test_total_request_time_is_limited_to_60_seconds():
    server = server_with(feed(b"x" * 1000))
    reply = server.routes[(HOST, "/rss.xml")]
    reply.chunk = 10
    reply.on_read = lambda: setattr(server.clock, "now", server.clock.now + 7)
    assert failure(server) == "tempo esgotado"
    # Nove leituras de 7 s chegam aos 63 s: a seguinte já não é feita.
    assert server.reads == 9


def test_each_network_operation_is_limited_to_20_seconds():
    server = server_with(feed(b"x" * 100))
    server.routes[(HOST, "/rss.xml")].chunk = 30
    server.transport().fetch_feed(FEED_URL)
    timeouts = [timeout for sock in server.sockets for timeout in sock.timeouts]
    assert timeouts and all(0 < timeout <= 20 for timeout in timeouts)
    assert all(request.connect_timeout == 20 for request in server.requests)


def test_remaining_time_shortens_the_operation_timeout():
    server = server_with(feed(b"x" * 100))
    reply = server.routes[(HOST, "/rss.xml")]
    reply.chunk = 10
    reply.on_read = lambda: setattr(server.clock, "now", server.clock.now + 15)
    with pytest.raises(TransportError):
        server.transport().fetch_feed(FEED_URL)
    feed_socket = server.sockets[-1]
    assert feed_socket.timeouts[:5] == [20, 20, 20, 20, 15]


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError(111, "Connection refused"),
        ConnectionResetError(104, "Connection reset by peer"),
        ssl.SSLCertVerificationError("certificate verify failed"),
        ssl.SSLError("handshake"),
        OSError(101, "Network is unreachable"),
        http.client.RemoteDisconnected("Remote end closed connection"),
        http.client.BadStatusLine("lixo"),
    ],
)
def test_connection_errors_are_transport_failures(error):
    server = server_with(Reply(error=error))
    assert failure(server) == f"erro de ligação: {type(error).__name__}"


def test_incomplete_read_is_a_transport_failure():
    server = server_with(
        Reply(200, {"Content-Type": "text/xml"}, read_error=http.client.IncompleteRead(b"ab", 10))
    )
    assert failure(server) == "erro de ligação: IncompleteRead"


def test_failure_is_not_retried():
    server = server_with(Reply(503, {"Content-Type": "text/plain"}))
    failure(server)
    assert server.paths().count(f"{HOST}/rss.xml") == 1


def test_connections_are_closed():
    server = server_with(feed(BODY))
    server.transport().fetch_feed(FEED_URL)
    assert server.connections and all(connection.closed for connection in server.connections)
    assert server.responses and all(response.closed for response in server.responses)
    for reply in (Reply(500, {"Content-Type": "text/plain"}), feed(b"x" * (FEED_MAX_BYTES + 1))):
        server = server_with(reply)
        failure(server)
        assert all(connection.closed for connection in server.connections)
        assert all(response.closed for response in server.responses)


# --- Cabeçalhos e User-Agent ----------------------------------------------------


def test_user_agent_identifies_the_project_with_its_public_url_as_contact():
    assert USER_AGENT == (
        f"tensdireito-content-engine/{tensdireito_content_engine.__version__} "
        "(+https://github.com/nunovinhas-creator/tensdireito-content-engine)"
    )
    assert PROJECT_URL in USER_AGENT
    assert "@" not in USER_AGENT


def test_every_request_sends_the_user_agent_without_credentials_or_cookies():
    server = server_with(feed(BODY))
    server.transport().fetch_feed(FEED_URL)
    assert len(server.requests) == 2
    for request in server.requests:
        headers = {name.lower(): value for name, value in request.headers.items()}
        assert headers["user-agent"] == USER_AGENT
        assert headers["accept-encoding"] == "identity"
        assert not {"cookie", "authorization", "if-modified-since", "if-none-match"} & set(headers)


# --- robots.txt -----------------------------------------------------------------


def _allow_all():
    from urllib.robotparser import RobotFileParser

    parser = RobotFileParser()
    parser.parse([])
    return parser


@pytest.mark.parametrize(
    "rules",
    [
        "User-agent: *\nDisallow: /",
        "User-agent: *\nDisallow: /rss",
        "User-agent: tensdireito-content-engine\nDisallow: /",
        "User-agent: *\nAllow: /\n\nUser-agent: tensdireito-content-engine\nDisallow: /rss.xml",
    ],
)
def test_robots_disallow_fails_without_requesting_the_feed(rules):
    server = server_with(feed(BODY), robots(rules))
    assert failure(server) == "robots.txt não permite"
    assert server.paths() == [f"{HOST}/robots.txt"]


@pytest.mark.parametrize(
    "rules",
    [
        "",
        "User-agent: *\nDisallow:",
        "User-agent: *\nDisallow: /privado/",
        "User-agent: outro-robo\nDisallow: /",
        "﻿User-agent: *\nAllow: /rss.xml\nDisallow: /",
    ],
)
def test_robots_allow_requests_the_feed(rules):
    server = server_with(feed(BODY), robots(rules))
    assert server.transport().fetch_feed(FEED_URL).body == BODY
    assert server.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml"]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 451])
def test_robots_4xx_means_no_restrictions(status):
    server = server_with(feed(BODY), Reply(status, {"Content-Type": "text/html"}))
    assert server.transport().fetch_feed(FEED_URL).body == BODY


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (Reply(500, {"Content-Type": "text/plain"}), "HTTP 500"),
        (Reply(503, {"Content-Type": "text/plain"}), "HTTP 503"),
        (Reply(301, {"Location": "https://o.example.org/r"}), "redirect não seguido: 301"),
        (Reply(204), "HTTP 204"),
        (Reply(error=TimeoutError("timed out")), "tempo esgotado"),
        (Reply(error=ConnectionResetError(104, "reset")), "erro de ligação: ConnectionResetError"),
        (robots("User-agent: *\nAllow: /", "text/html"), "Content-Type não aceite: text/html"),
        (Reply(200, {"Content-Type": "text/plain"}, b"\xff\xfe\x00"), "robots.txt não é UTF-8"),
        (
            Reply(200, {"Content-Type": "text/plain", "Content-Encoding": "gzip"}),
            "compressão não aceite: gzip",
        ),
    ],
)  # fmt: skip
def test_robots_unavailable_is_total_prohibition(reply, reason):
    server = server_with(feed(BODY), reply)
    assert failure(server) == f"robots.txt indisponível, tratado como proibição: {reason}"
    assert server.paths() == [f"{HOST}/robots.txt"]


def test_robots_above_512_kib_is_total_prohibition():
    server = server_with(feed(BODY), robots("#" * (ROBOTS_MAX_BYTES + 1)))
    assert failure(server) == (
        "robots.txt indisponível, tratado como proibição: resposta excede 512 KiB"
    )
    assert server.paths() == [f"{HOST}/robots.txt"]


def test_robots_at_512_kib_is_accepted():
    text = "User-agent: *\nDisallow: /privado/\n"
    server = server_with(feed(BODY), robots(text + "#" * (ROBOTS_MAX_BYTES - len(text))))
    assert server.transport().fetch_feed(FEED_URL).body == BODY


def test_robots_is_requested_once_per_host_per_execution():
    other = "outro.example.org"
    server = FakeServer(
        {
            (HOST, "/robots.txt"): robots("User-agent: *\nDisallow: /privado/"),
            (HOST, "/a.xml"): feed(BODY),
            (HOST, "/b.xml"): feed(BODY),
            (HOST, "/privado/c.xml"): feed(BODY),
            (other, "/robots.txt"): NO_ROBOTS,
            (other, "/a.xml"): feed(BODY),
        }
    )
    transport = server.transport()
    transport.fetch_feed(f"https://{HOST}/a.xml")
    transport.fetch_feed(f"https://{HOST}/b.xml")
    with pytest.raises(TransportError, match="robots.txt não permite"):
        transport.fetch_feed(f"https://{HOST}/privado/c.xml")
    transport.fetch_feed(f"https://{other}/a.xml")
    assert server.paths() == [
        f"{HOST}/robots.txt",
        f"{HOST}/a.xml",
        f"{HOST}/b.xml",
        f"{other}/robots.txt",
        f"{other}/a.xml",
    ]
    # Uma nova execução (novo transporte) volta a pedir robots.txt.
    server.routes[(HOST, "/a.xml")] = feed(BODY)
    server.transport().fetch_feed(f"https://{HOST}/a.xml")
    assert server.paths()[-2:] == [f"{HOST}/robots.txt", f"{HOST}/a.xml"]


def test_robots_failure_is_remembered_for_the_execution():
    server = FakeServer(
        {
            (HOST, "/robots.txt"): Reply(503, {"Content-Type": "text/plain"}),
            (HOST, "/a.xml"): feed(BODY),
            (HOST, "/b.xml"): feed(BODY),
        }
    )
    transport = server.transport()
    for path in ("/a.xml", "/b.xml"):
        with pytest.raises(TransportError, match="robots.txt indisponível"):
            transport.fetch_feed(f"https://{HOST}{path}")
    assert server.paths() == [f"{HOST}/robots.txt"]


def test_robots_is_requested_over_https_on_the_same_host_with_the_same_policy():
    server = server_with(feed(BODY))
    server.transport().fetch_feed(FEED_URL)
    robots_request = server.requests[0]
    assert (robots_request.address, robots_request.host, robots_request.path) == (
        PUBLIC_IP,
        HOST,
        "/robots.txt",
    )
    assert robots_request.headers["User-Agent"] == USER_AGENT


# --- Ritmo ----------------------------------------------------------------------


def test_minimum_interval_between_requests_to_the_same_host():
    server = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/a.xml"): feed(BODY),
            (HOST, "/b.xml"): feed(BODY),
        }
    )
    transport = server.transport()
    transport.fetch_feed(f"https://{HOST}/a.xml")
    transport.fetch_feed(f"https://{HOST}/b.xml")
    times = [request.at for request in server.requests]
    assert len(times) == 3
    assert all(later - earlier >= 5 for earlier, later in zip(times, times[1:], strict=False))
    assert server.clock.sleeps == [5.0, 5.0]


def test_elapsed_time_counts_towards_the_interval():
    server = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/a.xml"): feed(BODY),
            (HOST, "/b.xml"): feed(BODY),
        }
    )
    transport = server.transport()
    transport.fetch_feed(f"https://{HOST}/a.xml")
    server.clock.now += 3
    transport.fetch_feed(f"https://{HOST}/b.xml")
    assert server.clock.sleeps == [5.0, 2.0]
    server.clock.now += 10
    server.routes[(HOST, "/a.xml")] = feed(BODY)
    transport.fetch_feed(f"https://{HOST}/a.xml")
    assert server.clock.sleeps == [5.0, 2.0]


def test_no_wait_between_different_hosts():
    other = "outro.example.org"
    server = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (other, "/robots.txt"): NO_ROBOTS,
            (other, "/a.xml"): feed(BODY),
        }
    )
    transport = server.transport()
    transport._robots[HOST] = _allow_all()
    server.routes[(HOST, "/a.xml")] = feed(BODY)
    transport.fetch_feed(f"https://{HOST}/a.xml")
    transport.fetch_feed(f"https://{other}/a.xml")
    # O primeiro pedido a `other` (robots.txt) não espera pelo pedido a HOST; só o feed de
    # `other` espera pelo robots.txt do mesmo anfitrião.
    assert [request.at for request in server.requests[:2]] == [1000.0, 1000.0]
    assert server.clock.sleeps == [5.0]


def test_failed_request_also_counts_for_the_interval():
    server = server_with(Reply(500, {"Content-Type": "text/plain"}))
    transport = server.transport()
    with pytest.raises(TransportError):
        transport.fetch_feed(FEED_URL)
    with pytest.raises(TransportError):
        transport.fetch_feed(FEED_URL)
    assert server.clock.sleeps == [5.0, 5.0]


# --- Superfície e isolamento ----------------------------------------------------


def test_transport_exposes_only_fetch_feed():
    public = {name for name in vars(HttpsTransport) if not name.startswith("_")}
    assert public == {"fetch_feed"}


NETWORK_MODULES = {"socket", "ssl", "http", "urllib.request", "urllib.robotparser", "asyncio"}


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.add(node.module)
    return modules


def _is_network(module: str) -> bool:
    return any(module == name or module.startswith(f"{name}.") for name in NETWORK_MODULES)


def test_only_the_transport_imports_network_modules():
    transport_path = PACKAGE_DIR / "collectors" / "http.py"
    assert {module for module in _imports(transport_path) if _is_network(module)}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if path == transport_path:
            continue
        assert not {module for module in _imports(path) if _is_network(module)}, path


def test_transport_does_not_know_xml_storage_or_raw_item():
    modules = _imports(PACKAGE_DIR / "collectors" / "http.py")
    assert not any(module.startswith("xml") for module in modules)
    assert not any("storage" in module or module == "sqlite3" for module in modules)
    source = (PACKAGE_DIR / "collectors" / "http.py").read_text(encoding="utf-8")
    assert "RawItem" not in source


# --- Respostas reais de `http.client` (sem rede) ----------------------------------


class _RawSocket:
    """Socket falso para `http.client.HTTPResponse`: serve bytes HTTP gravados.

    Como um socket real, deixa de aceitar `settimeout` depois de `http.client` fechar a
    resposta lida até ao fim (regressão encontrada na validação manual local).
    """

    def __init__(self, raw: bytes) -> None:
        import io

        self._file = io.BytesIO(raw)
        self.timeouts: list[float] = []

    def makefile(self, mode: str):
        return self._file

    def settimeout(self, value: float) -> None:
        if self._file.closed:
            raise OSError(9, "Bad file descriptor")
        self.timeouts.append(value)


class _RawConnection:
    def __init__(self, raw: dict[str, bytes]) -> None:
        self._raw = raw
        self.sock: _RawSocket | None = None
        self._response: http.client.HTTPResponse | None = None

    def request(self, method: str, url: str, *, headers) -> None:
        self.sock = _RawSocket(self._raw[url])

    def getresponse(self) -> http.client.HTTPResponse:
        response = http.client.HTTPResponse(self.sock, method="GET")
        response.begin()
        if response.will_close:
            self.sock = None  # como `HTTPConnection.getresponse`
        return response

    def close(self) -> None:
        pass


def _raw_transport(raw: dict[str, bytes]) -> HttpsTransport:
    return HttpsTransport(
        resolve=lambda host, port: [PUBLIC_IP],
        connect=lambda address, host, timeout: _RawConnection(raw),
        sleep=lambda seconds: None,
    )


ROBOTS_404 = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"


@pytest.mark.parametrize(
    "raw_feed",
    [
        b"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nContent-Length: 21\r\n"
        b"Connection: close\r\n\r\n<rss><channel/></rss>",
        b"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nTransfer-Encoding: chunked\r\n"
        b"Connection: close\r\n\r\n5\r\n<rss>\r\n10\r\n<channel/></rss>\r\n0\r\n\r\n",
        b"HTTP/1.0 200 OK\r\nContent-Type: text/xml\r\n\r\n<rss><channel/></rss>",
    ],
    ids=["content-length", "chunked", "http-1.0-ate-fechar"],
)
def test_real_http_client_responses_are_read_to_the_end(raw_feed):
    transport = _raw_transport({"/robots.txt": ROBOTS_404, "/rss.xml": raw_feed})
    assert transport.fetch_feed(FEED_URL).body == BODY


def test_real_http_client_truncated_body_is_a_transport_failure():
    raw_feed = b"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nContent-Length: 100\r\n\r\n<rss>"
    transport = _raw_transport({"/robots.txt": ROBOTS_404, "/rss.xml": raw_feed})
    with pytest.raises(TransportError, match="^resposta incompleta$"):
        transport.fetch_feed(FEED_URL)


def test_real_http_client_truncated_chunked_body_is_a_transport_failure():
    raw_feed = (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nTransfer-Encoding: chunked\r\n\r\n"
        b"20\r\n<rss>"
    )
    transport = _raw_transport({"/robots.txt": ROBOTS_404, "/rss.xml": raw_feed})
    with pytest.raises(TransportError, match="^erro de ligação: IncompleteRead$"):
        transport.fetch_feed(FEED_URL)


def test_body_shorter_than_content_length_is_rejected():
    server = server_with(feed(BODY, **{"Content-Length": str(len(BODY) + 1)}))
    assert failure(server) == "resposta incompleta"
