import copy
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from tensdireito_content_engine.domain import RawItem
from tensdireito_content_engine.normalize import (
    DeduplicationResult,
    ExactDuplicate,
    NormalizedItem,
    deduplicate_exact,
    fingerprint,
    normalize_raw_item,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def make_item(text: str, *, url: str = "documento-1", title: str = "Título") -> NormalizedItem:
    raw = RawItem(url=url, title=title, raw_content=text, fetched_at=T0)
    return normalize_raw_item(raw)


def test_empty_input():
    result = deduplicate_exact([])
    assert result == DeduplicationResult(representatives=(), duplicates=())


def test_single_item_is_its_own_representative():
    item = make_item("Texto A.")
    result = deduplicate_exact([item])
    assert result.representatives == (item,)
    assert result.duplicates == ()


def test_distinct_hashes_are_all_representatives_in_input_order():
    a, b, c = make_item("Texto A."), make_item("Texto B."), make_item("Texto C.")
    result = deduplicate_exact([b, a, c])
    assert result.representatives == (b, a, c)
    assert result.duplicates == ()


def test_two_items_with_same_hash():
    first = make_item("Mesmo texto.", url="documento-1")
    second = make_item("Mesmo texto.", url="documento-2")
    result = deduplicate_exact([first, second])
    assert result.representatives == (first,)
    assert result.duplicates == (
        ExactDuplicate(item=second, duplicate_of=first, text_hash=fingerprint(first)),
    )
    assert result.representatives[0] is first
    assert result.duplicates[0].item is second
    assert result.duplicates[0].duplicate_of is first


def test_many_items_with_same_hash_point_to_first_occurrence():
    items = [make_item("Mesmo texto.", url=f"documento-{n}") for n in range(4)]
    result = deduplicate_exact(items)
    assert result.representatives == (items[0],)
    assert [d.item for d in result.duplicates] == items[1:]
    assert all(d.duplicate_of is items[0] for d in result.duplicates)
    assert {d.text_hash for d in result.duplicates} == {fingerprint(items[0])}


def test_mixed_unique_and_duplicate_groups():
    a1 = make_item("Texto A.", url="a1")
    b1 = make_item("Texto B.", url="b1")
    a2 = make_item("Texto A.", url="a2")
    c1 = make_item("Texto C.", url="c1")
    b2 = make_item("Texto B.", url="b2")
    a3 = make_item("Texto A.", url="a3")
    result = deduplicate_exact([a1, b1, a2, c1, b2, a3])
    assert result.representatives == (a1, b1, c1)
    assert [(d.item, d.duplicate_of) for d in result.duplicates] == [
        (a2, a1),
        (b2, b1),
        (a3, a1),
    ]


def test_every_input_item_appears_exactly_once_in_result():
    items = [make_item(t, url=f"d{n}") for n, t in enumerate(["X.", "Y.", "X.", "X.", "Z."])]
    result = deduplicate_exact(items)
    out = list(result.representatives) + [d.item for d in result.duplicates]
    assert sorted(map(id, out)) == sorted(map(id, items))


def test_duplicate_detection_uses_normalized_text_only():
    # Textos brutos diferentes com o mesmo texto normalizado (espaços, NFC) são duplicados;
    # título, URL e datas diferentes não impedem a deduplicação.
    a = make_item("Pensão  mínima.\r\n", url="a", title="Um")
    b = RawItem(
        url="b",
        title="Outro",
        raw_content="Pensão mínima.",
        fetched_at=T0 + timedelta(days=1),
        published_at_raw="2026-10-01T10:00:00+01:00",
    )
    b = normalize_raw_item(b)
    result = deduplicate_exact([a, b])
    assert result.representatives == (a,)
    assert result.duplicates[0].item is b


def test_case_and_accents_are_not_merged():
    items = [make_item("Pensão."), make_item("pensão."), make_item("Pensao.")]
    result = deduplicate_exact(items)
    assert result.representatives == tuple(items)
    assert result.duplicates == ()


def test_deterministic_for_same_input():
    items = [make_item(t, url=f"d{n}") for n, t in enumerate(["X.", "Y.", "X.", "Z.", "Y."])]
    assert deduplicate_exact(items) == deduplicate_exact(list(items))
    assert deduplicate_exact(items) == deduplicate_exact(tuple(items))


def test_representative_depends_only_on_input_order():
    first = make_item("Mesmo texto.", url="documento-1")
    second = make_item("Mesmo texto.", url="documento-2")
    assert deduplicate_exact([first, second]).representatives == (first,)
    assert deduplicate_exact([second, first]).representatives == (second,)


def test_input_is_not_mutated():
    items = [make_item(t, url=f"d{n}") for n, t in enumerate(["X.", "Y.", "X."])]
    snapshot = copy.deepcopy(items)
    ids = list(map(id, items))
    deduplicate_exact(items)
    assert items == snapshot
    assert list(map(id, items)) == ids


def test_accepts_any_iterable():
    items = [make_item("X.", url="a"), make_item("X.", url="b")]
    result = deduplicate_exact(item for item in items)
    assert result.representatives == (items[0],)
    assert len(result.duplicates) == 1


def test_rejects_non_normalized_item():
    raw = RawItem(url="a", title="T", raw_content="X.", fetched_at=T0)
    with pytest.raises(TypeError):
        deduplicate_exact([raw])


def test_result_types_are_immutable():
    a, b = make_item("X.", url="a"), make_item("X.", url="b")
    result = deduplicate_exact([a, b])
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.representatives = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.duplicates[0].duplicate_of = b  # type: ignore[misc]


def test_result_has_no_event_or_editorial_fields():
    names = {f.name for f in dataclasses.fields(ExactDuplicate)} | {
        f.name for f in dataclasses.fields(DeduplicationResult)
    }
    assert names == {"item", "duplicate_of", "text_hash", "representatives", "duplicates"}
