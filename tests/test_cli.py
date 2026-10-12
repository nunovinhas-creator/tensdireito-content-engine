import json
import subprocess
import sys
from pathlib import Path

import pytest

from tensdireito_content_engine import __version__
from tensdireito_content_engine.cli import doctor, main


def test_doctor_reports_ok():
    lines = doctor()
    assert lines[0] == f"tde {__version__}"
    assert lines[-1].startswith("status: OK")


def test_doctor_is_deterministic():
    assert doctor() == doctor()


def test_main_doctor_prints_and_exits_zero(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "status: OK" in out


def test_main_without_command_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage: tde" in out
    assert "doctor" in out


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "doctor" in capsys.readouterr().out


def test_publish_whatsapp_prints_eligible_preview(tmp_path, capsys):
    manifest = tmp_path / "whatsapp.json"
    manifest.write_text(
        json.dumps(
            {
                "emoji": "📢",
                "title": "Novo apoio às famílias",
                "key_points": ["Quem pode pedir", "Qual o prazo"],
                "cta": "Consulte os detalhes",
                "url": "https://example.org/direito",
                "editorial_score": 65,
                "verification_status": "verified_official",
                "editorial_status": "approved",
                "is_duplicate": False,
            }
        ),
        encoding="utf-8",
    )

    assert main(["publish", "--target", "whatsapp", "--input", str(manifest)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "publish: PRÉ-VISUALIZAÇÃO — whatsapp",
        "📢 **NOVO APOIO ÀS FAMÍLIAS**",
        "",
        "👉 Quem pode pedir",
        "👉 Qual o prazo",
        "",
        "🔎 **Consulte os detalhes:** https://example.org/direito",
        "",
        "👉 **Tensdireito.com — informação útil para o seu bolso.**",
    ]


def test_publish_whatsapp_rejects_ineligible_item(tmp_path, capsys):
    manifest = tmp_path / "whatsapp.json"
    manifest.write_text(
        json.dumps(
            {
                "emoji": "📢",
                "title": "Novo apoio às famílias",
                "key_points": ["Quem pode pedir", "Qual o prazo"],
                "cta": "Consulte os detalhes",
                "url": "https://example.org/direito",
                "editorial_score": 64,
                "verification_status": "unverified",
                "editorial_status": "approved",
                "is_duplicate": False,
            }
        ),
        encoding="utf-8",
    )

    assert main(["publish", "--target", "whatsapp", "--input", str(manifest)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "publish: NÃO ELEGÍVEL",
        "- item não validado editorialmente ou oficialmente",
    ]


def test_unknown_command_exits_with_error():
    with pytest.raises(SystemExit) as exc:
        main(["comando-inexistente"])
    assert exc.value.code == 2


def test_module_entry_point_runs_doctor():
    result = subprocess.run(
        [sys.executable, "-m", "tensdireito_content_engine.cli", "doctor"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "status: OK" in result.stdout


FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def write_config(tmp_path: Path, text: str) -> Path:
    (tmp_path / "sources.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def test_sources_validate_valid_config(capsys):
    assert main(["--config", str(FIXTURES), "sources", "validate"]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"sources: OK — {FIXTURES / 'sources.yaml'}",
        "fontes: 3",
        "endpoints: 3",
    ]
    assert captured.err == ""


def test_sources_validate_invalid_config_exits_one(tmp_path, capsys):
    config = write_config(tmp_path, "- id: fonte_a\n  name: A\n  entity_type: public_body\n")
    assert main(["--config", str(config), "sources", "validate"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"sources: ERRO — {config / 'sources.yaml'}",
        "- sources[0] (id=fonte_a): campo obrigatório em falta: tier",
    ]


def test_sources_validate_dec_035_active_endpoint_in_candidate_source_exits_one(tmp_path, capsys):
    config = write_config(
        tmp_path,
        "- id: fonte_a\n"
        "  name: A\n"
        "  entity_type: public_body\n"
        "  tier: T1\n"
        "  registry_status: CANDIDATE\n"
        "  endpoints:\n"
        "    - id: fonte_a_feed\n"
        "      endpoint_type: rss\n"
        "      url: https://exemplo.invalid/feed\n"
        "      endpoint_status: ACTIVE\n"
        "      validated_at: '2026-10-01T09:00:00Z'\n"
        "      validated_by: editor_ficticio\n",
    )
    assert main(["--config", str(config), "sources", "validate"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"sources: ERRO — {config / 'sources.yaml'}",
        "- sources[0].endpoints[0] (id=fonte_a_feed): "
        "um endpoint ACTIVE exige fonte VALIDATED (fonte fonte_a: CANDIDATE)",
    ]


def test_sources_validate_missing_file_exits_one(tmp_path, capsys):
    assert main(["--config", str(tmp_path), "sources", "validate"]) == 1
    assert "ficheiro não encontrado" in capsys.readouterr().err


def test_sources_validate_does_not_modify_config(tmp_path):
    text = (FIXTURES / "sources.yaml").read_text(encoding="utf-8")
    config = write_config(tmp_path, text)
    before = sorted((p.name, p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir())
    assert main(["--config", str(config), "sources", "validate"]) == 0
    after = sorted((p.name, p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir())
    assert after == before


def test_sources_validate_is_deterministic(capsys):
    main(["--config", str(FIXTURES), "sources", "validate"])
    first = capsys.readouterr()
    main(["--config", str(FIXTURES), "sources", "validate"])
    assert capsys.readouterr() == first


def test_sources_without_action_exits_with_error():
    with pytest.raises(SystemExit) as exc:
        main(["sources"])
    assert exc.value.code == 2


def test_default_config_dir_is_relative_to_working_directory(tmp_path, monkeypatch, capsys):
    (tmp_path / "config").mkdir()
    write_config(tmp_path / "config", "[]\n")
    monkeypatch.chdir(tmp_path)
    assert main(["sources", "validate"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "sources: OK — config/sources.yaml"


def test_repository_sources_registry_is_valid():
    root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "tensdireito_content_engine.cli", "sources", "validate"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("sources: OK — config/sources.yaml")


def test_sources_validate_invalid_config_exit_code_via_process(tmp_path):
    config = write_config(tmp_path, "- [\n")
    result = subprocess.run(
        [sys.executable, "-m", "tensdireito_content_engine.cli", "--config", str(config)]
        + ["sources", "validate"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "YAML inválido" in result.stderr
