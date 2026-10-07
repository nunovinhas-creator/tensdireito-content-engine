"""Salvaguarda de rede para todos os testes (ROADMAP.md M2.9, critério 18; DEC-033).

Qualquer tentativa de resolver um nome ou abrir uma ligação falha. Os testes do
transporte injectam resolução e ligação falsas; os que exercitam as funções por omissão
substituem explicitamente estas funções com `monkeypatch`.
"""

import socket

import pytest


class NetworkAccessError(AssertionError):
    pass


def _blocked(*_args, **_kwargs):
    raise NetworkAccessError("acesso à rede proibido nos testes")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
