import subprocess
import sys

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


def test_unknown_command_exits_with_error():
    with pytest.raises(SystemExit) as exc:
        main(["collect"])
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
