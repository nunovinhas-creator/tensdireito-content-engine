"""Vigia do agendamento do daily (DEC-071): decisão por janela, sem rede."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from tensdireito_content_engine import cli
from tensdireito_content_engine.vigia import (
    COVERED,
    DISPATCH,
    OUTSIDE,
    WAITING,
    RunInfo,
    VigiaError,
    decide,
    parse_runs,
    run_vigia,
    window_start,
)

DAY = datetime(2026, 10, 12, tzinfo=UTC)
WORKFLOWS = Path(__file__).parents[1] / ".github" / "workflows"


def at(hour: int, minute: int = 0, day: datetime = DAY) -> datetime:
    return day.replace(hour=hour, minute=minute)


def run(created: datetime, status="completed", conclusion="success", event="schedule", n=1):
    return RunInfo(id=n, created_at=created, status=status, conclusion=conclusion, event=event)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(7, 0), None),
        (at(8, 6), None),
        (at(8, 7), at(8, 7)),
        (at(12, 37), at(8, 7)),
        (at(13, 7), at(13, 7)),
        (at(22, 37), at(18, 7)),
    ],
)
def test_window_is_the_last_cron_time_already_passed_today(now, expected):
    assert window_start(now) == expected


def test_window_without_any_run_is_dispatched_after_one_hour():
    decision = decide(at(9, 37), [run(at(18, 10, DAY - timedelta(days=1)))])
    assert (decision.action, decision.reason) == (DISPATCH, "janela 08:07 sem run → disparado")


def test_scheduler_gets_one_hour_before_the_vigia_acts():
    assert decide(at(8, 37), []).action == WAITING
    assert decide(at(9, 7), []).action == DISPATCH


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_successful_run_in_the_window_covers_it(event):
    decision = decide(at(11, 37), [run(at(9, 50), event=event)])
    assert decision.action == COVERED
    assert decision.reason == f"janela 08:07 já coberta ({event}, success)"


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "pending", "requested"])
def test_run_in_progress_covers_the_window(status):
    decision = decide(at(9, 37), [run(at(9, 30), status=status, conclusion=None)])
    assert decision.action == COVERED


def test_failed_run_does_not_cover_the_window():
    decision = decide(at(10, 37), [run(at(9, 37), conclusion="failure")])
    assert decision.action == DISPATCH
    assert decision.reason == "janela 08:07 só com runs falhados → disparado"


def test_run_started_up_to_30_minutes_early_counts_for_the_window():
    assert decide(at(14, 37), [run(at(12, 40))]).action == COVERED
    assert decide(at(14, 37), [run(at(12, 30))]).action == DISPATCH


def test_run_of_the_previous_window_does_not_cover_the_next():
    assert decide(at(14, 37), [run(at(9, 0))]).action == DISPATCH


def test_outside_the_windows_nothing_is_dispatched():
    assert decide(at(7, 37), []).action == OUTSIDE
    assert decide(at(23, 0), []).action == OUTSIDE


GH_RUNS = json.dumps(
    [
        {
            "databaseId": 7,
            "createdAt": "2026-10-12T09:44:08Z",
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_dispatch",
        },
        {
            "databaseId": 6,
            "createdAt": "2026-10-11T21:52:17Z",
            "status": "completed",
            "conclusion": "",
            "event": "schedule",
        },
    ]
)


class FakeGh:
    def __init__(self, output: str = GH_RUNS) -> None:
        self.output = output
        self.calls: list[list[str]] = []

    def __call__(self, arguments: list[str]) -> str:
        self.calls.append(arguments)
        return self.output if arguments[:2] == ["run", "list"] else ""


def test_run_vigia_dispatches_the_daily_on_main_when_the_window_is_empty():
    gh = FakeGh()
    decision, lines = run_vigia(now=lambda: at(14, 37), gh=gh)
    assert decision.action == DISPATCH
    assert lines == ["VIGIA: janela 13:07 sem run → disparado"]
    assert gh.calls[0][:6] == ["run", "list", "--workflow", "daily.yml", "--branch", "main"]
    assert gh.calls[1] == ["workflow", "run", "daily.yml", "--ref", "main"]


def test_run_vigia_does_nothing_when_covered_or_in_dry_run():
    gh = FakeGh()
    decision, lines = run_vigia(now=lambda: at(10, 37), gh=gh)
    assert decision.action == COVERED
    assert lines == ["VIGIA: janela 08:07 já coberta (workflow_dispatch, success)"]
    assert len(gh.calls) == 1

    gh = FakeGh()
    _, lines = run_vigia(dry_run=True, now=lambda: at(14, 37), gh=gh)
    assert lines == ["VIGIA: janela 13:07 sem run → seria disparado (--dry-run)"]
    assert len(gh.calls) == 1


def test_empty_conclusion_is_read_as_none():
    runs = parse_runs(GH_RUNS)
    assert runs[1].conclusion is None
    assert runs[0].created_at == datetime(2026, 10, 12, 9, 44, 8, tzinfo=UTC)


@pytest.mark.parametrize("output", ["não é json", "{}", '[{"databaseId": 1}]'])
def test_malformed_gh_output_is_an_error(output):
    with pytest.raises(VigiaError, match="gh run list"):
        parse_runs(output)


def test_cli_reports_gh_errors_as_failure(monkeypatch, capsys):
    def failing(dry_run=False):
        raise VigiaError("`gh run list` falhou: HTTP 403")

    monkeypatch.setattr(cli, "run_vigia", failing)
    assert cli.main(["vigia"]) == 1
    assert capsys.readouterr().err == "VIGIA: ERRO — `gh run list` falhou: HTTP 403\n"


def test_vigia_workflow_runs_only_in_the_hours_it_can_act_and_can_dispatch():
    workflow = yaml.safe_load((WORKFLOWS / "vigia.yml").read_text(encoding="utf-8"))
    triggers = workflow[True]  # `on` é lido como booleano pelo YAML 1.1
    assert triggers["schedule"] == [{"cron": "37 9-12,14-17,19-22 * * *"}]
    assert "workflow_dispatch" in triggers
    assert workflow["jobs"]["vigia"]["permissions"] == {"actions": "write", "contents": "read"}
    daily = yaml.safe_load((WORKFLOWS / "daily.yml").read_text(encoding="utf-8"))
    assert daily[True]["schedule"] == [{"cron": "7 8,13,18 * * *"}]
    assert "workflow_dispatch" in daily[True]
