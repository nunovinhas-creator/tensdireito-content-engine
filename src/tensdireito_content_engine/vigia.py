"""Vigia do agendamento do daily (DEC-071).

O agendador do GitHub atrasa ou salta execuções (`schedule`): desde o cron `7 8,13,18`
houve uma só, com quase 4 h de atraso. A vigia corre de hora a hora nas horas a seguir a
cada janela e, se a janela ainda não tem um run do daily no `main` bem-sucedido ou em
curso, dispara-o (`workflow_dispatch`). O agendador continua a ser a fonte principal: a
vigia espera `GRACE` depois do início da janela antes de actuar.

A decisão (`decide`) é pura e testada sem rede; `run_vigia` usa o `gh` para ler os runs e
disparar o workflow.
"""

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

WORKFLOW = "daily.yml"
BRANCH = "main"
SLOTS = (time(8, 7), time(13, 7), time(18, 7))  # o cron do daily, em UTC
GRACE = timedelta(hours=1)  # tempo dado ao agendador antes de a vigia actuar
EARLY = timedelta(minutes=30)  # um run lançado até 30 min antes da janela conta para ela
LAST_ACTION = time(23, 0)  # depois disto, a janela das 18:07 já não é disparada
ACTIVE_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})
RUN_LIST_LIMIT = "30"

DISPATCH = "disparar"
COVERED = "coberta"
WAITING = "à espera"
OUTSIDE = "fora de janela"


class VigiaError(Exception):
    """Falha ao consultar ou disparar workflows pelo `gh`."""


@dataclass(frozen=True, slots=True)
class RunInfo:
    id: int
    created_at: datetime
    status: str
    conclusion: str | None
    event: str


@dataclass(frozen=True, slots=True)
class Decision:
    action: str  # DISPATCH | COVERED | WAITING | OUTSIDE
    window: datetime | None
    reason: str
    run: RunInfo | None = None


def window_start(now: datetime) -> datetime | None:
    """Início da janela em curso (a última hora do cron já passada hoje), ou `None`."""
    today = now.astimezone(UTC).date()
    starts = [datetime.combine(today, slot, tzinfo=UTC) for slot in SLOTS]
    passed = [start for start in starts if start <= now]
    return passed[-1] if passed else None


def decide(now: datetime, runs: Sequence[RunInfo]) -> Decision:
    """Disparar o daily ou não, na janela em curso."""
    start = window_start(now)
    if start is None or now.astimezone(UTC).time() >= LAST_ACTION:
        return Decision(OUTSIDE, start, "fora das janelas do daily")
    label = start.strftime("%H:%M")
    in_window = [run for run in runs if run.created_at >= start - EARLY]
    for run in sorted(in_window, key=lambda item: item.created_at):
        if run.conclusion == "success" or run.status in ACTIVE_STATUSES:
            state = run.conclusion or run.status
            return Decision(
                COVERED, start, f"janela {label} já coberta ({run.event}, {state})", run
            )
    if now < start + GRACE:
        return Decision(WAITING, start, f"janela {label} sem run; o agendador ainda tem tempo")
    failed = [run for run in in_window if run.conclusion not in (None, "success")]
    detail = "só com runs falhados" if failed else "sem run"
    return Decision(DISPATCH, start, f"janela {label} {detail} → disparado")


Gh = Callable[[list[str]], str]


def run_vigia(
    dry_run: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    gh: Gh | None = None,
) -> tuple[Decision, list[str]]:
    """Lê os runs do daily no `main`, decide e, se for preciso, dispara o workflow."""
    call = gh or _gh
    runs = parse_runs(
        call(
            [
                "run",
                "list",
                "--workflow",
                WORKFLOW,
                "--branch",
                BRANCH,
                "--limit",
                RUN_LIST_LIMIT,
                "--json",
                "databaseId,createdAt,status,conclusion,event",
            ]
        )
    )
    decision = decide(now(), runs)
    reason = decision.reason
    if decision.action == DISPATCH:
        if dry_run:
            reason = reason.replace("→ disparado", "→ seria disparado (--dry-run)")
        else:
            call(["workflow", "run", WORKFLOW, "--ref", BRANCH])
    return decision, [f"VIGIA: {reason}"]


def parse_runs(output: str) -> list[RunInfo]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise VigiaError("`gh run list` devolveu JSON inválido") from exc
    if not isinstance(data, list):
        raise VigiaError("a resposta de `gh run list` tem formato inválido")
    runs: list[RunInfo] = []
    for item in data:
        try:
            runs.append(
                RunInfo(
                    id=int(item["databaseId"]),
                    created_at=datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00")),
                    status=str(item["status"]),
                    conclusion=item.get("conclusion") or None,
                    event=str(item["event"]),
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise VigiaError("a resposta de `gh run list` tem formato inválido") from exc
    return runs


def _gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(["gh", *arguments], capture_output=True, check=False, text=True)
    except OSError as exc:
        raise VigiaError(f"não foi possível executar `gh`: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "erro sem detalhe"
        raise VigiaError(f"`gh {' '.join(arguments)}` falhou: {detail}")
    return result.stdout
