from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.domain import RawItem
from tensdireito_content_engine.normalize import normalize_raw_item
from tensdireito_content_engine.scoring import TopicTerms, load_topic_terms, score_item


def test_initial_score_is_deterministic_and_does_not_claim_verification():
    item = RawItem(
        url="https://example.org",
        title="Nova prestação aumenta para trabalhadores; prazo para pedir apoio",
        raw_content=(
            "<item><description>A nova prestação aumenta e cria direito para trabalhadores. "
            "Deve requerer apoio até 31 de outubro.</description></item>"
        ),
        fetched_at=datetime(2026, 10, 9, tzinfo=UTC),
    )
    normalized = normalize_raw_item(item)

    first = score_item(normalized)

    assert first == score_item(normalized)
    assert first.value == 74
    assert dict(first.components) == {
        "impact": 5,
        "reach": 3,
        "actionability": 5,
        "urgency": 4,
        "novelty": 0,
        "interest": 0,
    }
    assert not hasattr(first, "verification_status")


def test_unrelated_text_scores_below_draft_threshold():
    item = RawItem(
        url="https://example.org",
        title="Nota local",
        raw_content="<item><description>Notas de cultura local.</description></item>",
        fetched_at=datetime(2026, 10, 9, tzinfo=UTC),
    )

    assert score_item(normalize_raw_item(item)).value < 65


APOIOS = Path(__file__).resolve().parents[1] / "config" / "apoios.yaml"


def _item(title: str, description: str):
    return normalize_raw_item(
        RawItem(
            url="https://example.org",
            title=title,
            raw_content=f"<item><description>{description}</description></item>",
            fetched_at=datetime(2026, 10, 9, tzinfo=UTC),
        )
    )


def test_topic_terms_come_from_the_supports_map():
    topics = load_topic_terms(APOIOS)
    assert "abono de familia pre-natal" in topics.named_supports
    assert "ase" in topics.named_supports
    assert "porta 65 jovem" in topics.named_supports
    assert "cuidador informal" in topics.keywords
    assert load_topic_terms(Path("nao-existe.yaml")) == TopicTerms()


def test_named_support_in_title_raises_novelty_and_interest():
    topics = load_topic_terms(APOIOS)
    item = _item(
        "Abono de família: prova escolar decide se a Segurança Social continua a pagar",
        "Jovens com 16 anos têm de fazer prova escolar para manter o abono.",
    )
    base = dict(score_item(item).components)
    themed = dict(score_item(item, topics).components)
    assert base["novelty"] == base["interest"] == 0
    assert themed["novelty"] > 0
    assert themed["interest"] > 0


def test_topic_terms_match_whole_words_only():
    topics = TopicTerms(keywords=("lar",), named_supports=("lar",))
    item = _item("Largo da cidade recebe feira", "Uma feira no largo.")
    assert dict(score_item(item, topics).components)["interest"] == 0
    plural = _item("Lares de idosos com vagas", "Novos lares abrem.")
    assert dict(score_item(plural, topics).components)["interest"] > 0
