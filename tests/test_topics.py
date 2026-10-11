"""Mapa de apoios: áreas e guias do tensdireito.com (DEC-058)."""

from pathlib import Path

import pytest

from tensdireito_content_engine.topics import TopicMap, load_topic_map

APOIOS = Path(__file__).resolve().parents[1] / "config" / "apoios.yaml"


@pytest.fixture(scope="module")
def topic_map() -> TopicMap:
    return load_topic_map(APOIOS)


@pytest.mark.parametrize(
    ("title", "guide"),
    [
        ("Filho fez 16 anos e recebe abono de família? Prova escolar decide", "prova-escolar"),
        ("Abono de família sobe em 2027", "abono-de-familia"),
        ("Majoração do subsídio de desemprego prolongada", "majoracao-subsidio-desemprego"),
        ("Subsídio de desemprego: novas regras", "subsidio-desemprego"),
        ("Porta 65 Jovem com candidaturas abertas", "porta-65"),
        ("Pensão de sobrevivência em união de facto", "pensao-sobrevivencia-uniao-de-facto"),
        ("Prestação Social Única entra em vigor e agrega 13 apoios", "psu-lista-13-apoios"),
        ("CSI vai aumentar no OE2027", "complemento-solidario-idosos"),
    ],
)
def test_guide_is_chosen_from_the_title(topic_map, title, guide):
    assert topic_map.guide_for(title) == f"https://tensdireito.com/{guide}.html"


def test_no_guide_when_title_has_no_known_support(topic_map):
    assert topic_map.guide_for("Choque petrolífero: uma perda que se reparte") is None


def test_every_guide_url_is_https_on_tensdireito(topic_map):
    assert topic_map.guides
    assert all(g.url.startswith("https://tensdireito.com/") for g in topic_map.guides)


def test_areas_are_detected_by_whole_words(topic_map):
    names = {area.id for area in topic_map.areas_for("Aumento das pensões e Porta 65 em 2027")}
    assert {"reformas_pensoes", "habitacao"} <= names
    assert topic_map.areas_for("Largo da cidade recebe feira") == ()


def test_missing_file_gives_empty_map():
    empty = load_topic_map(Path("nao-existe.yaml"))
    assert empty == TopicMap()
    assert empty.guide_for("Abono de família") is None
