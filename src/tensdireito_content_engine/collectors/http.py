"""Transporte HTTPS restrito dos collectors de produção (ROADMAP.md M2.9; DEC-033).

Único módulo do sistema que abre ligações de rede. Faz um `GET` ao URL de um feed e
devolve código, `Content-Type` e corpo em bytes, sem interpretar o conteúdo. Não há
função pública para obter um URL arbitrário: a única operação é `fetch_feed`, que o
collector `rss` chama com o `url` de um endpoint `ACTIVE`.

Política (valores fixos no código, DEC-033):
- URL só `https`, sem credenciais, porta omitida ou `443`, anfitrião por nome.
- Todos os endereços resolvidos têm de ser públicos; a ligação é aberta ao endereço
  verificado (não há segunda resolução), com TLS verificado para o nome do anfitrião.
- Só `200` é sucesso; `Content-Type` aceite por tipo de pedido; sem compressão;
  limites de tamanho e de tempo.
- Redirects (DEC-065/066, especificação §5 e §7): só para um endpoint com
  `redirect_hosts`, para um desses anfitriões (lista exacta), um único salto e só
  HTTPS → HTTPS; o destino é revalidado como um pedido novo (URL, IP público,
  robots.txt, limites) antes de ser contactado. Sem autorização, o redirect é recusado
  com o destino e o motivo, e o pedido não é repetido.
- Novas tentativas: 429/503 têm uma, após o `Retry-After` (segundos ou data HTTP, até
  60 s; sem cabeçalho ou inválido, 20 s). Excepção documentada: num endpoint
  `redirect_is_throttle` (as pesquisas do Bing), um 302/307 é limitação e tem uma nova
  tentativa após 20 s. No máximo uma nova tentativa por pedido.
- Pedidos sequenciais, intervalo mínimo por anfitrião.
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
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urljoin, urlsplit
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
# DEC-066 (revê DEC-062): 429/503 têm uma nova tentativa, após o `Retry-After` até 60 s
# (20 s sem cabeçalho ou com valor inválido); um redirect não é uma falha transitória.
RETRY_STATUSES = frozenset({429, 503})
RETRY_DELAY_SECONDS = 20.0
RETRY_AFTER_MAX_SECONDS = 60.0
REDIRECT_STATUSES = frozenset({301, 302, 307, 308})
# Excepção documentada (DEC-066): só em endpoints `redirect_is_throttle`.
THROTTLE_STATUSES = frozenset({302, 307})
HTTPS_PORT = 443
READ_CHUNK_BYTES = 64 * 1024


class TransportError(Exception):
    """Falha de transporte; a mensagem é determinista e nunca inclui o corpo da resposta."""


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    content_type: str  # tipo de media, sem parâmetros, em minúsculas
    body: bytes


@dataclass(frozen=True, slots=True)
class TransportEvent:
    """O que aconteceu num pedido bem-sucedido além do pedido simples, para o resumo."""

    kind: str  # LIMITATION | RETRY | REDIRECT
    url: str
    detail: str


LIMITATION = "limitação"
RETRY = "nova tentativa"
REDIRECT = "redirect seguido"


class FeedTransport(Protocol):
    """Interface do transporte vista pelos collectors."""

    def fetch_feed(
        self,
        url: str,
        *,
        redirect_hosts: Collection[str] = (),
        redirect_is_throttle: bool = False,
    ) -> Response: ...


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


@dataclass(frozen=True, slots=True)
class _Reply:
    status: int
    response: Response | None  # só para `200`, já validada
    location: str | None = None
    retry_after: str | None = None


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
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._resolve = resolve
        self._connect = connect
        self._monotonic = monotonic
        self._sleep = sleep
        self._now = now
        self._robots: dict[str, RobotFileParser | TransportError] = {}
        self._last_request: dict[str, float] = {}
        self._events: list[TransportEvent] = []

    def fetch_feed(
        self,
        url: str,
        *,
        redirect_hosts: Collection[str] = (),
        redirect_is_throttle: bool = False,
    ) -> Response:
        """`GET` de um feed ou sitemap; `200` validado ou `TransportError`.

        `redirect_hosts` e `redirect_is_throttle` vêm do endpoint (`sources.yaml`).
        """
        allowed = frozenset(host.lower() for host in redirect_hosts)
        if allowed and redirect_is_throttle:
            raise TransportError("redirect_hosts e redirect_is_throttle não se combinam")
        target = _check_url(url)
        self._public_address(target.host)  # destino não público falha antes de robots.txt
        self._require_robots_permission(target.host, url)
        reply = self._get(target, _FEED)
        retried = False
        if reply.status in RETRY_STATUSES:
            reply, retried = self._retry(target, url, reply), True
        elif redirect_is_throttle and reply.status in THROTTLE_STATUSES:
            self._events.append(
                TransportEvent(LIMITATION, url, f"HTTP {reply.status}; espera 20 s")
            )
            self._sleep(RETRY_DELAY_SECONDS)
            reply, retried = self._get(target, _FEED), True
        if reply.status in REDIRECT_STATUSES and not redirect_is_throttle:
            destination = self._authorize_redirect(url, reply, allowed)
            reply = self._follow(url, destination, retried)
        if reply.status != 200:
            raise TransportError(_status_reason(reply.status))
        assert reply.response is not None
        return reply.response

    def drain_events(self) -> list[TransportEvent]:
        """Eventos desde a última chamada (limitações, novas tentativas, redirects)."""
        events, self._events = self._events, []
        return events

    # --- Novas tentativas e redirects (DEC-065/066) ------------------------------------

    def _retry(self, target: _Target, url: str, reply: _Reply) -> _Reply:
        delay = retry_after_seconds(reply.retry_after, self._now())
        self._events.append(TransportEvent(RETRY, url, f"HTTP {reply.status}; espera {delay:g} s"))
        self._sleep(delay)
        return self._get(target, _FEED)

    def _authorize_redirect(self, url: str, reply: _Reply, allowed: frozenset[str]) -> str:
        """Destino autorizado e revalidado como um pedido novo, ou `TransportError`."""
        if not reply.location or not reply.location.strip():
            raise TransportError(f"redirect recusado: {reply.status} sem Location")
        try:
            destination = urljoin(url, reply.location.strip())
        except ValueError:
            raise TransportError(
                f"redirect recusado: {reply.status} com Location inválido"
            ) from None

        def refuse(reason: str) -> TransportError:
            shown = _shorten(destination)
            return TransportError(f"redirect recusado: {reply.status} para {shown}: {reason}")

        if not allowed:
            raise refuse("endpoint sem redirect_hosts")
        try:
            target = _check_url(destination)
        except TransportError as exc:
            raise refuse(str(exc)) from None
        if target.host.lower() not in allowed:
            raise refuse("anfitrião fora de redirect_hosts")
        try:
            self._public_address(target.host)
            self._require_robots_permission(target.host, destination)
        except TransportError as exc:
            raise refuse(str(exc)) from None
        return destination

    def _follow(self, url: str, destination: str, retried: bool) -> _Reply:
        """Um único salto, já autorizado; um segundo redirect é recusado."""
        target = _check_url(destination)
        reply = self._get(target, _FEED)
        if reply.status in RETRY_STATUSES and not retried:
            reply = self._retry(target, destination, reply)
        if reply.status in REDIRECT_STATUSES:
            raise TransportError(
                f"redirect recusado: segundo redirect ({reply.status}) "
                f"depois de {_shorten(destination)}"
            )
        if reply.status == 200:
            self._events.append(TransportEvent(REDIRECT, url, f"→ {destination}"))
        return reply

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
            reply = self._get(_Target(host, "/robots.txt"), _ROBOTS)
        except TransportError as exc:
            return exc
        status, response = reply.status, reply.response
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

    def _get(self, target: _Target, policy: _Policy) -> _Reply:
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

    def _exchange(self, address: str, target: _Target, policy: _Policy) -> _Reply:
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
                return _Reply(
                    status,
                    None,
                    location=response.getheader("Location"),
                    retry_after=response.getheader("Retry-After"),
                )
            content_type, declared = _check_headers(response, policy)
            body = self._read_body(sock, response, policy, deadline)
            if declared is not None and len(body) != declared:
                # `http.client` não levanta `IncompleteRead` em `read(amt)`.
                raise TransportError("resposta incompleta")
            if content_type in policy.sniffed_content_types and not _looks_like_feed(body):
                raise TransportError(f"Content-Type não aceite: {content_type}")
            return _Reply(status, Response(status=status, content_type=content_type, body=body))
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


# O `Location` vem do servidor: nas mensagens (que vão para `last_error` e para o resumo)
# mostra-se no máximo este número de caracteres.
LOCATION_SHOWN_CHARS = 200


def _shorten(url: str) -> str:
    return url if len(url) <= LOCATION_SHOWN_CHARS else f"{url[:LOCATION_SHOWN_CHARS]}…"


def retry_after_seconds(value: str | None, now: datetime) -> float:
    """Espera de `Retry-After` (segundos ou data HTTP), entre 0 e 60 s; inválido → 20 s."""
    if value is None:
        return RETRY_DELAY_SECONDS
    text = value.strip()
    if text.isascii() and text.isdigit():
        seconds = float(int(text))
    else:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return RETRY_DELAY_SECONDS
        if when.tzinfo is None:  # formato asctime sem zona: as datas HTTP são GMT
            when = when.replace(tzinfo=UTC)
        seconds = max(0.0, (when - now).total_seconds())
    return min(seconds, RETRY_AFTER_MAX_SECONDS)


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
