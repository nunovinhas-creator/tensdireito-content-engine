"""Fase 2b (DEC-069): news sitemap no pipeline diário e medição da cobertura por método.

Critérios acordados na revisão do PR #68: sobreposição entre métodos medida só nas notícias
do dia; `www.` junta-se ao domínio sem `www.` só quando a mesma fonte declara as duas formas.
"""

import sqlite3
from pathlib import Path

from test_daily import DAY, T0, FakeRss, item

from tensdireito_content_engine import cli
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.domain import EndpointType, RawItem

SM = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS = "http://www.google.com/schemas/sitemap-news/0.9"


class FakeSitemap:
    endpoint_type = EndpointType.NEWS_SITEMAP

    def __init__(self, produce):
        self.produce = produce

    def fetch(self, endpoint, since):
        return self.produce(endpoint.id)


def sitemap_item(endpoint_id, url, title, published="2026-10-09T10:00:00+01:00"):
    date = f"<n:publication_date>{published}</n:publication_date>" if published else ""
    raw = (
        f'<url xmlns="{SM}" xmlns:n="{NEWS}"><loc>{url}</loc><n:news>'
        f"<n:publication><n:name>Jornal</n:name><n:language>pt</n:language></n:publication>"
        f"<n:title>{title}</n:title>{date}</n:news></url>"
    )
    return RawItem(
        url=url,
        title=title,
        raw_content=raw,
        fetched_at=T0,
        source_endpoint_id=endpoint_id,
        external_id=url,
        published_at_raw=published,
    )


def config(tmp_path: Path, jornal_domains: str) -> Path:
    text = f"""
- id: jornal
  name: Jornal
  entity_type: press
  tier: T3
  domains: {jornal_domains}
  registry_status: VALIDATED
  validated_at: "2026-10-01T09:00:00Z"
  validated_by: editor_teste
  endpoints:
    - id: jornal-rss
      endpoint_type: rss
      url: https://jornal.example/feed.xml
      endpoint_status: ACTIVE
      validated_at: "2026-10-01T09:00:00Z"
      validated_by: editor_teste
    - id: jornal-news-sitemap
      endpoint_type: news_sitemap
      url: https://jornal.example/news-sitemap.xml
      endpoint_status: ACTIVE
      validated_at: "2026-10-01T09:00:00Z"
      validated_by: editor_teste
"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources.yaml").write_text(text.lstrip(), encoding="utf-8")
    return tmp_path


def run(monkeypatch, tmp_path, sources, rss_items, sitemap_items):
    rss = FakeRss(lambda _: rss_items)
    sitemap = FakeSitemap(lambda _: sitemap_items)
    monkeypatch.setattr(cli, "default_registry", lambda: CollectorRegistry([rss, sitemap]))
    db = tmp_path / "tde.sqlite3"
    summary = tmp_path / "summary.md"
    summary.write_text("", encoding="utf-8")
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
            str(tmp_path / "reports"),
            "--summary-md",
            str(summary),
        ]
    )
    return code, db, summary.read_text(encoding="utf-8")


def rows(db, sql):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql).fetchall()


def test_same_article_by_rss_and_sitemap_joins_www_when_both_forms_are_declared(
    monkeypatch, tmp_path, capsys
):
    sources = config(tmp_path / "config", "[jornal.example, www.jornal.example]")
    rss = [item("jornal-rss", title="Abono sobe em janeiro", url="https://www.jornal.example/a")]
    sitemap = [sitemap_item("jornal-news-sitemap", "https://jornal.example/a", "Abono sobe")]
    code, db, summary = run(monkeypatch, tmp_path, sources, rss, sitemap)
    capsys.readouterr()
    assert code == 0
    assert rows(db, "SELECT url_key FROM candidate") == [("https://jornal.example/a",)]
    assert sorted(rows(db, "SELECT method FROM candidate_discovery")) == [
        ("news_sitemap",),
        ("rss",),
    ]
    # Mesma notícia do dia pelos dois métodos: nenhum é exclusivo.
    assert "| news_sitemap | 1 | 0 | 1 | 0 | 1 |" in summary
    assert "| rss | 1 | 0 | 1 | 0 | 1 |" in summary


def test_www_is_not_joined_without_both_forms_declared(monkeypatch, tmp_path, capsys):
    sources = config(tmp_path / "config", "[jornal.example]")
    rss = [item("jornal-rss", title="Abono sobe em janeiro", url="https://www.jornal.example/a")]
    sitemap = [sitemap_item("jornal-news-sitemap", "https://jornal.example/a", "Abono sobe")]
    code, db, _ = run(monkeypatch, tmp_path, sources, rss, sitemap)
    capsys.readouterr()
    assert code == 0
    assert rows(db, "SELECT COUNT(*) FROM candidate") == [(2,)]


def test_overlap_is_also_measured_only_on_news_of_the_day(monkeypatch, tmp_path, capsys):
    sources = config(tmp_path / "config", "[jornal.example]")
    rss = [
        item(
            "jornal-rss",
            title="Abono sobe em janeiro",
            url="https://jornal.example/hoje",
            raw="<item><description>Hoje.</description></item>",
        ),
        item(
            "jornal-rss",
            title="Pensões: calendário de pagamentos",
            url="https://jornal.example/so-rss",
            raw="<item><description>Só RSS.</description></item>",
        ),
    ]
    sitemap = [
        sitemap_item("jornal-news-sitemap", "https://jornal.example/hoje", "Abono sobe"),
        sitemap_item(
            "jornal-news-sitemap",
            "https://jornal.example/ontem",
            "IRS: reembolsos",
            published="2026-10-08T10:00:00+01:00",
        ),
    ]
    code, db, summary = run(monkeypatch, tmp_path, sources, rss, sitemap)
    capsys.readouterr()
    assert code == 0
    # news_sitemap: 2 candidatos (1 só dele), mas do dia só 1, partilhado com o RSS.
    assert "| news_sitemap | 2 | 1 | 1 | 0 | 2 |" in summary
    # rss: 2 candidatos do dia, 1 só dele.
    assert "| rss | 2 | 1 | 2 | 1 | 2 |" in summary


def test_sitemap_capture_has_its_date_source_document_and_language(monkeypatch, tmp_path, capsys):
    sources = config(tmp_path / "config", "[jornal.example]")
    sitemap = [sitemap_item("jornal-news-sitemap", "https://jornal.example/a", "Abono sobe")]
    code, db, _ = run(monkeypatch, tmp_path, sources, [], sitemap)
    capsys.readouterr()
    assert code == 0
    assert rows(db, "SELECT published_at_source, state FROM candidate") == [("sitemap", "rascunho")]
    assert rows(
        db,
        "SELECT d.text, d.language FROM candidate c "
        "JOIN source_document d ON d.id = c.representative_document_id",
    ) == [(None, "pt")]


def test_sitemap_entry_without_date_is_not_of_the_day(monkeypatch, tmp_path, capsys):
    sources = config(tmp_path / "config", "[jornal.example]")
    sitemap = [sitemap_item("jornal-news-sitemap", "https://jornal.example/a", "Abono sobe", None)]
    code, db, _ = run(monkeypatch, tmp_path, sources, [], sitemap)
    capsys.readouterr()
    assert code == 0
    # Primeira recolha do endpoint: sem data não conta como do dia (DEC-061).
    assert rows(db, "SELECT published_at_source, state FROM candidate") == [("none", "fora_do_dia")]
