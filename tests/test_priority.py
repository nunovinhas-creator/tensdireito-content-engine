"""Prioridade editorial alta/rever/baixa (DEC-063, fase 1).

Os casos vêm do diagnóstico de 2026-10-12: títulos sobre apoios que o score lexical
(limiar 65) deitava fora e um artigo genérico que passava. Estes testes foram escritos
antes da implementação e são o critério de aceitação da fase 1.
"""

from pathlib import Path

import pytest

from tensdireito_content_engine.priority import (
    Priority,
    PriorityTerms,
    Rule,
    classify,
    load_priority_terms,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config" / "apoios.yaml"

# Títulos relevantes da tabela do diagnóstico (proposta de 2026-10-12).
RELEVANT_TITLES = (
    "Prestação Social Única entra em vigor e agrega 13 apoios sociais",
    "Segurança Social paga hoje subsídio de desemprego e RSI",
    "IEFP abre hoje candidaturas a estágios profissionais: saiba quem pode concorrer",
    "Pensões vão aumentar em janeiro: veja quanto",
    "IRS Jovem: o que muda em 2027 com o Orçamento do Estado",
    "Abono de família: pagamento de outubro chega esta semana",
)

# O exemplo irrelevante que passava o limiar: título sem tema e resumo genérico.
PROFESSIONS_TITLE = "“Algumas profissões desaparecerão, outras terão de se reinventar”"
PROFESSIONS_TEXT = (
    "Os trabalhadores terão de se adaptar; novo estudo altera previsões e cria nova "
    "realidade para famílias e cidadãos a partir de 2027."
)

# Casos ambíguos: podem importar, mas o título não nomeia um apoio.
AMBIGUOUS_TITLES = (
    "Agricultores exigem pacote de apoios de 140 milhões",
    "OE2027: Governo entrega proposta de Orçamento do Estado no Parlamento",
    "Conselho de Ministros aprova decreto-lei sobre rendas",
    "Portaria publicada hoje altera regras de contratação",
)

IRRELEVANT_TITLES = (
    "Benfica vence em Braga e reforça liderança",
    "Incêndio em armazém obriga a cortar estrada em Setúbal",
)


@pytest.fixture(scope="module")
def repo_terms() -> PriorityTerms:
    return load_priority_terms(REPO_CONFIG)


@pytest.fixture(scope="module")
def default_terms() -> PriorityTerms:
    return load_priority_terms(Path("/inexistente/apoios.yaml"))


@pytest.mark.parametrize("title", RELEVANT_TITLES)
@pytest.mark.parametrize("terms_name", ["repo_terms", "default_terms"])
def test_relevant_titles_are_high_or_review(title, terms_name, request):
    terms = request.getfixturevalue(terms_name)
    decision = classify(title, "", "T3", terms)
    assert decision.level in (Priority.HIGH, Priority.REVIEW), decision


@pytest.mark.parametrize("title", RELEVANT_TITLES)
def test_no_relevant_title_is_excluded_by_a_lexical_rule(title, repo_terms):
    """Salvaguarda pedida na revisão: nenhuma regra lexical põe um destes em baixa."""
    for tier in ("T1", "T2", "T3", None):
        assert classify(title, "", tier, repo_terms).level is not Priority.LOW


@pytest.mark.parametrize("title", RELEVANT_TITLES)
def test_relevant_titles_from_the_diagnosis_are_high(title, repo_terms):
    decision = classify(title, "", "T3", repo_terms)
    assert decision.level is Priority.HIGH, decision


def test_professions_example_is_not_high(repo_terms, default_terms):
    for terms in (repo_terms, default_terms):
        decision = classify(PROFESSIONS_TITLE, PROFESSIONS_TEXT, "T3", terms)
        assert decision.level is not Priority.HIGH, decision
        assert decision.level is Priority.LOW, decision


@pytest.mark.parametrize("title", AMBIGUOUS_TITLES)
def test_ambiguous_titles_go_to_review(title, repo_terms):
    decision = classify(title, "", "T3", repo_terms)
    assert decision.level is Priority.REVIEW, decision


@pytest.mark.parametrize("title", IRRELEVANT_TITLES)
def test_irrelevant_titles_from_press_are_low(title, repo_terms):
    decision = classify(title, "Texto sem relação com apoios.", "T3", repo_terms)
    assert decision.level is Priority.LOW, decision


@pytest.mark.parametrize("tier", ["T1", "T2"])
@pytest.mark.parametrize("title", IRRELEVANT_TITLES)
def test_official_sources_are_never_low(title, tier, repo_terms):
    decision = classify(title, "", tier, repo_terms)
    assert decision.level is Priority.REVIEW, decision
    assert tier in decision.reason


def test_strong_term_only_in_the_summary_goes_to_review(repo_terms):
    decision = classify(
        "Governo e parceiros reúnem-se amanhã",
        "Em cima da mesa está o aumento do abono de família.",
        "T3",
        repo_terms,
    )
    assert decision.level is Priority.REVIEW
    assert "resumo" in decision.reason


def test_every_decision_has_a_reason(repo_terms):
    titles = (*RELEVANT_TITLES, *AMBIGUOUS_TITLES, *IRRELEVANT_TITLES, PROFESSIONS_TITLE)
    for title in titles:
        decision = classify(title, "", "T3", repo_terms)
        assert decision.reason.strip(), title


def test_reason_names_the_matched_term(repo_terms):
    decision = classify("Abono de família sobe em janeiro", "", "T3", repo_terms)
    assert decision.level is Priority.HIGH
    assert "abono" in decision.reason


@pytest.mark.parametrize(
    ("title", "term"),
    [
        ("Pensões sobem 2,8% em janeiro", "pensao"),
        ("Novos estágios profissionais abrem esta semana", "estagio profissional"),
        ("Apoios sociais chegam a mais famílias", "apoio social"),
    ],
)
def test_portuguese_plurals_match(title, term):
    terms = PriorityTerms(high=(term,), review=())
    assert classify(title, "", "T3", terms).level is Priority.HIGH


def test_whole_words_only():
    terms = PriorityTerms(high=("lar",), review=())
    assert classify("Largo do Rato fechado ao trânsito", "", "T3", terms).level is Priority.LOW


def test_config_section_extends_the_defaults(tmp_path):
    config = tmp_path / "apoios.yaml"
    config.write_text(
        "areas:\n"
        "  teste:\n"
        "    nome: Teste\n"
        "    apoios: [Vale Farmácia]\n"
        "    palavras_chave: [farmácias]\n"
        "prioridade:\n"
        "  alta: [cartão solidário]\n"
        "  rever: [autarquia]\n",
        encoding="utf-8",
    )
    terms = load_priority_terms(config)
    assert classify("Vale Farmácia abre em novembro", "", "T3", terms).level is Priority.HIGH
    assert classify("Cartão solidário chega a Braga", "", "T3", terms).level is Priority.HIGH
    assert classify("Farmácias fecham mais cedo", "", "T3", terms).level is Priority.REVIEW
    assert classify("Autarquia reúne hoje", "", "T3", terms).level is Priority.REVIEW
    # As predefinições continuam activas quando o YAML acrescenta termos.
    assert classify("Abono sobe em janeiro", "", "T3", terms).level is Priority.HIGH


@pytest.mark.parametrize(
    "title",
    [
        "PSI fecha em alta pela terceira sessão",
        "Jovens portugueses emigram mais do que em 2025",
        "Mega operação policial em Lisboa",
    ],
)
def test_aliases_in_parentheses_do_not_make_a_title_high(title, repo_terms):
    assert classify(title, "", "T3", repo_terms).level is not Priority.HIGH


def test_classification_is_deterministic(repo_terms):
    first = [classify(t, "", "T3", repo_terms) for t in RELEVANT_TITLES]
    second = [classify(t, "", "T3", repo_terms) for t in RELEVANT_TITLES]
    assert first == second


@pytest.mark.parametrize(
    "title",
    [
        "Macau transfere 1,76 mil milhões de euros para cobrir défice do Fundo de Pensões",
        "Cabo Verde. Universidade pública com propinas gratuitas",
    ],
)
def test_strong_term_about_another_country_goes_to_review(title, repo_terms):
    decision = classify(title, "", "T3", repo_terms)
    assert decision.level is Priority.REVIEW
    assert decision.rule is Rule.FOREIGN


def test_decisions_carry_the_rule(repo_terms):
    assert classify(RELEVANT_TITLES[0], "", "T3", repo_terms).rule is Rule.HIGH_TITLE
    assert classify(IRRELEVANT_TITLES[0], "", "T1", repo_terms).rule is Rule.OFFICIAL
    assert classify(AMBIGUOUS_TITLES[0], "", "T3", repo_terms).rule is Rule.AMBIGUOUS_TITLE
    assert classify(IRRELEVANT_TITLES[0], "", "T3", repo_terms).rule is Rule.NONE
