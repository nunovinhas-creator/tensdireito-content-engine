import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from _fake_http import FEED_URL, HOST, NO_ROBOTS, FakeServer, feed

from tensdireito_content_engine import cli
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.collectors.rss import RssCollector
from tensdireito_content_engine.domain import EndpointType, RawItem
from tensdireito_content_engine.normalize import normalize_published_at

DAY = date(2026, 10, 9)
T0 = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)


def config_dir(tmp_path: Path, *endpoint_ids: str) -> Path:
    lines = []
    for index, endpoint_id in enumerate(endpoint_ids):
        source_id = f"source_{index}"
        lines.extend(
            (
                f"- id: {source_id}",
                f"  name: Fonte {index}",
                "  entity_type: press",
                "  tier: T3",
                f"  domains: [source{index}.example]",
                "  registry_status: VALIDATED",
                '  validated_at: "2026-10-01T09:00:00Z"',
                "  validated_by: editor_teste",
                "  endpoints:",
                f"    - id: {endpoint_id}",
                "      endpoint_type: rss",
                f"      url: https://source{index}.example/feed.xml",
                "      endpoint_status: ACTIVE",
                '      validated_at: "2026-10-01T09:00:00Z"',
                "      validated_by: editor_teste",
            )
        )
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def item(
    endpoint_id: str,
    *,
    raw: str = "<item>Texto exacto</item>",
    published: str | None = "2026-10-09T10:00:00+01:00",
    title: str = "  Notícia   diária ",
    url: str = "https://news.example/story",
) -> RawItem:
    return RawItem(
        url=url,
        title=title,
        raw_content=raw,
        fetched_at=T0,
        source_endpoint_id=endpoint_id,
        published_at_raw=published,
    )


class FakeRss:
    endpoint_type = EndpointType.RSS

    def __init__(self, produce):
        self.produce = produce

    def fetch(self, endpoint, since):
        assert since is None
        return self.produce(endpoint.id)


def invoke_daily(monkeypatch, tmp_path, sources, collector):
    monkeypatch.setattr(cli, "default_registry", lambda: CollectorRegistry([collector]))
    db = tmp_path / "tde.sqlite3"
    report_dir = tmp_path / "reports"
    code = cli.main(
        [
            "--config",
            str(sources),
            "--db",
            str(db),
            "daily",
            "--date",
            DAY.isoformat(),
            "--report-dir",
            str(report_dir),
        ]
    )
    return code, db, report_dir / f"{DAY.isoformat()}.txt"


def test_daily_runs_real_rss_parser_against_local_fixture(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    config_path = sources / "sources.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("source0.example", HOST)
        .replace("https://feed.example.org/feed.xml", FEED_URL),
        encoding="utf-8",
    )
    fixture_path = Path(__file__).parent / "fixtures" / "rss" / "valid.xml"
    server = FakeServer(
        {
            (HOST, "/robots.txt"): NO_ROBOTS,
            (HOST, "/rss.xml"): feed(fixture_path.read_bytes()),
        }
    )
    registry = CollectorRegistry([RssCollector(server.transport(), now=lambda: T0)])
    monkeypatch.setattr(cli, "default_registry", lambda: registry)

    db = tmp_path / "tde.sqlite3"
    report = tmp_path / "reports" / f"{DAY.isoformat()}.txt"
    code = cli.main(
        [
            "--config",
            str(sources),
            "--db",
            str(db),
            "daily",
            "--date",
            DAY.isoformat(),
            "--report-dir",
            str(report.parent),
        ]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "itens obtidos: 3" in output
    assert "notícias selecionadas: 3" in output
    text = report.read_text(encoding="utf-8")
    assert "1. Primeira notícia" in text
    assert "Fonte: Fonte 0" in text
    assert "URL: https://feed.example.org/noticias/1?utm_source=rss#topo" in text
    assert server.paths() == [f"{HOST}/robots.txt", f"{HOST}/rss.xml"]


def test_daily_first_and_repeated_execution_are_idempotent(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    collector = FakeRss(lambda endpoint_id: [item(endpoint_id)])

    code, db, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    first_output = capsys.readouterr().out
    assert code == 0
    assert "itens obtidos: 1" in first_output
    assert "notícias selecionadas: 1" in first_output
    assert "Data: 09/10/2026 10:00" in report.read_text(encoding="utf-8")

    code, _, repeated_report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    second_output = capsys.readouterr().out
    assert code == 0
    assert "itens obtidos: 1" in second_output
    assert "notícias selecionadas: 1" in second_output
    assert repeated_report.read_bytes() == report.read_bytes()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_item").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM whatsapp_draft").fetchone() == (0,)


def test_daily_generates_only_eligible_non_duplicate_drafts(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "feed_a", "feed_b")
    eligible = item(
        "feed_a",
        title="Nova prestação aumenta para trabalhadores; prazo para pedir apoio",
        raw=(
            "<item><description>A nova prestação aumenta e cria direito para trabalhadores. "
            "Deve requerer apoio até 31 de outubro.</description></item>"
        ),
    )
    duplicate = item(
        "feed_b",
        title=eligible.title,
        raw=eligible.raw_content,
    )
    low_score = item(
        "feed_b",
        title="Nota local",
        raw="<item><description>Notas de cultura local.</description></item>",
        url="https://news.example/local",
    )
    collector = FakeRss(
        lambda endpoint_id: [eligible] if endpoint_id == "feed_a" else [duplicate, low_score]
    )

    code, db, _ = invoke_daily(monkeypatch, tmp_path, sources, collector)
    output = capsys.readouterr().out

    assert code == 0
    assert "duplicados na janela: 1" in output
    assert "rascunhos WhatsApp gerados: 1" in output
    with sqlite3.connect(db) as connection:
        drafts = connection.execute(
            "SELECT raw_item_id, editorial_score, verification_status, status, message "
            "FROM whatsapp_draft"
        ).fetchall()
    assert len(drafts) == 1
    assert drafts[0][1:4] == (74.0, "unverified", "pending")
    assert drafts[0][4].startswith("📢 *Nova prestação aumenta")
    assert "Resumo da fonte (por validar)" in drafts[0][4]
    assert "Confirme os factos e o impacto antes de aprovar." in drafts[0][4]

    code, _, _ = invoke_daily(monkeypatch, tmp_path, sources, collector)
    capsys.readouterr()
    assert code == 0
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM whatsapp_draft").fetchone() == (1,)


def test_daily_requires_validated_source_for_drafts(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    collector = FakeRss(
        lambda endpoint_id: [
            item(
                endpoint_id,
                title="Nova prestação aumenta para trabalhadores; prazo para pedir apoio",
                raw=(
                    "<item><description>A nova prestação aumenta e cria direito para "
                    "trabalhadores. Deve requerer apoio até 31 de outubro.</description></item>"
                ),
            )
        ]
    )
    monkeypatch.setattr(cli, "default_registry", lambda: CollectorRegistry([collector]))
    db = tmp_path / "tde.sqlite3"
    import tensdireito_content_engine.daily as daily_pipeline

    original_collect = daily_pipeline.run_collect

    def collect_then_unvalidate(*args, **kwargs):
        result = original_collect(*args, **kwargs)
        with sqlite3.connect(db) as connection:
            connection.execute(
                "UPDATE source_registry SET registry_status = 'candidate'"
            )
        return result

    monkeypatch.setattr(daily_pipeline, "run_collect", collect_then_unvalidate)
    report_dir = tmp_path / "reports"
    assert cli.main(
        [
            "--config",
            str(sources),
            "--db",
            str(db),
            "daily",
            "--date",
            DAY.isoformat(),
            "--report-dir",
            str(report_dir),
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "rascunhos WhatsApp gerados: 0" in output
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM whatsapp_draft").fetchone() == (0,)


def test_repeated_item_in_feed_is_saved_once_and_reported_once(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    collector = FakeRss(lambda endpoint_id: [item(endpoint_id), item(endpoint_id)])

    code, db, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    output = capsys.readouterr().out
    assert code == 0
    assert "itens obtidos: 2" in output
    assert "notícias selecionadas: 1" in output
    assert "1 normalizadas; 0 duplicadas" in report.read_text(encoding="utf-8")
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_item").fetchone() == (1,)


def test_same_article_from_two_sources_is_deduplicated(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "feed_a", "feed_b")
    collector = FakeRss(lambda endpoint_id: [item(endpoint_id)])

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    output = capsys.readouterr().out
    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert "duplicados na janela: 1" in output
    assert "2 normalizadas; 1 duplicadas" in text
    assert text.count("1. Notícia diária") == 1


def test_partial_source_failure_keeps_successful_items(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "feed_a", "feed_b")

    def produce(endpoint_id):
        if endpoint_id == "feed_b":
            raise OSError("feed indisponível")
        return [item(endpoint_id)]

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, FakeRss(produce))
    output = capsys.readouterr()
    assert code == 2
    assert "fontes consultadas: 2" in output.out
    assert "notícias selecionadas: 1" in output.out
    assert "feed indisponível" in output.err
    assert "1. Notícia diária" in report.read_text(encoding="utf-8")


def test_all_source_failures_still_write_report_and_return_error(
    monkeypatch, tmp_path, capsys
):
    sources = config_dir(tmp_path / "config", "feed_a", "feed_b")

    def fail(_):
        raise OSError("feed indisponível")

    collector = FakeRss(fail)

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    output = capsys.readouterr()

    assert code == 1
    assert "fontes consultadas: 2" in output.out
    assert "notícias selecionadas: 0" in output.out
    assert output.err.count("feed indisponível") == 2
    assert "Não foram encontradas notícias na janela diária." in report.read_text(
        encoding="utf-8"
    )


def test_empty_feed_writes_a_zero_news_report(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, FakeRss(lambda _: []))
    output = capsys.readouterr().out
    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert "itens obtidos: 0" in output
    assert "notícias selecionadas: 0" in output
    assert "Não foram encontradas notícias na janela diária." in text


def test_disabled_endpoint_is_not_collected(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    config_path = sources / "sources.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "endpoint_status: ACTIVE", "endpoint_status: VALIDATED"
        ),
        encoding="utf-8",
    )

    code, _, report = invoke_daily(
        monkeypatch,
        tmp_path,
        sources,
        FakeRss(lambda _: pytest.fail("non-active endpoint was collected")),
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "fontes consultadas: 0" in output
    assert "itens obtidos: 0" in output
    assert "notícias selecionadas: 0" in output
    assert "Não foram encontradas notícias na janela diária." in report.read_text(
        encoding="utf-8"
    )


def test_zero_items_in_requested_publication_window(monkeypatch, tmp_path, capsys):
    sources = config_dir(tmp_path / "config", "news_feed")
    collector = FakeRss(
        lambda endpoint_id: [item(endpoint_id, published="2026-10-08T12:00:00Z")]
    )

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    output = capsys.readouterr().out
    assert code == 0
    assert "notícias selecionadas: 0" in output
    assert "0 normalizadas; 0 duplicadas" in report.read_text(encoding="utf-8")


def test_unrecognized_publication_date_uses_collection_day_without_inventing_date(
    monkeypatch, tmp_path, capsys
):
    sources = config_dir(tmp_path / "config", "news_feed")
    collector = FakeRss(
        lambda endpoint_id: [
            item(endpoint_id, published="Fri, 09 Oct 2026 09:00:00 GMT")
        ]
    )

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    capsys.readouterr()
    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert normalize_published_at("Fri, 09 Oct 2026 09:00:00 GMT") is None
    assert "1. Notícia diária" in text
    assert "Data: não indicada" in text

@pytest.mark.parametrize("published", [None, "not-a-date"])
def test_missing_or_invalid_publication_date_uses_collection_day_without_inventing_date(
    monkeypatch, tmp_path, capsys, published
):
    sources = config_dir(tmp_path / "config", "news_feed")
    collector = FakeRss(
        lambda endpoint_id: [item(endpoint_id, published=published)]
    )

    code, _, report = invoke_daily(monkeypatch, tmp_path, sources, collector)
    capsys.readouterr()
    text = report.read_text(encoding="utf-8")

    assert code == 0
    assert "1. Notícia diária" in text
    assert "Data: não indicada" in text
