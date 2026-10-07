import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from tensdireito_content_engine.domain import (
    EndpointStatus,
    EndpointType,
    EntityType,
    RegistryStatus,
    SourceTier,
)
from tensdireito_content_engine.sources import SourceRegistryError, load_sources, parse_sources

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

MINIMAL_SOURCE = """\
- id: fonte_a
  name: "Fonte A"
  entity_type: public_body
  tier: T1
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def errors_for(tmp_path: Path, text: str) -> tuple[str, ...]:
    with pytest.raises(SourceRegistryError) as exc:
        load_sources(write(tmp_path, text))
    return exc.value.errors


def source(**fields) -> dict:
    data = {"id": "fonte_a", "name": "Fonte A", "entity_type": "public_body", "tier": "T1"}
    data.update(fields)
    return data


def endpoint(**fields) -> dict:
    data = {"id": "fonte_a_pagina", "endpoint_type": "html_page"}
    data.update(fields)
    return data


def single_error(data: object) -> str:
    with pytest.raises(SourceRegistryError) as exc:
        parse_sources(data)
    assert len(exc.value.errors) == 1, exc.value.errors
    return exc.value.errors[0]


# YAML válido


def test_empty_registry_is_valid(tmp_path):
    loaded = load_sources(write(tmp_path, "[]\n"))
    assert loaded.sources == ()
    assert loaded.endpoints == ()


def test_minimal_source_uses_domain_defaults(tmp_path):
    loaded = load_sources(write(tmp_path, MINIMAL_SOURCE))
    (registry,) = loaded.sources
    assert registry.id == "fonte_a"
    assert registry.entity_type is EntityType.PUBLIC_BODY
    assert registry.tier is SourceTier.T1
    assert registry.registry_status is RegistryStatus.CANDIDATE
    assert registry.categories == ()
    assert registry.domains == ()
    assert registry.validated_at is None
    assert loaded.endpoints == ()


def test_fixture_with_multiple_sources_and_endpoints():
    loaded = load_sources(FIXTURES / "sources.yaml")
    assert [s.id for s in loaded.sources] == [
        "exemplo_fonte_oficial",
        "exemplo_fonte_validada",
        "exemplo_fonte_sem_endpoints",
    ]
    assert [(e.source_id, e.id) for e in loaded.endpoints] == [
        ("exemplo_fonte_oficial", "exemplo_fonte_oficial_noticias"),
        ("exemplo_fonte_oficial", "exemplo_fonte_oficial_manual"),
        ("exemplo_fonte_validada", "exemplo_fonte_validada_feed"),
    ]
    assert [s.tier for s in loaded.sources] == [SourceTier.T1, SourceTier.T2, SourceTier.T3]


def test_documented_enum_representation_maps_to_domain_values():
    loaded = load_sources(FIXTURES / "sources.yaml")
    official, validated, inactive = loaded.sources
    assert official.registry_status is RegistryStatus.CANDIDATE
    assert validated.registry_status is RegistryStatus.VALIDATED
    assert inactive.registry_status is RegistryStatus.INACTIVE
    assert validated.entity_type is EntityType.SPECIALISED
    noticias, manual, feed = loaded.endpoints
    assert noticias.endpoint_type is EndpointType.HTML_PAGE
    assert manual.endpoint_type is EndpointType.MANUAL
    assert feed.endpoint_type is EndpointType.RSS
    assert noticias.endpoint_status is EndpointStatus.CANDIDATE
    assert feed.endpoint_status is EndpointStatus.ACTIVE
    assert noticias.url is None


def test_validated_at_with_explicit_offset_is_converted_to_utc():
    loaded = load_sources(FIXTURES / "sources.yaml")
    assert loaded.sources[1].validated_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert loaded.endpoints[2].validated_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert loaded.endpoints[2].validated_at.tzinfo is UTC


def test_unquoted_timestamp_is_not_converted_by_yaml(tmp_path):
    loaded = load_sources(
        write(
            tmp_path,
            MINIMAL_SOURCE
            + "  registry_status: VALIDATED\n"
            + "  validated_at: 2026-10-01T09:00:00Z\n"
            + "  validated_by: editor_ficticio\n",
        )
    )
    assert loaded.sources[0].validated_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def test_loading_is_deterministic():
    assert load_sources(FIXTURES / "sources.yaml") == load_sources(FIXTURES / "sources.yaml")


# Erros estruturais


def test_missing_file(tmp_path):
    with pytest.raises(SourceRegistryError) as exc:
        load_sources(tmp_path / "nao_existe.yaml")
    assert exc.value.errors == (f"ficheiro não encontrado: {tmp_path / 'nao_existe.yaml'}",)


def test_invalid_yaml_reports_position(tmp_path):
    (error,) = errors_for(tmp_path, "- id: [fonte_a\n")
    assert error.startswith("YAML inválido em")
    assert "linha" in error


def test_repeated_yaml_key_is_rejected(tmp_path):
    (error,) = errors_for(tmp_path, MINIMAL_SOURCE + "  tier: T2\n")
    assert "chave repetida: 'tier'" in error


@pytest.mark.parametrize("text", ["", "fonte_a: {}\n", "texto\n", "42\n"])
def test_root_must_be_a_list(tmp_path, text):
    (error,) = errors_for(tmp_path, text)
    assert error.startswith("a raiz do registo tem de ser uma lista de fontes")


def test_source_must_be_a_mapping():
    assert single_error(["fonte_a"]) == (
        "sources[0]: cada fonte tem de ser um mapeamento, recebido texto"
    )


@pytest.mark.parametrize("field", ["id", "name", "entity_type", "tier"])
def test_source_required_fields(field):
    data = source()
    del data[field]
    assert f"campo obrigatório em falta: {field}" in single_error([data])


@pytest.mark.parametrize("field", ["id", "endpoint_type"])
def test_endpoint_required_fields(field):
    data = endpoint()
    del data[field]
    assert f"campo obrigatório em falta: {field}" in single_error([source(endpoints=[data])])


def test_required_text_cannot_be_empty():
    assert "name é obrigatório" in single_error([source(name="  ")])


def test_unknown_fields_are_rejected():
    assert single_error([source(tiers="T1")]).endswith("campo desconhecido: tiers")
    error = single_error([source(endpoints=[endpoint(last_error="x")])])
    assert error.endswith("campo desconhecido: last_error")


def test_duplicate_source_ids():
    error = single_error([source(), source(name="Outra")])
    assert error == (
        "sources[1] (id=fonte_a): id de fonte repetido "
        "(já usado em sources[0] (id=fonte_a)): fonte_a"
    )


def test_duplicate_endpoint_ids_across_sources():
    data = [
        source(endpoints=[endpoint()]),
        source(id="fonte_b", endpoints=[endpoint()]),
    ]
    error = single_error(data)
    assert error.startswith("sources[1].endpoints[0] (id=fonte_a_pagina): id de endpoint repetido")


def test_source_and_endpoint_ids_are_separate_namespaces():
    loaded = parse_sources([source(endpoints=[endpoint(id="fonte_a")])])
    assert loaded.endpoints[0].id == "fonte_a"


@pytest.mark.parametrize("tier", ["T5", "t1", 1, None])
def test_invalid_tier(tier):
    error = single_error([source(tier=tier)])
    assert error == f"sources[0] (id=fonte_a): tier inválido: {tier!r} (aceites: T1 | T2 | T3 | T4)"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity_type", "ministry"),
        ("entity_type", "PUBLIC_BODY"),
        ("registry_status", "ACTIVE"),
        ("registry_status", "candidate"),
    ],
)
def test_invalid_source_enums(field, value):
    assert f"{field} inválido: {value!r}" in single_error([source(**{field: value})])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint_type", "api"),
        ("endpoint_type", "RSS"),
        ("endpoint_status", "active"),
        ("endpoint_status", "PAUSED"),
    ],
)
def test_invalid_endpoint_enums(field, value):
    error = single_error([source(endpoints=[endpoint(**{field: value})])])
    assert f"{field} inválido: {value!r}" in error


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"name": 42}, "name tem de ser texto, recebido inteiro"),
        ({"id": True}, "id tem de ser texto, recebido booleano"),
        ({"categories": "consumo"}, "categories tem de ser uma lista, recebido texto"),
        ({"domains": [1]}, "domains só pode conter texto, recebido inteiro"),
        ({"notes": ["x"]}, "notes tem de ser texto, recebido lista"),
        ({"endpoints": {}}, "endpoints tem de ser uma lista, recebido mapeamento"),
        ({"endpoints": ["x"]}, "cada endpoint tem de ser um mapeamento, recebido texto"),
        ({"validated_at": 20261001}, "validated_at tem de ser texto ISO 8601, recebido inteiro"),
    ],
)
def test_wrong_types(fields, message):
    assert single_error([source(**fields)]).endswith(message)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"url": 1}, "url tem de ser texto, recebido inteiro"),
        ({"fetch": "daily"}, "fetch tem de ser um mapeamento, recebido texto"),
    ],
)
def test_wrong_endpoint_types(fields, message):
    assert single_error([source(endpoints=[endpoint(**fields)])]).endswith(message)


def test_repeated_categories_are_rejected_by_domain():
    assert "categories não pode ter valores repetidos" in single_error(
        [source(categories=["consumo", "consumo"])]
    )


def test_all_errors_are_reported_in_file_order():
    with pytest.raises(SourceRegistryError) as exc:
        parse_sources([source(tier="T9"), "x", source(id="fonte_b", entity_type="?")])
    assert [error.split(":")[0] for error in exc.value.errors] == [
        "sources[0] (id=fonte_a)",
        "sources[1]",
        "sources[2] (id=fonte_b)",
    ]


# Invariantes do domínio


VALIDATION = {"validated_at": "2026-10-01T09:00:00Z", "validated_by": "editor_ficticio"}


def test_candidate_source_cannot_have_domains():
    error = single_error([source(registry_status="CANDIDATE", domains=["exemplo.invalid"])])
    assert error.endswith("uma fonte CANDIDATE não pode ter domains")


@pytest.mark.parametrize("missing", ["validated_at", "validated_by"])
def test_validated_source_requires_manual_validation(missing):
    fields = {**VALIDATION, missing: None}
    error = single_error([source(registry_status="VALIDATED", **fields)])
    assert error.endswith("validação manual exige validated_at e validated_by")


def test_validated_endpoint_without_validated_at():
    data = endpoint(endpoint_status="VALIDATED", validated_by="editor_ficticio")
    error = single_error([source(endpoints=[data])])
    assert error.endswith("validação manual exige validated_at e validated_by")


def test_active_endpoint_without_validated_at():
    data = endpoint(
        endpoint_status="ACTIVE", url="https://exemplo.invalid/", validated_by="editor_ficticio"
    )
    error = single_error([source(endpoints=[data])])
    assert error.endswith("um endpoint ACTIVE exige validated_at")


def test_active_endpoint_without_url():
    data = endpoint(endpoint_status="ACTIVE", **VALIDATION)
    error = single_error([source(endpoints=[data])])
    assert error.endswith("um endpoint ACTIVE exige url")


def test_active_endpoint_without_url_nor_validated_at_reports_both():
    with pytest.raises(SourceRegistryError) as exc:
        parse_sources([source(endpoints=[endpoint(endpoint_status="ACTIVE")])])
    assert [e.split(": ", 1)[1] for e in exc.value.errors] == [
        "um endpoint ACTIVE exige url",
        "um endpoint ACTIVE exige validated_at",
    ]


def test_validated_endpoint_without_url_is_allowed():
    loaded = parse_sources(
        [source(endpoints=[endpoint(endpoint_status="VALIDATED", **VALIDATION)])]
    )
    assert loaded.endpoints[0].url is None


@pytest.mark.parametrize("actor", ["llm:classify@v1", "LLM:x", " llm:x"])
def test_validated_by_cannot_be_llm(actor):
    fields = {**VALIDATION, "validated_by": actor}
    assert "validated_by tem de ser uma pessoa" in single_error(
        [source(registry_status="VALIDATED", **fields)]
    )
    data = endpoint(endpoint_status="VALIDATED", **fields)
    assert "validated_by tem de ser uma pessoa" in single_error([source(endpoints=[data])])


@pytest.mark.parametrize("value", ["2026-10-01T09:00:00", "2026-10-01", "2026-10-01 09:00"])
def test_validated_at_without_timezone_is_rejected(value):
    fields = {**VALIDATION, "validated_at": value}
    error = single_error([source(registry_status="VALIDATED", **fields)])
    assert error.endswith(f"validated_at tem de indicar o fuso horário explicitamente: {value!r}")


@pytest.mark.parametrize("value", ["ontem", "01/10/2026 09:00 UTC", ""])
def test_validated_at_must_be_iso_8601(value):
    error = single_error([source(validated_at=value)])
    assert error.endswith(f"validated_at não é uma data/hora ISO 8601: {value!r}")


def test_endpoint_belongs_to_parent_source():
    loaded = parse_sources([source(id="fonte_x", endpoints=[endpoint()])])
    assert loaded.endpoints[0].source_id == "fonte_x"


# Decisões de formato (DEC-023, DEC-024, DEC-025)


DOCS = Path(__file__).parent.parent / "docs"


def test_documented_example_is_valid():
    # O exemplo de SOURCES.md §4 cumpre o schema fechado e a representação dos estados.
    text = (DOCS / "SOURCES.md").read_text(encoding="utf-8")
    block = text.split("## 4. Registo")[1].split("```yaml\n")[1].split("```")[0]
    loaded = parse_sources(yaml.safe_load(block))
    assert [s.id for s in loaded.sources] == ["exemplo_fonte_oficial"]
    assert [e.id for e in loaded.endpoints] == ["exemplo_fonte_oficial_noticias"]


@pytest.mark.parametrize(
    "fields",
    [
        {"id_fonte": "x"},
        {"endpoints": [{"id": "e", "endpoint_type": "rss", "frequency": "daily"}]},
    ],
)
def test_dec_023_unknown_field_at_any_supported_level_is_an_error(fields):
    assert "campo desconhecido" in single_error([source(**fields)])


def test_dec_023_fetch_content_is_not_a_validated_level():
    fetch = {"frequency": "daily", "qualquer": [1, {"a": None}], "selectors": {}}
    loaded = parse_sources([source(endpoints=[endpoint(fetch=fetch)])])
    (parsed,) = loaded.endpoints
    assert not hasattr(parsed, "fetch")  # não convertido: SourceEndpoint (M2.2) não o tem


@pytest.mark.parametrize("value", ["", None, {}])
def test_dec_023_fetch_absent_null_or_empty_mapping_is_accepted(value):
    data = endpoint() if value == "" else endpoint(fetch=value)
    assert len(parse_sources([source(endpoints=[data])]).endpoints) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CANDIDATE", RegistryStatus.CANDIDATE),
        ("VALIDATED", RegistryStatus.VALIDATED),
        ("INACTIVE", RegistryStatus.INACTIVE),
    ],
)
def test_dec_024_registry_status_uppercase_is_accepted(value, expected):
    fields = VALIDATION if value == "VALIDATED" else {}
    (parsed,) = parse_sources([source(registry_status=value, **fields)]).sources
    assert parsed.registry_status is expected
    assert parsed.registry_status.value == value.lower()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CANDIDATE", EndpointStatus.CANDIDATE),
        ("VALIDATED", EndpointStatus.VALIDATED),
        ("ACTIVE", EndpointStatus.ACTIVE),
        ("INACTIVE", EndpointStatus.INACTIVE),
    ],
)
def test_dec_024_endpoint_status_uppercase_is_accepted(value, expected):
    fields = {**VALIDATION, "url": "https://exemplo.invalid/"}
    data = endpoint(endpoint_status=value, **fields)
    (parsed,) = parse_sources([source(endpoints=[data])]).endpoints
    assert parsed.endpoint_status is expected


@pytest.mark.parametrize("value", ["candidate", "validated", "inactive", "Candidate"])
def test_dec_024_registry_status_lowercase_is_an_error(value):
    error = single_error([source(registry_status=value)])
    assert error.endswith(
        f"registry_status inválido: {value!r} (aceites: CANDIDATE | VALIDATED | INACTIVE)"
    )


@pytest.mark.parametrize("value", ["candidate", "validated", "active", "inactive"])
def test_dec_024_endpoint_status_lowercase_is_an_error(value):
    error = single_error([source(endpoints=[endpoint(endpoint_status=value)])])
    assert error.endswith(
        f"endpoint_status inválido: {value!r} (aceites: CANDIDATE | VALIDATED | ACTIVE | INACTIVE)"
    )


def test_dec_025_repeated_key_in_endpoint_is_an_error(tmp_path):
    text = MINIMAL_SOURCE + (
        "  endpoints:\n"
        "    - id: fonte_a_pagina\n"
        "      endpoint_type: html_page\n"
        "      endpoint_status: CANDIDATE\n"
        "      endpoint_status: ACTIVE\n"
    )
    (error,) = errors_for(tmp_path, text)
    assert "chave repetida: 'endpoint_status'" in error


def test_dec_025_utf8_file_is_accepted(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_bytes(MINIMAL_SOURCE.replace("Fonte A", "Segurança Social — Ação").encode("utf-8"))
    assert load_sources(path).sources[0].name == "Segurança Social — Ação"


@pytest.mark.parametrize("encoding", ["utf-16", "latin-1"])
def test_dec_025_other_encodings_are_an_error(tmp_path, encoding):
    path = tmp_path / "sources.yaml"
    path.write_bytes(MINIMAL_SOURCE.replace("Fonte A", "Segurança").encode(encoding))
    with pytest.raises(SourceRegistryError) as exc:
        load_sources(path)
    assert exc.value.errors == (f"ficheiro não está em UTF-8: {path}",)
