"""Sincronização de rascunhos WhatsApp com issues do GitHub."""

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tensdireito_content_engine.storage import DraftIssueData, list_unverified_drafts_for_issues
from tensdireito_content_engine.topics import TopicMap

LABEL = "draft-whatsapp"
AREA_LABEL_PREFIX = "área: "
AREA_LABEL_COLOR = "0E8A16"
# DEC-058: sem limite prático; o `gh` pagina internamente.
ISSUE_LIST_LIMIT = "1000000"
STALE_COMMENT = "Fechada automaticamente: rascunho com mais de {days} dias (DEC-058)."
REFERENCE_PREFIX = "<!-- tensdireito-draft-source: "
REFERENCE_SUFFIX = " -->"


class GitHubIssueError(Exception):
    """Erro explícito ao consultar ou criar issues no GitHub."""


@dataclass(frozen=True, slots=True)
class IssueSyncResult:
    created: tuple[str, ...]
    already_present: int


@dataclass(frozen=True, slots=True)
class StaleCloseResult:
    closed: tuple[int, ...]


def sync_draft_issues(db_path: Path, topic_map: TopicMap | None = None) -> IssueSyncResult:
    """Cria uma issue para cada rascunho ainda não verificado sem referência existente."""
    drafts = list_unverified_drafts_for_issues(db_path)
    if not drafts:
        return IssueSyncResult(created=(), already_present=0)
    topic_map = topic_map or TopicMap()
    labels = _existing_labels()
    _ensure_label(labels, LABEL, "1D76DB", "Rascunho WhatsApp pendente de revisão editorial")
    issues = _gh_json(
        ["issue", "list", "--state", "all", "--limit", ISSUE_LIST_LIMIT, "--json", "number,body"]
    )
    issue_bodies = _issue_bodies(issues)

    created: list[str] = []
    already_present = 0
    for draft in drafts:
        reference = _source_reference(draft.source_url)
        if any(reference in body for body in issue_bodies):
            already_present += 1
            continue
        body = _issue_body(draft, reference)
        label_args = ["--label", LABEL]
        for area in topic_map.areas_for(f"{draft.title}\n{draft.message}"):
            name = f"{AREA_LABEL_PREFIX}{area.name}"
            _ensure_label(labels, name, AREA_LABEL_COLOR, f"Área temática: {area.name}")
            label_args += ["--label", name]
        result = _gh(
            [
                "issue",
                "create",
                "--title",
                f"[Rascunho WhatsApp] {draft.title}",
                "--body",
                body,
                *label_args,
            ]
        )
        created.append(result.strip())
        issue_bodies.append(body)
    return IssueSyncResult(created=tuple(created), already_present=already_present)


def close_stale_draft_issues(days: int, now: datetime | None = None) -> StaleCloseResult:
    """Fecha como "não planeada" cada issue de rascunho aberta há mais de `days` dias."""
    if days < 1:
        raise ValueError("days tem de ser pelo menos 1")
    limit = (now or datetime.now(UTC)) - timedelta(days=days)
    issues = _gh_json(
        [
            "issue",
            "list",
            "--state",
            "open",
            "--label",
            LABEL,
            "--limit",
            ISSUE_LIST_LIMIT,
            "--json",
            "number,createdAt",
        ]
    )
    if not isinstance(issues, list) or any(
        not isinstance(issue, dict)
        or not isinstance(issue.get("number"), int)
        or not isinstance(issue.get("createdAt"), str)
        for issue in issues
    ):
        raise GitHubIssueError("a resposta de `gh issue list` tem formato inválido")
    closed: list[int] = []
    for issue in sorted(issues, key=lambda item: item["number"]):
        try:
            created = datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise GitHubIssueError("`createdAt` inválido em `gh issue list`") from exc
        if created >= limit:
            continue
        _gh(
            [
                "issue",
                "close",
                str(issue["number"]),
                "--reason",
                "not planned",
                "--comment",
                STALE_COMMENT.format(days=days),
            ]
        )
        closed.append(issue["number"])
    return StaleCloseResult(closed=tuple(closed))


def _existing_labels() -> set[str]:
    labels = _gh_json(["label", "list", "--limit", ISSUE_LIST_LIMIT, "--json", "name"])
    if not isinstance(labels, list) or any(
        not isinstance(label, dict) or not isinstance(label.get("name"), str) for label in labels
    ):
        raise GitHubIssueError("a resposta de `gh label list` tem formato inválido")
    return {label["name"] for label in labels}


def _ensure_label(existing: set[str], name: str, color: str, description: str) -> None:
    if name in existing:
        return
    _gh(["label", "create", name, "--color", color, "--description", description])
    existing.add(name)


def _issue_bodies(issues: Any) -> list[str]:
    if not isinstance(issues, list) or any(
        not isinstance(issue, dict)
        or not isinstance(issue.get("number"), int)
        or issue.get("body") is not None
        and not isinstance(issue.get("body"), str)
        for issue in issues
    ):
        raise GitHubIssueError("a resposta de `gh issue list` tem formato inválido")
    # Edições manuais ou por ferramentas podem envolver os URLs em `código`; a referência
    # compara-se sem crases para não duplicar a issue.
    return [(issue["body"] or "").replace("`", "") for issue in issues]


def _source_reference(source_url: str) -> str:
    return f"{REFERENCE_PREFIX}{source_url}{REFERENCE_SUFFIX}"


def _issue_body(draft: DraftIssueData, reference: str) -> str:
    return (
        f"{draft.message}\n\n"
        "---\n"
        f"**Score de relevância:** {draft.editorial_score:g}/100\n\n"
        f"**Fonte original:** {draft.source_url}\n\n"
        "⚠️ Resumo automático a partir da fonte: confirme os factos antes de publicar.\n\n"
        "Copie o texto para o WhatsApp e feche a issue após publicação.\n\n"
        f"{reference}"
    )


def _gh_json(arguments: list[str]) -> Any:
    output = _gh(arguments).strip()
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise GitHubIssueError(f"`gh {' '.join(arguments)}` devolveu JSON inválido") from exc


def _gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *arguments],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        raise GitHubIssueError(f"não foi possível executar `gh`: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "erro sem detalhe"
        raise GitHubIssueError(f"`gh {' '.join(arguments)}` falhou: {detail}")
    return result.stdout
