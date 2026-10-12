"""Chave de deduplicação de URLs (`candidate.url_key`; especificação das fases 2–4, §4.1).

Regras fixas, cada uma com teste. Função pura: não acede à rede nem segue redirects.
A equivalência entre anfitriões (`www.` e sem `www.`) só se aplica quando os dois estão
nos `domains` da mesma fonte, e é decidida por quem chama (`equivalent_hosts`); aqui não
se adivinham equivalências.
"""

import re
from collections.abc import Collection
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = frozenset({"fbclid", "gclid", "ocid", "mc_cid", "mc_eid"})
TRACKING_PREFIXES = ("utm_",)
AMP_PARAMS = frozenset({"amp"})
AMP_VALUES = {"outputtype": "amp"}
DEFAULT_PORT = 443

_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
# Caracteres não reservados (RFC 3986 §2.3): descodificados quando vêm codificados.
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class UrlKeyError(ValueError):
    """URL que não pode dar uma chave (sem esquema HTTPS ou sem anfitrião)."""


def url_key(url: str, equivalent_hosts: Collection[str] = ()) -> str:
    """Chave normalizada de `url`.

    `equivalent_hosts`: anfitriões declarados na mesma fonte; se `www.<h>` e `<h>` estão
    ambos lá, a chave usa `<h>`.
    """
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise UrlKeyError(f"URL sem esquema HTTPS ou sem anfitrião: {url!r}")
    host = parts.hostname.lower()
    hosts = {h.lower() for h in equivalent_hosts}
    if host.startswith("www.") and host[4:] in hosts and host in hosts:
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, DEFAULT_PORT) else f"{host}:{port}"

    path = _normalize_percent(parts.path) or "/"
    if path.endswith("/amp/") or path.endswith("/amp"):
        path = path[: path.rfind("/amp")] or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(key) and not _is_amp(key, value)
    ]
    query.sort()
    encoded = urlencode(query, quote_via=quote, safe="")
    return urlunsplit(("https", netloc, path, encoded, ""))


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PREFIXES)


def _is_amp(key: str, value: str) -> bool:
    lowered = key.lower()
    return lowered in AMP_PARAMS or AMP_VALUES.get(lowered) == value.lower()


def _normalize_percent(path: str) -> str:
    """Hex do percent-encoding em maiúsculas; não reservados descodificados."""

    def fix(match: re.Match[str]) -> str:
        char = unquote(match.group(0))
        return char if char in _UNRESERVED else match.group(0).upper()

    return _PERCENT.sub(fix, path)
