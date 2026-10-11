"""Agrupamento lexical de títulos (DEC-059)."""

import pytest

from tensdireito_content_engine.similarity import same_topic


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (
            "Prestação Social Única entra em vigor e agrega 13 apoios sociais",
            "Prestação Social Única entra em vigor hoje, mas só chega ao terreno a 31 de dezembro",
            True,
        ),
        (
            "Pensões vão aumentar 2,8% em janeiro",
            "Aumento das pensões de 2,8% confirmado para janeiro",
            True,
        ),
        (
            "Prestação Social Única entra em vigor e agrega 13 apoios sociais",
            "Prestação Social Única confirma ataque aos direitos de Segurança Social",
            False,
        ),
        ("Abono de família sobe em 2027", "Abono de família: prova escolar decide", False),
        ("", "Qualquer coisa", False),
    ],
)
def test_same_topic(first, second, expected):
    assert same_topic(first, second) is expected
