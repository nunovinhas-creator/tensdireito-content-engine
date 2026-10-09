import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine import cli
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.domain import EndpointType, RawItem

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)


def write_sources(config_dir: Path, *endpoint_ids: str) -> Path:
    entries = []
    for index, endpoint_id in enumerate(endpoint_ids):
        entries.extend(
            (
                f"- id: source_{index}",
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
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "sources.yaml"
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return config_dir


class FakeRss:
    endpoint_type = EndpointType.RSS

    def __init__(self, *, fail_endpoint: str | None = None) -> None:
        self.fail_endpoint = fail_endpoint

    def fetch(self, endpoint, since):
        assert since is None
        if endpoint.id == self.fail_endpoint:
            raise OSError("feed indisponível")
        return [
            RawItem(
                url=f"https://news.example/{endpoint.id}",
                title=f"Notícia {endpoint.id}",
                raw_content=f"<item>Conteúdo de {endpoint.id}.</item>",
                fetched_at=NOW,
                source_endpoint_id=endpoint.id,
            )
        ]


def invoke_ingest(monkeypatch, config_dir: Path, db_path: Path, collector: FakeRss) -> int:
    monkeypatch.setattr(cli, "default_registry", lambda: CollectorRegistry([collector]))
    return cli.main(["--config", str(config_dir), "--db", str(db_path), "ingest"])


def test_ingest_repeated_execution_is_idempotent(monkeypatch, tmp_path, capsys):
    config_dir = write_sources(tmp_path / "config", "feed_a")
    db_path = tmp_path / "tde.sqlite3"
    assert cli.main(["--db", str(db_path), "init"]) == 0
    capsys.readouterr()

    for _ in range(2):
        assert invoke_ingest(monkeypatch, config_dir, db_path, FakeRss()) == 0
        output = capsys.readouterr().out
        assert "sources sync: OK" in output
        assert "collect: OK" in output
        assert "normalize: OK" in output
        assert "ingest: OK" in output

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_item").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM source_document").fetchone() == (1,)


def test_ingest_normalizes_successful_items_after_partial_collection(monkeypatch, tmp_path, capsys):
    config_dir = write_sources(tmp_path / "config", "feed_ok", "feed_fails")
    db_path = tmp_path / "tde.sqlite3"
    assert cli.main(["--db", str(db_path), "init"]) == 0
    capsys.readouterr()

    assert invoke_ingest(monkeypatch, config_dir, db_path, FakeRss(fail_endpoint="feed_fails")) == 2
    captured = capsys.readouterr()
    assert "collect: PARCIAL" in captured.out
    assert "normalize: OK" in captured.out
    assert "ingest: PARCIAL" in captured.out
    assert "feed_fails: o collector falhou: OSError: feed indisponível" in captured.err

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_item").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM source_document").fetchone() == (1,)


def test_ingest_normalizes_persisted_items_after_total_collection_failure(
    monkeypatch, tmp_path, capsys
):
    config_dir = write_sources(tmp_path / "config", "feed_fails")
    db_path = tmp_path / "tde.sqlite3"
    assert cli.main(["--db", str(db_path), "init"]) == 0
    capsys.readouterr()

    assert invoke_ingest(monkeypatch, config_dir, db_path, FakeRss(fail_endpoint="feed_fails")) == 1
    captured = capsys.readouterr()
    assert "collect: ERRO" in captured.out
    assert "normalize: OK" in captured.out
    assert "ingest: ERRO" in captured.out
    assert "feed_fails: o collector falhou: OSError: feed indisponível" in captured.err


def test_ingest_stops_when_sources_sync_fails(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text("- [\n", encoding="utf-8")
    db_path = tmp_path / "tde.sqlite3"

    def unexpected_step(*args, **kwargs):
        raise AssertionError("collect/normalize não devem executar")

    monkeypatch.setattr(cli, "collect", unexpected_step)
    monkeypatch.setattr(cli, "normalize", unexpected_step)

    assert invoke_ingest(monkeypatch, config_dir, db_path, FakeRss()) == 1
    captured = capsys.readouterr()
    assert "sources sync: ERRO" in captured.err
    assert "ingest: ERRO — sources sync falhou" in captured.err
    assert not db_path.exists()
