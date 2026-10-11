"""Transporte HTTPS restrito dos collectors de produção (ROADMAP.md M2.9; DEC-033).

Único módulo do sistema que abre ligações de rede. Faz um `GET` ao URL de um feed e
devolve código, `Content-Type` e corpo em bytes, sem interpretar o conteúdo. Não há
função pública para obter um URL arbitrário: a única operação é `fetch_feed`, que o
collector `rss` chama com o `url` de um endpoint `ACTIVE`.

Política (valores fixos no código, DEC-033):
- URL só `https`, sem credenciais, porta omitida ou `443`, anfitrião por nome.
- Todos os endereços resolvidos têm de ser públicos; a ligação é aberta ao endereço
  verificado (não há segunda resolução), com TLS verificado para o nome do anfitrião.
- Redirects não são seguidos; só `200` é sucesso; `Content-Type` aceite por tipo de
  pedido; sem compressão; limites de tamanho e de tempo.
- Uma tentativa por pedido, pedidos sequenciais, intervalo mínimo por anfitrião.
- `robots.txt` obtido uma vez por anfitrião e por instância (uma execução de
  `tde collect`), antes do primeiro pedido do feed, e avaliado com `urllib.robotparser`.

A resolução de nomes, a abertura da ligação, o relógio e a espera são injectáveis; os
testes não usam a rede.
"""

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from tensdireito_content_engine import __version__

USER_AGENT_TOKEN = "tensdireito-content-engine"
PROJECT_URL = "https://github.com/nunovinhas-creator/tensdireito-content-engine"
USER_AGENT = f"{USER_AGENT_TOKEN}/{__version__} (+{PROJECT_URL})"

FEED_CONTENT_TYPES = frozenset({"application/rss+xml", "application/xml", "text/xml"})
# DEC-051: servidores que entregam RSS com um `Content-Type` HTML errado. Só se aceita
# quando o corpo começa (após BOM e espaços) por uma declaração XML ou por `<rss`.
FEED_SNIFFED_CONTENT_TYPES = frozenset({"text/html"})
_FEED_BODY_PREFIXES = (b"<?xml", b"<rss")
# DEC-052: alguns servidores (p. ex. Feedburner) entregam o robots.txt como `text/xml`.
ROBOTS_CONTENT_TYPES = frozenset({"text/plain", "text/xml"})
FEED_MAX_BYTES = 5 * 1024 * 1024
ROBOTS_MAX_BYTES = 512 * 1024
OPERATION_TIMEOUT_SECONDS = 20.0  # ligação e cada leitura
REQUEST_TIMEOUT_SECONDS = 60.0  # total por pedido
MIN_INTERVAL_SECONDS = 5.0  # entre pedidos ao mesmo anfitrião
HTTPS_PORT = 443
READ_CHUNK_BYTES = 64 * 1024


class TransportError(Exception):
    """Falha de transporte; a mensagem é determinista e nunca inclui o corpo da resposta."""


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    content_type: str  # tipo de media, sem parâmetros, em minúsculas
    body: bytes


class FeedTransport(Protocol):
    """Interface do transporte vista pelos collectors."""

    def fetch_feed(self, url: str) -> Response: ...


class _Socket(Protocol):
    def settimeout(self, value: float | None) -> None: ...


class _HTTPResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amt: int) -> bytes: ...

    def isclosed(self) -> bool: ...

    def close(self) -> None: ...


class _HTTPConnection(Protocol):
    sock: _Socket | None

    def request(self, method: str, url: str, *, headers: Mapping[str, str]) -> None: ...

    def getresponse(self) -> _HTTPResponse: ...

    def close(self) -> None: ...


Resolver = Callable[[str, int], Sequence[str]]
Connector = Callable[[str, str, float], _HTTPConnection]


@dataclass(frozen=True, slots=True)
class _Policy:
    name: str
    content_types: frozenset[str]
    max_bytes: int
    limit_label: str
    sniffed_content_types: frozenset[str] = frozenset()


_FEED = _Policy("feed", FEED_CONTENT_TYPES, FEED_MAX_BYTES, "5 MiB", FEED_SNIFFED_CONTENT_TYPES)
_ROBOTS = _Policy("robots.txt", ROBOTS_CONTENT_TYPES, ROBOTS_MAX_BYTES, "512 KiB")


@dataclass(frozen=True, slots=True)
class _Target:
    host: str
    path: str  # caminho e query, sem fragmento


def _resolve_addresses(host: str, port: int) -> list[str]:
    """Endereços IP de `host` pela resolução do sistema."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Ligação HTTPS ao endereço já verificado, com SNI e verificação TLS para `host`."""

    def __init__(self, address: str, host: str, timeout: float) -> None:
        super().__init__(host, HTTPS_PORT, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, HTTPS_PORT), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _open_connection(address: str, host: str, timeout: float) -> _HTTPConnection:
    return _PinnedHTTPSConnection(address, host, timeout)


class HttpsTransport:
    """Transporte de uma execução: guarda `robots.txt` e o último pedido por anfitrião."""

    def __init__(
        self,
        *,
        resolve: Resolver = _resolve_addresses,
        connect: Connector = _open_connection,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._resolve = resolve
        self._connect = connect
        self._monotonic = monotonic
        self._sleep = sleep
        self._robots: dict[str, RobotFileParser | TransportError] = {}
        self._last_request: dict[str, float] = {}

    def fetch_feed(self, url: str) -> Response:
        target = _check_url(url)
        self._public_address(target.host)  # destino não público falha antes de robots.txt
        self._require_robots_permission(target.host, url)
        status, response = self._get(target, _FEED)
        if status != 200:
            raise TransportError(_status_reason(status))
        assert response is not None
        return response

    # --- robots.txt ---------------------------------------------------------------

    def _require_robots_permission(self, host: str, url: str) -> None:
        if host not in self._robots:
            self._robots[host] = self._load_robots(host)
        robots = self._robots[host]
        if isinstance(robots, TransportError):
            raise TransportError(f"robots.txt indisponível, tratado como proibição: {robots}")
        if not robots.can_fetch(USER_AGENT_TOKEN, url):
            raise TransportError("robots.txt não permite")

    def _load_robots(self, host: str) -> RobotFileParser | TransportError:
        parser = RobotFileParser()
        try:
            status, response = self._get(_Target(host, "/robots.txt"), _ROBOTS)
        except TransportError as exc:
            return exc
        if 400 <= status < 500 or status in (301, 302, 307, 308):
            # 4xx segue RFC 9309; redirects são uma exceção de compatibilidade e não são seguidos.
            parser.parse([])
            return parser
        if status != 200:
            return TransportError(_status_reason(status))
        assert response is not None
        try:
            text = response.body.decode("utf-8-sig")
        except UnicodeDecodeError:
            return TransportError("robots.txt não é UTF-8")
        parser.parse(text.splitlines())
        return parser

    # --- Pedido -------------------------------------------------------------------

    def _get(self, target: _Target, policy: _Policy) -> tuple[int, Response | None]:
        """Faz o pedido; devolve o código e, só para `200`, a resposta já validada."""
        address = self._public_address(target.host)
        self._wait_for_turn(target.host)
        try:
            return self._exchange(address, target, policy)
        finally:
            self._last_request[target.host] = self._monotonic()

    def _public_address(self, host: str) -> str:
        try:
            addresses = list(self._resolve(host, HTTPS_PORT))
        except (OSError, ValueError) as exc:
            raise TransportError(f"resolução de nomes falhou: {type(exc).__name__}") from None
        if not addresses:
            raise TransportError("resolução de nomes falhou: sem endereços")
        for address in addresses:
            if not _is_public(address):
                raise TransportError("destino não público")
        return addresses[0]

    def _wait_for_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is None:
            return
        remaining = last + MIN_INTERVAL_SECONDS - self._monotonic()
        if remaining > 0:
            self._sleep(remaining)

    def _exchange(
        self, address: str, target: _Target, policy: _Policy
    ) -> tuple[int, Response | None]:
        deadline = self._monotonic() + REQUEST_TIMEOUT_SECONDS
        connection: _HTTPConnection | None = None
        response: _HTTPResponse | None = None
        try:
            connection = self._connect(address, target.host, self._timeout(deadline))
            connection.request("GET", target.path, headers=_headers(policy))
            # O socket fica guardado: `getresponse` pode desligá-lo da ligação (`will_close`).
            sock = connection.sock
            self._set_timeout(sock, deadline)
            response = connection.getresponse()
            status = response.status
            if status != 200:
                return status, None
            content_type, declared = _check_headers(response, policy)
            body = self._read_body(sock, response, policy, deadline)
            if declared is not None and len(body) != declared:
                # `http.client` não levanta `IncompleteRead` em `read(amt)`.
                raise TransportError("resposta incompleta")
            if content_type in policy.sniffed_content_types and not _looks_like_feed(body):
                raise TransportError(f"Content-Type não aceite: {content_type}")
            return status, Response(status=status, content_type=content_type, body=body)
        except TransportError:
            raise
        except TimeoutError:
            raise TransportError("tempo esgotado") from None
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise TransportError(f"erro de ligação: {type(exc).__name__}") from None
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()

    def _timeout(self, deadline: float) -> float:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise TransportError("tempo esgotado")
        return min(OPERATION_TIMEOUT_SECONDS, remaining)

    def _set_timeout(self, sock: _Socket | None, deadline: float) -> None:
        timeout = self._timeout(deadline)
        if sock is not None:
            sock.settimeout(timeout)

    def _read_body(
        self,
        sock: _Socket | None,
        response: _HTTPResponse,
        policy: _Policy,
        deadline: float,
    ) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            # Com a resposta lida até ao fim, `http.client` fecha o socket; parar aqui evita
            # mexer num socket já fechado.
            if response.isclosed():
                return b"".join(chunks)
            self._set_timeout(sock, deadline)
            chunk = response.read(min(READ_CHUNK_BYTES, policy.max_bytes + 1 - size))
            if not chunk:
                return b"".join(chunks)
            size += len(chunk)
            if size > policy.max_bytes:
                raise TransportError(f"resposta excede {policy.limit_label}")
            chunks.append(chunk)


def _check_url(url: str) -> _Target:
    if not isinstance(url, str) or not url:
        raise TransportError("URL ausente")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise TransportError("URL inválido") from None
    if parts.scheme != "https":
        raise TransportError(f"esquema não permitido: {parts.scheme or '(nenhum)'}")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise TransportError("credenciais no URL não permitidas")
    if port is not None and port != HTTPS_PORT:
        raise TransportError(f"porta não permitida: {port}")
    host = parts.hostname
    if not host:
        raise TransportError("URL sem anfitrião")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise TransportError("IP literal não permitido")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return _Target(host=host, path=path)


def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _headers(policy: _Policy) -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": ", ".join(sorted(policy.content_types)),
        "Accept-Encoding": "identity",
        "Connection": "close",
    }


def _check_headers(response: _HTTPResponse, policy: _Policy) -> tuple[str, int | None]:
    """Valida compressão, `Content-Type` e `Content-Length`.

    Devolve o tipo de media e o tamanho declarado (se houver).
    """
    encoding = (response.getheader("Content-Encoding") or "identity").strip().lower()
    if encoding != "identity":
        raise TransportError(f"compressão não aceite: {encoding}")
    raw_type = response.getheader("Content-Type")
    if raw_type is None or not raw_type.split(";", 1)[0].strip():
        raise TransportError("Content-Type ausente")
    content_type = raw_type.split(";", 1)[0].strip().lower()
    if content_type not in policy.content_types | policy.sniffed_content_types:
        raise TransportError(f"Content-Type não aceite: {content_type}")
    length = response.getheader("Content-Length")
    declared = None
    if length is not None:
        try:
            declared = int(length.strip())
        except ValueError:
            raise TransportError("Content-Length inválido") from None
        if declared < 0:
            raise TransportError("Content-Length inválido")
        if declared > policy.max_bytes:
            raise TransportError(f"resposta excede {policy.limit_label}")
    return content_type, declared


def _looks_like_feed(body: bytes) -> bool:
    """O corpo começa por uma declaração XML ou por `<rss` (DEC-051)."""
    head = body[:512].removeprefix(b"\xef\xbb\xbf").lstrip().lower()
    return head.startswith(_FEED_BODY_PREFIXES)


def _status_reason(status: int) -> str:
    if 300 <= status < 400:
        return f"redirect não seguido: {status}"
    return f"HTTP {status}"
