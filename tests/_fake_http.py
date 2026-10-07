"""Servidor HTTPS falso para os testes do transporte e do collector `rss` (M2.9).

Substitui a resolução de nomes e a abertura da ligação injectadas em `HttpsTransport`:
nenhum socket é aberto. Os anfitriões usam domínios reservados (RFC 2606) e o endereço
"público" nunca é contactado.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from tensdireito_content_engine.collectors.http import HttpsTransport

# Endereço global usado só como valor devolvido pela resolução falsa; nunca é contactado.
PUBLIC_IP = "9.9.9.9"
HOST = "feed.example.org"
FEED_URL = f"https://{HOST}/rss.xml"
RSS_TYPE = "application/rss+xml"


@dataclass
class Reply:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    chunk: int | None = None  # tamanho máximo devolvido por `read`
    error: BaseException | None = None  # levantada em `getresponse`
    read_error: BaseException | None = None  # levantada no primeiro `read`
    on_read: Callable[[], None] | None = None  # efeito em cada `read` (ex.: avançar o relógio)


def feed(body: bytes, content_type: str = RSS_TYPE, **headers: str) -> Reply:
    return Reply(200, {"Content-Type": content_type, **headers}, body)


def robots(text: str, content_type: str = "text/plain") -> Reply:
    return Reply(200, {"Content-Type": content_type}, text.encode("utf-8"))


NO_ROBOTS = Reply(404, {"Content-Type": "text/html"}, b"<h1>404</h1>")


class FakeSocket:
    def __init__(self) -> None:
        self.timeouts: list[float | None] = []

    def settimeout(self, value: float | None) -> None:
        self.timeouts.append(value)


class FakeResponse:
    def __init__(self, reply: Reply, server: "FakeServer") -> None:
        self.status = reply.status
        self._reply = reply
        self._headers = {name.lower(): value for name, value in reply.headers.items()}
        self._offset = 0
        self._server = server
        self.closed = False

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name.lower(), default)

    def close(self) -> None:
        self.closed = True

    def isclosed(self) -> bool:
        return self.closed

    def read(self, amt: int) -> bytes:
        self._server.reads += 1
        if self._reply.on_read is not None:
            self._reply.on_read()
        if self._reply.read_error is not None:
            raise self._reply.read_error
        size = min(amt, self._reply.chunk or amt)
        chunk = self._reply.body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


@dataclass
class Request:
    address: str
    host: str
    connect_timeout: float
    method: str = ""
    path: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    at: float = 0.0


class FakeConnection:
    def __init__(self, server: "FakeServer", request: Request) -> None:
        self._server = server
        self._request = request
        self.sock: FakeSocket | None = None
        self.closed = False

    def request(self, method: str, url: str, *, headers) -> None:
        self._request.method = method
        self._request.path = url
        self._request.headers = dict(headers)
        self.sock = FakeSocket()
        self._server.sockets.append(self.sock)

    def getresponse(self) -> FakeResponse:
        reply = self._server.routes.get((self._request.host, self._request.path))
        if reply is None:
            reply = Reply(404, {"Content-Type": "text/plain"}, b"")
        if isinstance(reply, list):  # respostas sucessivas para o mesmo caminho
            reply = reply.pop(0)
        if reply.error is not None:
            raise reply.error
        response = FakeResponse(reply, self._server)
        self._server.responses.append(response)
        return response

    def close(self) -> None:
        self.closed = True


class FakeClock:
    """Relógio monotónico e espera falsos: `sleep` avança o relógio sem esperar."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeServer:
    def __init__(self, routes=None, addresses=None, connect_error=None) -> None:
        self.routes: dict[tuple[str, str], Reply | list[Reply]] = dict(routes or {})
        self.addresses: dict[str, list[str]] = addresses or {}
        self.connect_error = connect_error
        self.requests: list[Request] = []
        self.resolved: list[str] = []
        self.connections: list[FakeConnection] = []
        self.sockets: list[FakeSocket] = []
        self.responses: list[FakeResponse] = []
        self.reads = 0
        self.clock = FakeClock()

    def resolve(self, host: str, port: int) -> list[str]:
        assert port == 443
        self.resolved.append(host)
        return self.addresses.get(host, [PUBLIC_IP])

    def connect(self, address: str, host: str, timeout: float) -> FakeConnection:
        request = Request(address=address, host=host, connect_timeout=timeout, at=self.clock.now)
        self.requests.append(request)
        if self.connect_error is not None:
            raise self.connect_error
        connection = FakeConnection(self, request)
        self.connections.append(connection)
        return connection

    def transport(self) -> HttpsTransport:
        return HttpsTransport(
            resolve=self.resolve,
            connect=self.connect,
            monotonic=self.clock.monotonic,
            sleep=self.clock.sleep,
        )

    def paths(self) -> list[str]:
        return [f"{request.host}{request.path}" for request in self.requests]
