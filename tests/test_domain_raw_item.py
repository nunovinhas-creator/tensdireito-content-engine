import dataclasses
import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest

from tensdireito_content_engine.domain import DomainValidationError, Event, RawItem

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

EVENT_AND_EDITORIAL_FIELDS = {
    "id",
    "event_id",
    "category",
    "subcategory",
    "audience",
    "impact_type",
    "legal_stage",
    "verification_status",
    "editorial_status",
    "source_tier",
    "document_kind",
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


def test_valid_raw_item_with_optional_fields():
    item = make_raw_item(
        source_endpoint_id="exemplo_fonte_oficial_noticias",
        external_id="guid-1",
        published_at_raw="1 de Outubro de 2026",
        manual_note="Pista indicada por um leitor.",
    )
    assert item.source_endpoint_id == "exemplo_fonte_oficial_noticias"
    assert item.published_at_raw == "1 de Outubro de 2026"


def test_raw_item_optional_fields_default_to_none():
    item = make_raw_item()
    assert item.source_endpoint_id is None
    assert item.external_id is None
    assert item.published_at_raw is None
    assert item.manual_note is None


def test_raw_item_preserves_original_content_untouched():
    content = "  <p>Texto\r\n  com   espaços</p>\n\n\n"
    title = "  Título\tbruto  "
    item = make_raw_item(raw_content=content, title=title)
    assert item.raw_content == content
    assert item.title == title


def test_raw_item_is_immutable():
    item = make_raw_item()
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.raw_content = "outro"  # type: ignore[misc]


def test_content_hash_is_sha256_of_raw_content():
    item = make_raw_item(raw_content="  conteúdo bruto  ")
    expected = hashlib.sha256("  conteúdo bruto  ".encode()).hexdigest()
    assert item.content_hash == expected


def test_content_hash_is_not_normalized():
    assert make_raw_item(raw_content="a  b").content_hash != (
        make_raw_item(raw_content="a b").content_hash
    )


@pytest.mark.parametrize("field", ["url", "title", "raw_content"])
@pytest.mark.parametrize("value", ["", "   ", None, 1])
def test_required_text_fields_reject_invalid(field, value):
    with pytest.raises(DomainValidationError):
        make_raw_item(**{field: value})


@pytest.mark.parametrize(
    "field", ["source_endpoint_id", "external_id", "published_at_raw", "manual_note"]
)
def test_optional_text_fields_reject_blank(field):
    with pytest.raises(DomainValidationError):
        make_raw_item(**{field: "  "})


@pytest.mark.parametrize(
    "fetched_at",
    [
        datetime(2026, 10, 1, 9, 0),
        datetime(2026, 10, 1, 9, 0, tzinfo=timezone(timedelta(hours=1))),
        "2026-10-01T09:00:00Z",
    ],
)
def test_fetched_at_must_be_utc_datetime(fetched_at):
    with pytest.raises(DomainValidationError):
        make_raw_item(fetched_at=fetched_at)


def test_raw_item_is_not_an_event():
    item = make_raw_item()
    assert not isinstance(item, Event)
    assert not issubclass(RawItem, Event)


def test_raw_item_has_no_editorial_or_verification_fields():
    names = {f.name for f in dataclasses.fields(RawItem)}
    assert names.isdisjoint(EVENT_AND_EDITORIAL_FIELDS)
