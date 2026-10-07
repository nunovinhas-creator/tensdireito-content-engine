import dataclasses
import hashlib
import unicodedata
from datetime import UTC, date, datetime

import pytest

from tensdireito_content_engine.domain import Event, RawItem, SourceDocument
from tensdireito_content_engine.normalize import (
    NormalizedItem,
    fingerprint,
    normalize_published_at,
    normalize_raw_item,
    normalize_text,
    normalize_title,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

EVENT_AND_EDITORIAL_FIELDS = {
    "id",
    "event_id",
    "category",
    "subcategory",
    "secondary_categories",
    "audience",
    "impact_type",
    "legal_stage",
    "proposed_category",
    "proposed_impact_type",
    "proposed_legal_stage",
    "verification_status",
    "editorial_status",
    "source_tier",
    "document_kind",
    "language",
    "canonical_url",
}


def make_raw_item(**overrides) -> RawItem:
    fields = {
        "url": "documento-de-teste-1",
        "title": "Documento de teste",
        "raw_content": "O valor de referência passa a ser X.",
        "fetched_at": T0,
    }
    fields.update(overrides)
    return RawItem(**fields)


def make_item(text: str, title: str = "Título") -> NormalizedItem:
    return normalize_raw_item(make_raw_item(raw_content=text, title=title))


# --- normalize_text ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  texto  ", "texto"),
        ("\n\t texto \t\n", "texto"),
        ("um    dois\t\ttrês", "um dois três"),
        ("um  dois", "um dois"),
        ("linha 1\r\nlinha 2\rlinha 3", "linha 1\nlinha 2\nlinha 3"),
        ("linha 1   \n   linha 2", "linha 1\nlinha 2"),
        ("§1\n\n\n\n§2", "§1\n\n§2"),
        ("§1\n  \n \t \n§2", "§1\n\n§2"),
        ("§1\n\n§2", "§1\n\n§2"),
        ("", ""),
        ("   \r\n\t ", ""),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


def test_normalize_text_preserves_portuguese_characters_case_and_punctuation():
    raw = "Pensão de VELHICE: o IAS é 522,50 € — n.º 3, alínea ç) «até» 2027!"
    assert normalize_text(raw) == raw


def test_normalize_text_composes_unicode_to_nfc():
    decomposed = unicodedata.normalize("NFD", "Prestação ã é ç")
    assert decomposed != "Prestação ã é ç"
    assert normalize_text(decomposed) == "Prestação ã é ç"


def test_normalize_text_does_not_apply_compatibility_forms():
    # NFKC mudaria o significado ("m²" → "m2", "½" → "1⁄2"); só NFC é aplicado.
    assert normalize_text("área de 50 m² e ½ do valor") == "área de 50 m² e ½ do valor"


def test_normalize_text_does_not_remove_markup():
    assert normalize_text("<p>Texto  </p>") == "<p>Texto </p>"


def test_normalize_text_is_idempotent():
    raw = "  um   dois\r\n\r\n\r\n três   quatro  "
    once = normalize_text(raw)
    assert normalize_text(once) == once


@pytest.mark.parametrize("value", [None, 1, b"bytes", ["texto"]])
def test_normalize_text_rejects_non_str(value):
    with pytest.raises(TypeError):
        normalize_text(value)


# --- normalize_title --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Título  ", "Título"),
        ("Novo\n  valor\r\ndo IAS", "Novo valor do IAS"),
        ("a\t\tb", "a b"),
        ("", ""),
        (unicodedata.normalize("NFD", "Habitação"), "Habitação"),
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


@pytest.mark.parametrize("value", [None, 3.5])
def test_normalize_title_rejects_non_str(value):
    with pytest.raises(TypeError):
        normalize_title(value)


# --- normalize_published_at -------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-01T09:00:00Z", datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
        ("2026-10-01T09:00:00+00:00", datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
        ("2026-10-01T10:00:00+01:00", datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
        ("2026-10-01T00:30:00+01:00", datetime(2026, 9, 30, 23, 30, tzinfo=UTC)),
        ("  2026-10-01T09:00:00Z  ", datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
    ],
)
def test_published_at_with_explicit_offset_is_converted_to_utc(raw, expected):
    result = normalize_published_at(raw)
    assert result == expected
    assert result.tzinfo is UTC


@pytest.mark.parametrize(
    "raw",
    [
        "2026-10-01",  # data sem hora: não se inventa hora
        "2026-10-01T09:00:00",  # sem fuso: não se assume o fuso local
        "1 de Outubro de 2026",
        "Thu, 01 Oct 2026 09:00:00 GMT",  # formato não documentado
        "ontem",
        "",
    ],
)
def test_published_at_without_documented_representation_is_none(raw):
    assert normalize_published_at(raw) is None


def test_published_at_none_stays_none():
    assert normalize_published_at(None) is None


def test_published_at_rejects_non_str():
    with pytest.raises(TypeError):
        normalize_published_at(date(2026, 10, 1))  # type: ignore[arg-type]


# --- normalize_raw_item -----------------------------------------------------


def test_normalize_raw_item():
    raw = make_raw_item(
        title="  Novo\nvalor  ",
        raw_content="  Texto   bruto\r\n\r\n\r\nSegundo parágrafo  ",
        published_at_raw="2026-10-01T10:00:00+01:00",
    )
    item = normalize_raw_item(raw)
    assert item.title == "Novo valor"
    assert item.text == "Texto bruto\n\nSegundo parágrafo"
    assert item.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def test_normalize_raw_item_preserves_original():
    raw = make_raw_item(raw_content="  Texto   bruto  ", published_at_raw="2026-10-01")
    item = normalize_raw_item(raw)
    assert item.raw_item is raw
    assert item.raw_item.raw_content == "  Texto   bruto  "
    assert item.raw_item.published_at_raw == "2026-10-01"
    assert item.published_at is None


def test_normalize_raw_item_is_deterministic():
    raw = make_raw_item(raw_content="  a  b \n\n\n c ")
    assert normalize_raw_item(raw) == normalize_raw_item(raw)


@pytest.mark.parametrize("value", [None, "texto", {"raw_content": "texto"}])
def test_normalize_raw_item_rejects_non_raw_item(value):
    with pytest.raises(TypeError):
        normalize_raw_item(value)


def test_normalized_item_is_immutable():
    item = make_item("texto")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.text = "outro"  # type: ignore[misc]


def test_normalized_item_is_not_event_nor_source_document():
    item = make_item("texto")
    assert not isinstance(item, Event | SourceDocument)


def test_normalization_assigns_no_editorial_classification_or_verification():
    names = {f.name for f in dataclasses.fields(NormalizedItem)}
    assert names == {"raw_item", "title", "text", "published_at"}
    assert names.isdisjoint(EVENT_AND_EDITORIAL_FIELDS)


# --- fingerprint ------------------------------------------------------------


def test_fingerprint_is_sha256_hex_of_normalized_text():
    item = make_item("  Pensão   social \r\n")
    expected = hashlib.sha256("Pensão social".encode()).hexdigest()
    assert fingerprint(item) == expected
    assert len(fingerprint(item)) == 64


def test_fingerprint_is_deterministic():
    item = make_item("O valor passa a ser X.")
    assert fingerprint(item) == fingerprint(item)
    assert fingerprint(item) == fingerprint(make_item("O valor passa a ser X."))


def test_equivalent_raw_texts_have_same_fingerprint():
    a = make_item("  O valor\t passa a ser X.  ")
    b = make_item("O valor passa a ser X.")
    c = make_item(unicodedata.normalize("NFD", "O valor passa a ser X."))
    assert fingerprint(a) == fingerprint(b) == fingerprint(c)


@pytest.mark.parametrize(
    "other",
    [
        "O valor passa a ser Y.",
        "O valor passa a ser X",
        "o valor passa a ser X.",
        "O valor passa a ser X.\n\nNovo parágrafo.",
    ],
)
def test_small_content_differences_change_fingerprint(other):
    assert fingerprint(make_item(other)) != fingerprint(make_item("O valor passa a ser X."))


def test_paragraph_break_is_not_the_same_as_space():
    assert fingerprint(make_item("um\n\ndois")) != fingerprint(make_item("um dois"))


def test_accent_differences_change_fingerprint():
    assert fingerprint(make_item("pensão")) != fingerprint(make_item("pensao"))


def test_fingerprint_depends_only_on_normalized_text():
    a = make_item("Mesmo texto.", title="Título A")
    b = normalize_raw_item(
        make_raw_item(
            raw_content="Mesmo texto.",
            title="Título B",
            url="outro-documento",
            published_at_raw="2026-10-01T09:00:00Z",
        )
    )
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_is_not_an_event_id():
    value = fingerprint(make_item("texto"))
    assert isinstance(value, str)
    assert not isinstance(value, int)
    assert int(value, 16) >= 0  # hexadecimal
    assert "event_id" not in {f.name for f in dataclasses.fields(NormalizedItem)}


@pytest.mark.parametrize("value", [None, "texto", make_raw_item()])
def test_fingerprint_rejects_non_normalized_item(value):
    with pytest.raises(TypeError):
        fingerprint(value)
