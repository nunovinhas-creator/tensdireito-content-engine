from datetime import UTC, datetime

import pytest

from tensdireito_content_engine.domain import (
    DocumentKind,
    DocumentStatus,
    DomainValidationError,
    EndpointStatus,
    EndpointType,
    EntityType,
    EvidenceStance,
    RegistryStatus,
    SourceDocument,
    SourceEndpoint,
    SourceEvidence,
    SourceRegistry,
    SourceTier,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
HASH = "a" * 64


def make_registry(**overrides) -> SourceRegistry:
    fields = {
        "id": "exemplo_fonte_oficial",
        "name": "Fonte oficial de exemplo",
        "entity_type": EntityType.PUBLIC_BODY,
        "tier": SourceTier.T1,
        "categories": ("seguranca_social",),
    }
    fields.update(overrides)
    return SourceRegistry(**fields)


def make_endpoint(**overrides) -> SourceEndpoint:
    fields = {
        "id": "exemplo_fonte_oficial_noticias",
        "source_id": "exemplo_fonte_oficial",
        "endpoint_type": EndpointType.HTML_PAGE,
    }
    fields.update(overrides)
    return SourceEndpoint(**fields)


def make_document(**overrides) -> SourceDocument:
    fields = {
        "id": 10,
        "raw_item_id": 3,
        "source_id": "exemplo_fonte_oficial",
        "canonical_url": "documento-de-teste-1",
        "title": "Documento de teste",
        "text": "O valor de referência passa a ser X.",
        "language": "pt",
        "source_tier": SourceTier.T1,
        "document_kind": DocumentKind.LEGAL_TEXT,
        "text_hash": HASH,
        "status": DocumentStatus.NORMALIZED,
    }
    fields.update(overrides)
    return SourceDocument(**fields)


def make_evidence(**overrides) -> SourceEvidence:
    fields = {
        "id": 100,
        "claim_id": 7,
        "source_document_id": 10,
        "quote": "passa a ser X",
        "stance": EvidenceStance.SUPPORTS,
        "source_tier": SourceTier.T1,
        "document_kind": DocumentKind.LEGAL_TEXT,
        "matched_by": "rules",
    }
    fields.update(overrides)
    return SourceEvidence(**fields)


# --- source_registry -------------------------------------------------------


def test_valid_candidate_registry():
    registry = make_registry()
    assert registry.registry_status is RegistryStatus.CANDIDATE
    assert registry.domains == ()


def test_candidate_registry_cannot_have_domains():
    with pytest.raises(DomainValidationError):
        make_registry(domains=("fonte.invalid",))


def test_validated_registry_requires_manual_validation():
    with pytest.raises(DomainValidationError):
        make_registry(registry_status=RegistryStatus.VALIDATED)
    registry = make_registry(
        registry_status=RegistryStatus.VALIDATED,
        domains=("fonte.invalid",),
        validated_at=T0,
        validated_by="Editora A",
    )
    assert registry.validated_by == "Editora A"


@pytest.mark.parametrize("actor", ["llm:classify@v1", "LLM:x", "  llm:extract_claims@v3"])
def test_registry_validator_cannot_be_llm(actor):
    with pytest.raises(DomainValidationError):
        make_registry(registry_status=RegistryStatus.VALIDATED, validated_at=T0, validated_by=actor)


@pytest.mark.parametrize("field", ["id", "name"])
def test_registry_required_text(field):
    with pytest.raises(DomainValidationError):
        make_registry(**{field: ""})


def test_registry_tier_must_be_typed():
    with pytest.raises(DomainValidationError):
        make_registry(tier="T5")


# --- source_endpoint -------------------------------------------------------


def test_valid_candidate_endpoint_has_no_assumed_url():
    endpoint = make_endpoint()
    assert endpoint.url is None
    assert endpoint.endpoint_status is EndpointStatus.CANDIDATE


@pytest.mark.parametrize("status", [EndpointStatus.VALIDATED, EndpointStatus.ACTIVE])
def test_validated_or_active_endpoint_requires_manual_validation(status):
    with pytest.raises(DomainValidationError):
        make_endpoint(endpoint_status=status)
    with pytest.raises(DomainValidationError):
        make_endpoint(endpoint_status=status, validated_at=T0, validated_by="llm:x@v1")
    endpoint = make_endpoint(endpoint_status=status, validated_at=T0, validated_by="Editor B")
    assert endpoint.endpoint_status is status


def test_endpoint_requires_source():
    with pytest.raises(DomainValidationError):
        make_endpoint(source_id=" ")


# --- source_document -------------------------------------------------------


def test_valid_document():
    document = make_document(published_at=T0)
    assert document.source_tier is SourceTier.T1


@pytest.mark.parametrize("field", ["canonical_url", "title", "text", "language"])
def test_document_required_text(field):
    with pytest.raises(DomainValidationError):
        make_document(**{field: ""})


def test_document_without_resolved_source_is_t4():
    with pytest.raises(DomainValidationError):
        make_document(source_id=None)
    document = make_document(source_id=None, source_tier=SourceTier.T4)
    assert document.source_tier is SourceTier.T4


def test_document_published_at_must_be_utc():
    with pytest.raises(DomainValidationError):
        make_document(published_at=datetime(2026, 10, 1))


def test_document_before_persistence_has_no_id():
    assert make_document(id=None).id is None
    with pytest.raises(DomainValidationError):
        make_document(id=0)


@pytest.mark.parametrize("value", [None, 0, -1, True, "3"])
def test_document_raw_item_id_is_required(value):
    with pytest.raises(DomainValidationError):
        make_document(raw_item_id=value)


def test_document_m211_optional_fields_accept_null():
    document = make_document(
        canonical_url=None, language=None, document_kind=None, text=None, text_hash=None
    )
    assert (document.canonical_url, document.language, document.document_kind) == (
        None,
        None,
        None,
    )
    assert (document.text, document.text_hash) == (None, None)


def test_document_status_is_document_status():
    with pytest.raises(DomainValidationError):
        make_document(status="normalized")
    assert {status.value for status in DocumentStatus} == {
        "normalized",
        "classified",
        "clustered",
        "ignored",
    }


@pytest.mark.parametrize(("text", "text_hash"), [(None, HASH), ("Texto.", None)])
def test_document_text_null_iff_text_hash_null(text, text_hash):
    with pytest.raises(DomainValidationError):
        make_document(text=text, text_hash=text_hash)


@pytest.mark.parametrize("value", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, ""])
def test_document_text_hash_is_lowercase_sha256_hex(value):
    with pytest.raises(DomainValidationError):
        make_document(text_hash=value)


@pytest.mark.parametrize("value", ["PT", "p", "port", "pt-PT", "pt ", "1a", "pö"])
def test_document_language_is_two_or_three_lowercase_ascii_letters(value):
    with pytest.raises(DomainValidationError):
        make_document(language=value)
    assert make_document(language="mwl").language == "mwl"


def test_document_kind_when_present_is_document_kind():
    with pytest.raises(DomainValidationError):
        make_document(document_kind="other")


def test_document_duplicate_of_requires_ignored_and_text_hash():
    duplicate = make_document(duplicate_of=4, status=DocumentStatus.IGNORED)
    assert duplicate.duplicate_of == 4
    with pytest.raises(DomainValidationError):
        make_document(duplicate_of=4, status=DocumentStatus.NORMALIZED)
    with pytest.raises(DomainValidationError):
        make_document(duplicate_of=4, status=DocumentStatus.IGNORED, text=None, text_hash=None)
    with pytest.raises(DomainValidationError):
        make_document(duplicate_of=0, status=DocumentStatus.IGNORED)


def test_document_has_no_classification_fields():
    fields = set(SourceDocument.__dataclass_fields__)
    assert fields == {
        "id",
        "raw_item_id",
        "source_id",
        "canonical_url",
        "title",
        "text",
        "language",
        "published_at",
        "source_tier",
        "document_kind",
        "text_hash",
        "duplicate_of",
        "status",
    }


# --- source_evidence -------------------------------------------------------


@pytest.mark.parametrize("matched_by", ["rules", "human", "llm:match_evidence@v1"])
def test_valid_evidence(matched_by):
    evidence = make_evidence(matched_by=matched_by, quote_offset=21)
    assert evidence.source_document_id == 10
    assert evidence.validated is False


@pytest.mark.parametrize("field", ["source_document_id", "claim_id", "id"])
@pytest.mark.parametrize("value", [None, 0, "10"])
def test_evidence_belongs_to_identifiable_document_and_claim(field, value):
    with pytest.raises(DomainValidationError):
        make_evidence(**{field: value})


@pytest.mark.parametrize("quote", ["", "   ", None])
def test_evidence_requires_literal_quote(quote):
    with pytest.raises(DomainValidationError):
        make_evidence(quote=quote)


@pytest.mark.parametrize("matched_by", ["", "llm:", "ai", "gpt"])
def test_evidence_origin_must_be_known(matched_by):
    with pytest.raises(DomainValidationError):
        make_evidence(matched_by=matched_by)


def test_evidence_stance_must_be_typed():
    with pytest.raises(DomainValidationError):
        make_evidence(stance="agrees")


def test_evidence_quote_offset_not_negative():
    with pytest.raises(DomainValidationError):
        make_evidence(quote_offset=-1)
