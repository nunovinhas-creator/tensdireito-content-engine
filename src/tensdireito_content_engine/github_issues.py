"""Sincronização de rascunhos WhatsApp com issues do GitHub."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tensdireito_content_engine.storage import DraftIssueData, list_unverified_drafts_for_issues

LABEL = "draft-whatsapp"
REFERENCE_PREFIX = "<!-- tensdireito-draft-source: "
REFERENCE_SUFFIX = " -->"


class GitHubIssueError(Exception):
    """Erro explícito ao consultar ou criar issues no GitHub."""


@dataclass(frozen=True, slots=True)
class IssueSyncResult:
    created: tuple[str, ...]
    already_present: int


def sync_draft_issues(db_path: Path) -> IssueSyncResult:
    """Cria uma issue para cada rascunho ainda não verificado sem referência existente."""
    drafts = list_unverified_drafts_for_issues(db_path)
    if not drafts:
        return IssueSyncResult(created=(), already_present=0)
    _ensure_label()
    issues = _gh_json(
        ["issue", "list", "--state", "all", "--limit", "1000", "--json", "number,body"]
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
        result = _gh(
            [
                "issue",
                "create",
                "--title",
                f"[Rascunho WhatsApp] {draft.title}",
                "--body",
                body,
                "--label",
                LABEL,
            ]
        )
        created.append(result.strip())
        issue_bodies.append(body)
    return IssueSyncResult(created=tuple(created), already_present=already_present)


def _ensure_label() -> None:
    labels = _gh_json(["label", "list", "--limit", "1000", "--json", "name"])
    if not isinstance(labels, list) or any(
        not isinstance(label, dict) or not isinstance(label.get("name"), str)
        for label in labels
    ):
        raise GitHubIssueError("a resposta de `gh label list` tem formato inválido")
    if any(label["name"] == LABEL for label in labels):
        return
    _gh(
        [
            "label",
            "create",
            LABEL,
            "--color",
            "1D76DB",
            "--description",
            "Rascunho WhatsApp pendente de revisão editorial",
        ]
    )


def _issue_bodies(issues: Any) -> list[str]:
    if not isinstance(issues, list) or any(
        not isinstance(issue, dict)
        or not isinstance(issue.get("number"), int)
        or issue.get("body") is not None
        and not isinstance(issue.get("body"), str)
        for issue in issues
    ):
        raise GitHubIssueError("a resposta de `gh issue list` tem formato inválido")
    return [issue["body"] or "" for issue in issues]


def _source_reference(source_url: str) -> str:
    return f"{REFERENCE_PREFIX}{source_url}{REFERENCE_SUFFIX}"


def _issue_body(draft: DraftIssueData, reference: str) -> str:
    return (
        f"{draft.message}\n\n"
        "---\n"
        f"**Score de relevância:** {draft.editorial_score:g}/100\n\n"
        f"**Fonte original:** {draft.source_url}\n\n"
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
