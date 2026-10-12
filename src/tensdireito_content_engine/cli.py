"""Interface de linha de comandos `tde`.

Usa `argparse` (biblioteca padrão), conforme TECHNICAL_SPEC.md §1, para não
introduzir dependências externas.
"""

import argparse
import json
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tensdireito_content_engine import __version__
from tensdireito_content_engine.ai_draft import write_whatsapp
from tensdireito_content_engine.collect import CollectError, CollectResult, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry, default_registry
from tensdireito_content_engine.config import DEFAULT_CONFIG_DIR, sources_path
from tensdireito_content_engine.daily import (
    DECISION_DRAFT,
    DEFAULT_REPORT_DIR,
    DailyArticle,
    DailyResult,
    run_daily,
)
from tensdireito_content_engine.domain.enums import EditorialStatus, VerificationStatus
from tensdireito_content_engine.github_issues import (
    GitHubIssueError,
    close_stale_draft_issues,
    sync_draft_issues,
)
from tensdireito_content_engine.llm import LLMError, load_provider
from tensdireito_content_engine.normalize_command import run_normalize
from tensdireito_content_engine.priority import Priority, Rule
from tensdireito_content_engine.publish.whatsapp import (
    WhatsAppMessage,
    check_whatsapp_eligibility,
    format_whatsapp_message,
)
from tensdireito_content_engine.sources import SourceRegistryError, load_sources
from tensdireito_content_engine.storage import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    SourceSyncError,
    StorageError,
    approve_draft,
    export_approved_drafts,
    init_database,
    list_drafts,
    prune_raw_items,
    resolve_db_path,
    sync_sources,
)
from tensdireito_content_engine.topics import TOPICS_FILENAME, load_topic_map
from tensdireito_content_engine.vigia import VigiaError, run_vigia

PROG = "tde"


def doctor() -> list[str]:
    """Diagnóstico determinístico da fundação da aplicação.

    Não acede à rede, a serviços externos, a variáveis de ambiente nem a base de dados.
    """
    return [
        f"{PROG} {__version__}",
        f"python {platform.python_version()}",
        "package: tensdireito_content_engine",
        "status: OK — fundação da aplicação funcional",
    ]


def sources_validate(path: Path) -> tuple[bool, list[str]]:
    """Valida o registo de fontes (SOURCES.md §4).

    Local e determinista: só lê o ficheiro; não acede à rede nem escreve.
    """
    try:
        loaded = load_sources(path)
    except SourceRegistryError as exc:
        return False, [f"sources: ERRO — {path}", *(f"- {error}" for error in exc.errors)]
    return True, [
        f"sources: OK — {path}",
        f"fontes: {len(loaded.sources)}",
        f"endpoints: {len(loaded.endpoints)}",
    ]


def init(path: Path) -> tuple[bool, list[str]]:
    """Cria a base de dados e aplica as migrações pendentes (ROADMAP.md M2.6).

    Escreve só o esquema; não cria registos de negócio nem acede à rede.
    """
    try:
        result = init_database(path)
    except StorageError as exc:
        return False, [f"init: ERRO — {path}", f"- {exc}"]
    applied = ", ".join(result.applied) if result.applied else "nenhuma"
    return True, [f"init: OK — {result.path}", f"migrações aplicadas: {applied}"]


def sources_sync(config_path: Path, db_path: Path) -> tuple[bool, list[str]]:
    """Sincroniza o registo de fontes validado com SQLite (ROADMAP.md M2.7).

    Unidireccional YAML → SQLite, numa transacção única; não cria a base de dados nem
    aplica migrações e não acede à rede. Um YAML inválido não toca na base de dados.
    """
    try:
        loaded = load_sources(config_path)
    except SourceRegistryError as exc:
        return False, [
            f"sources sync: ERRO — {config_path}",
            *(f"- {error}" for error in exc.errors),
        ]
    try:
        result = sync_sources(db_path, loaded.sources, loaded.endpoints)
    except SourceSyncError as exc:
        return False, [f"sources sync: ERRO — {db_path}", *(f"- {error}" for error in exc.errors)]
    except StorageError as exc:
        return False, [f"sources sync: ERRO — {db_path}", f"- {exc}"]
    counts = result.total
    return True, [
        f"sources sync: OK — {result.path}",
        f"inseridos: {counts.inserted}",
        f"actualizados: {counts.updated}",
        f"inalterados: {counts.unchanged}",
        f"removidos: {counts.removed}",
    ]


def collect(
    db_path: Path, registry: CollectorRegistry, source_id: str | None
) -> tuple[int, list[str], list[str]]:
    """Recolha local dos endpoints `ACTIVE` do espelho SQLite (ROADMAP.md M2.8; DEC-031).

    Devolve o código de saída e as linhas de stdout e de stderr. Não lê
    `config/sources.yaml`, não cria a base de dados nem aplica migrações.
    """
    try:
        result = run_collect(db_path, registry, source_id)
    except (StorageError, CollectError) as exc:
        return 1, [], [f"collect: ERRO — {db_path}", f"- {exc}"]
    label, code = {"success": ("OK", 0), "partial": ("PARCIAL", 2), "failed": ("ERRO", 1)}[
        result.status
    ]
    out = [
        f"collect: {label} — {result.path}",
        f"run: {result.run_id}",
        f"endpoints: {len(result.endpoints)}",
        f"com sucesso: {result.succeeded}",
        f"com falha: {result.failed}",
        f"itens novos: {result.new}",
        f"itens existentes: {result.existing}",
    ]
    err = [f"- {outcome.id}: {outcome.error}" for outcome in result.endpoints if outcome.error]
    return code, out, err


def normalize(db_path: Path) -> tuple[int, list[str], list[str]]:
    """Normaliza os `raw_item` pendentes em `source_document` (ROADMAP.md M2.11; DEC-041).

    Devolve o código de saída e as linhas de stdout e de stderr. Não lê
    `config/sources.yaml`, não acede à rede, não cria a base de dados nem aplica migrações.
    """
    try:
        result = run_normalize(db_path)
    except StorageError as exc:
        return 1, [], [f"normalize: ERRO — {db_path}", f"- {exc}"]
    label, code = {"success": ("OK", 0), "partial": ("PARCIAL", 2), "failed": ("ERRO", 1)}[
        result.status
    ]
    totals = result.stats()["totals"]
    assert isinstance(totals, dict)
    out = [
        f"normalize: {label} — {result.path}",
        f"run: {result.run_id}",
        f"pendentes: {totals['pending']}",
        f"normalizados: {totals['normalized']}",
        f"duplicados: {totals['duplicates']}",
        f"sem texto: {totals['without_text']}",
        f"não suportados: {totals['unsupported']}",
        f"com falha: {totals['failed']}",
    ]
    err = [
        f"- raw_item {outcome.raw_item_id}: {outcome.reason}"
        for outcome in result.items
        if outcome.result == "failed"
    ]
    return code, out, err


def ingest(
    db_path: Path, config_dir: Path, registry: CollectorRegistry
) -> tuple[int, list[str], list[str]]:
    """Sincroniza fontes, recolhe e normaliza, sem inicializar a base de dados."""
    synced, sync_lines = sources_sync(sources_path(config_dir), db_path)
    if not synced:
        return 1, [], [*sync_lines, "ingest: ERRO — sources sync falhou"]

    out = [*sync_lines]
    errors: list[str] = []
    collect_code, collect_out, collect_err = collect(db_path, registry, None)
    out.extend(collect_out)
    errors.extend(collect_err)

    normalize_code, normalize_out, normalize_err = normalize(db_path)
    out.extend(normalize_out)
    errors.extend(normalize_err)

    if 1 in (collect_code, normalize_code):
        code, label = 1, "ERRO"
    elif 2 in (collect_code, normalize_code):
        code, label = 2, "PARCIAL"
    else:
        code, label = 0, "OK"
    out.append(f"ingest: {label}")
    return code, out, errors


def daily(
    db_path: Path,
    config_dir: Path,
    report_dir: Path,
    registry: CollectorRegistry,
    day: date | None,
    summary_md: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, list[str], list[str]]:
    """Executa o pipeline diário e traduz o resultado para a CLI."""
    try:
        result = run_daily(
            db_path,
            sources_path(config_dir),
            report_dir,
            registry,
            day=day,
            writer=load_provider(config_dir, environ or {}),
        )
        if summary_md is not None:
            with Path(summary_md).open("a", encoding="utf-8") as handle:
                handle.write(daily_summary_markdown(result))
    except (StorageError, CollectError, SourceRegistryError, OSError, ValueError) as exc:
        return 1, [], [f"daily: ERRO — {exc}"]
    return _daily_lines(result)


def daily_summary_markdown(result: DailyResult) -> str:
    """Resumo Markdown do run para o `$GITHUB_STEP_SUMMARY` (DEC-058)."""
    outcomes = sorted(result.collection.endpoints, key=lambda outcome: outcome.id)
    failed = [outcome for outcome in outcomes if outcome.error]
    lines = [
        f"## Pipeline diário — {result.day.isoformat()}",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Fontes consultadas | {len(outcomes)} ({len(failed)} com falha) |",
        f"| Itens obtidos | {result.collection.new + result.collection.existing} |",
        f"| Notícias do dia | {len(result.articles)} |",
        f"| Duplicados | {result.duplicates} |",
        f"| Rascunhos novos | {result.drafts_created} |",
        f"| Redigidos por IA | {result.ai_drafts} |",
        "",
        *_funnel_markdown(result),
        *_candidates_markdown(result),
    ]
    if failed:
        lines += ["### Fontes com falha", "", "| Endpoint | Erro |", "|---|---|"]
        lines += [f"| `{o.id}` | {_md_cell(o.error or '')} |" for o in failed]
        lines.append("")
    noted = [outcome for outcome in outcomes if outcome.notes]
    if noted:
        # DEC-070: o que o transporte fez além do pedido simples, por endpoint.
        lines += [
            "### Limitações, novas tentativas e redirects",
            "",
            "| Endpoint | Ocorrência |",
            "|---|---|",
        ]
        lines += [f"| `{o.id}` | {_md_cell('; '.join(o.notes))} |" for o in noted]
        lines.append("")
    lines += [
        "<details><summary>Itens por fonte</summary>",
        "",
        "| Endpoint | Novos | Já existentes | Estado |",
        "|---|---:|---:|---|",
    ]
    lines += [
        f"| `{o.id}` | {o.new} | {o.existing} | {'falha' if o.error else 'ok'} |" for o in outcomes
    ]
    lines += ["", "</details>", ""]
    return "\n".join(lines) + "\n"


# DEC-063: quantos itens da prioridade `rever` e da amostra de `baixa` aparecem no resumo.
SUMMARY_REVIEW_ROWS = 30
SUMMARY_LOW_SAMPLE = 10
AUDIT_LOW_LINES = 5
AUDIT_REVIEW_LINES = 3


def _funnel_markdown(result: DailyResult) -> list[str]:
    """Funil por prioridade e decisões, com listas para auditoria (DEC-063)."""
    counts = result.priority_counts()
    high = result.by_priority(Priority.HIGH)
    review = result.by_priority(Priority.REVIEW)
    low = result.by_priority(Priority.LOW)
    high_decisions: dict[str, int] = {}
    for article in high:
        key = "mesmo tema" if article.decision.startswith("mesmo tema") else article.decision
        high_decisions[key] = high_decisions.get(key, 0) + 1
    lines = [
        "### Funil do dia",
        "",
        "| Fase | Itens |",
        "|---|---:|",
        f"| Notícias do dia, sem duplicados | {len(result.articles)} |",
        f"| Prioridade alta | {counts[Priority.HIGH.value]} |",
    ]
    lines += [f"| ↳ {_md_cell(name)} | {n} |" for name, n in sorted(high_decisions.items())]
    lines.append(f"| Prioridade rever (aguarda classificação) | {counts[Priority.REVIEW.value]} |")
    by_rule: dict[str, int] = {}
    for article in review:
        by_rule[article.priority_rule] = by_rule.get(article.priority_rule, 0) + 1
    lines += [f"| ↳ {_md_cell(rule)} | {n} |" for rule, n in sorted(by_rule.items())]
    lines += [
        f"| Prioridade baixa (arquivada) | {counts[Priority.LOW.value]} |",
        f"| Rascunhos novos nesta execução | {result.drafts_created} |",
        "",
    ]
    not_drafted = [a for a in high if a.decision != DECISION_DRAFT]
    if not_drafted:
        lines += _article_table(
            f"Prioridade alta sem rascunho ({len(not_drafted)})",
            not_drafted,
            "Decisão",
            lambda a: a.decision,
        )
    if review:
        shown = _review_first(review)[:SUMMARY_REVIEW_ROWS]
        lines += _article_table(
            f"Prioridade rever ({len(shown)} de {len(review)})",
            shown,
            "Motivo",
            lambda a: a.priority_reason,
        )
    if low:
        sample = _spread_sample(low, SUMMARY_LOW_SAMPLE)
        lines += _article_table(
            f"Amostra de baixa prioridade para auditoria ({len(sample)} de {len(low)})",
            sample,
            "Motivo",
            lambda a: a.priority_reason,
        )
    return lines


def _candidates_markdown(result: DailyResult) -> list[str]:
    """Registo de candidatos e cobertura por método de descoberta (fase 2a, DEC-068)."""
    stats = result.candidate_stats
    if stats is None:
        return []
    lines = [
        "### Registo de candidatos",
        "",
        "| Medida | Valor |",
        "|---|---:|",
        f"| Capturas registadas neste run | {stats.observations} |",
        f"| Candidatos (notícias) | {stats.candidates} |",
        f"| Candidatos novos | {stats.new_candidates} |",
        f"| Transições de estado | {stats.transitions} |",
        f"| Capturas sem chave de URL | {result.candidates_without_key} |",
        f"| Documentos (`tde normalize`) | {_md_cell(result.normalize_status or '—')} |",
        "",
    ]
    if stats.by_state:
        lines += ["| Estado | Candidatos |", "|---|---:|"]
        lines += [f"| {state} | {n} |" for state, n in stats.by_state.items()]
        lines.append("")
    if stats.by_method:
        lines += [
            "| Método | Candidatos | Só por este método | Do dia | Do dia, só por este método "
            "| Descobertas novas |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        lines += [
            f"| {method} | {m.candidates} | {m.exclusive} | {m.today_candidates} "
            f"| {m.today_exclusive} | {m.new_discoveries} |"
            for method, m in stats.by_method.items()
        ]
        lines.append("")
    return lines


def _article_table(title, articles, column, value) -> list[str]:
    lines = [
        f"<details><summary>{title}</summary>",
        "",
        f"| Título | Fonte | {column} |",
        "|---|---|---|",
    ]
    lines += [
        f"| [{_md_cell(a.title)}]({a.url}) | {_md_cell(a.source_name)} | {_md_cell(value(a))} |"
        for a in articles
    ]
    return [*lines, "", "</details>", ""]


def _review_first(articles: Sequence[DailyArticle]) -> list[DailyArticle]:
    """Ordem de leitura de `rever`: oficiais com termo forte, imprensa, restantes oficiais.

    Os oficiais sem termo forte são centenas (sobretudo o DRE, 2.ª série) e ficam no fim.
    """
    order = {Rule.OFFICIAL_SUMMARY.value: 0, Rule.OFFICIAL.value: 2}
    return sorted(articles, key=lambda a: order.get(a.priority_rule, 1))


def _spread_sample(articles: Sequence[DailyArticle], k: int) -> tuple[DailyArticle, ...]:
    """Amostra determinística espalhada pela lista (início, meio e fim)."""
    if len(articles) <= k:
        return tuple(articles)
    step = (len(articles) - 1) / (k - 1)
    return tuple(articles[round(index * step)] for index in range(k))


def _md_cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def drafts_list(db_path: Path) -> tuple[bool, list[str]]:
    """Mostra a fila persistente de rascunhos pendentes."""
    try:
        drafts = list_drafts(db_path)
    except StorageError as exc:
        return False, [f"drafts: ERRO — {exc}"]
    lines = [f"rascunhos pendentes: {len(drafts)}"]
    for draft in drafts:
        lines.extend(
            (
                f"[{draft.id}] score={draft.editorial_score:g} "
                f"verificação={draft.verification_status.value} estado={draft.status}",
                draft.message,
                "",
            )
        )
    return True, lines


def drafts_sync_issues(db_path: Path, config_dir: Path) -> tuple[bool, list[str]]:
    """Sincroniza rascunhos não verificados com issues do GitHub."""
    try:
        topic_map = load_topic_map(Path(config_dir) / TOPICS_FILENAME)
        result = sync_draft_issues(db_path, topic_map)
    except (GitHubIssueError, StorageError, OSError, ValueError) as exc:
        return False, [f"drafts sync-issues: ERRO — {exc}"]
    lines = [
        f"drafts sync-issues: OK — {len(result.created)} issues criadas, "
        f"{result.already_present} já existentes, {result.same_topic} do mesmo tema"
    ]
    lines.extend(f"- issue criada: {issue}" for issue in result.created)
    return True, lines


def prune(db_path: Path, days: int, now: datetime | None = None) -> tuple[bool, list[str]]:
    """Apaga itens recolhidos há mais de `days` dias (DEC-061)."""
    if days < 1:
        return False, ["prune: ERRO — --days tem de ser pelo menos 1"]
    if not Path(db_path).is_file():
        return True, ["prune: OK — base inexistente, nada a limpar"]
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    try:
        removed = prune_raw_items(db_path, cutoff)
    except StorageError as exc:
        return False, [f"prune: ERRO — {exc}"]
    return True, [f"prune: OK — {removed} itens com mais de {days} dias apagados"]


def llm_check(config_dir: Path, environ: Mapping[str, str]) -> list[str]:
    """Verifica o fornecedor de IA com um pedido mínimo; nunca falha o comando (DEC-061)."""
    try:
        loaded = load_provider(config_dir, environ)
    except (OSError, ValueError, KeyError) as exc:
        return [f"llm: ERRO — configuração inválida: {exc}"]
    if loaded is None:
        return [
            "llm: desactivado — nenhuma chave definida (GEMINI_API_KEY ou GROQ_API_KEY); "
            "rascunhos só por regras"
        ]
    name, task = next(iter(loaded.tasks.items()))
    providers = getattr(loaded.provider, "providers", (loaded.provider,))
    lines = []
    for provider in providers:
        label = f"{provider.name} {getattr(provider, 'model', '')}".strip()
        try:
            provider.complete(task, "Responde apenas: OK", "Teste de ligação.")
        except LLMError as exc:
            lines.append(f"llm: ERRO — {label} ({name}): {exc}")
        else:
            lines.append(f"llm: OK — {label} ({name})")
    # Rascunho de teste completo (prompt, JSON e validação), com o texto do exemplo editorial.
    proposal = write_whatsapp(loaded, SAMPLE_TITLE, SAMPLE_TEXT)
    if proposal is None:
        lines.append("llm: rascunho de teste — falhou a validação; os rascunhos usam regras")
    else:
        lines.append(f"llm: rascunho de teste OK — {proposal.emoji} {proposal.title}")
    return lines


SAMPLE_TITLE = "Bolsa de mérito para alunos do secundário com Ação Social Escolar"
SAMPLE_TEXT = (
    "Os alunos do ensino secundário que sejam beneficiários da Ação Social Escolar podem ter "
    "acesso a uma bolsa de mérito. É necessário ter média superior a 14 valores no 10.º ou "
    "11.º ano. O valor da bolsa é de 1.342,83 euros. A candidatura deve ser feita até 30 de "
    "setembro, na escola frequentada pelo aluno."
)


def drafts_close_stale(days: int) -> tuple[bool, list[str]]:
    """Fecha as issues de rascunho abertas há mais de `days` dias (DEC-058)."""
    try:
        result = close_stale_draft_issues(days)
    except (GitHubIssueError, ValueError) as exc:
        return False, [f"drafts close-stale: ERRO — {exc}"]
    lines = [f"drafts close-stale: OK — {len(result.closed)} issues fechadas"]
    lines.extend(f"- issue fechada: #{number}" for number in result.closed)
    return True, lines


def drafts_approve(
    db_path: Path, draft_id: int, verification_status: VerificationStatus
) -> tuple[bool, list[str]]:
    """Marca um rascunho como aprovado após declaração explícita de verificação humana."""
    try:
        approved = approve_draft(db_path, draft_id, verification_status, datetime.now(UTC))
    except (StorageError, ValueError) as exc:
        return False, [f"drafts approve: ERRO — {exc}"]
    if not approved:
        return False, [
            f"drafts approve: ERRO — rascunho {draft_id} inexistente, não elegível ou não pendente"
        ]
    return True, [
        f"rascunho {draft_id}: aprovado",
        f"verificação: {verification_status.value}",
    ]


def drafts_export(
    db_path: Path,
    verification_statuses: Sequence[VerificationStatus],
    output_format: str,
    mark_published: bool,
) -> tuple[bool, list[str]]:
    """Exporta rascunhos aprovados para cópia manual ou formatos estruturados."""
    try:
        drafts = export_approved_drafts(
            db_path,
            verification_statuses,
            datetime.now(UTC),
            mark_published=mark_published,
        )
    except (StorageError, ValueError) as exc:
        return False, [f"drafts export: ERRO — {exc}"]

    if not drafts:
        if output_format == "json":
            return True, ["[]"]
        if output_format == "markdown":
            return True, ["*Sem rascunhos aprovados elegíveis para exportação.*"]
        return True, ["nenhum rascunho aprovado elegível para exportação"]
    if output_format == "whatsapp":
        return True, ["\n\n".join(draft.message for draft in drafts)]
    if output_format == "json":
        return True, [
            json.dumps(
                [
                    {
                        "id": draft.id,
                        "editorial_score": draft.editorial_score,
                        "verification_status": draft.verification_status.value,
                        "status": draft.status,
                        "message": draft.message,
                    }
                    for draft in drafts
                ],
                ensure_ascii=False,
                indent=2,
            )
        ]
    if output_format == "markdown":
        return True, [
            "\n\n".join(
                f"## Rascunho {draft.id}\n\n"
                f"- Verificação: `{draft.verification_status.value}`\n"
                f"- Score: {draft.editorial_score:g}\n\n"
                f"{draft.message}"
                for draft in drafts
            )
        ]
    raise ValueError(f"formato de exportação desconhecido: {output_format}")


def publish_whatsapp(input_path: Path) -> tuple[bool, list[str]]:
    """Gera uma pré-visualização WhatsApp apenas para conteúdo elegível."""
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, [f"publish: ERRO — {input_path}", f"- {exc}"]

    try:
        if not isinstance(data, dict):
            raise ValueError("o manifesto tem de ser um objecto JSON")
        required = {
            "emoji",
            "title",
            "key_points",
            "cta",
            "url",
            "editorial_score",
            "verification_status",
            "editorial_status",
            "is_duplicate",
        }
        missing = required - data.keys()
        extra = data.keys() - required
        if missing or extra:
            details = []
            if missing:
                details.append(f"campos em falta: {', '.join(sorted(missing))}")
            if extra:
                details.append(f"campos desconhecidos: {', '.join(sorted(extra))}")
            raise ValueError("; ".join(details))

        points = data["key_points"]
        if not isinstance(points, list) or not all(isinstance(point, str) for point in points):
            raise ValueError("key_points tem de ser uma lista de texto")
        score = data["editorial_score"]
        if isinstance(score, bool) or not isinstance(score, int | float):
            raise ValueError("editorial_score tem de ser um número")
        if not isinstance(data["is_duplicate"], bool):
            raise ValueError("is_duplicate tem de ser booleano")

        message = WhatsAppMessage(
            emoji=data["emoji"],
            title=data["title"],
            key_points=tuple(points),
            cta=data["cta"],
            url=data["url"],
        )
        verification_status = VerificationStatus(data["verification_status"])
        editorial_status = EditorialStatus(data["editorial_status"])
        reasons = check_whatsapp_eligibility(
            score,
            verification_status,
            editorial_status,
            data["is_duplicate"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        return False, [f"publish: ERRO — {input_path}", f"- {exc}"]

    if reasons:
        return False, ["publish: NÃO ELEGÍVEL", *(f"- {reason}" for reason in reasons)]
    return True, ["publish: PRÉ-VISUALIZAÇÃO — whatsapp", format_whatsapp_message(message)]


def _daily_lines(result: DailyResult) -> tuple[int, list[str], list[str]]:
    collection = result.collection
    label, code = {"success": ("OK", 0), "partial": ("PARCIAL", 2), "failed": ("ERRO", 1)}[
        collection.status
    ]
    out = [
        f"COLLECT: {label}",
        f"  fontes consultadas: {len(collection.endpoints)}",
        f"  itens obtidos: {collection.new + collection.existing}",
        "NORMALIZE",
        f"  documentos normalizados: {result.normalized}",
        f"  duplicados na janela: {result.duplicates}",
        "DAILY",
        f"  notícias selecionadas: {len(result.articles)}",
        f"  rascunhos WhatsApp gerados: {result.drafts_created}",
        f"relatório gerado: {result.report_path}",
        *_audit_lines(result),
    ]
    errors = [
        f"- {outcome.id}: {outcome.error}" for outcome in collection.endpoints if outcome.error
    ]
    return code, out, errors


def _audit_lines(result: DailyResult) -> list[str]:
    """Linhas `FUNIL`/`AUDITORIA` que o workflow transforma em anotações (DEC-063)."""
    counts = result.priority_counts()
    lines = [
        f"FUNIL: do dia {len(result.articles)}; alta {counts[Priority.HIGH.value]}; "
        f"rever {counts[Priority.REVIEW.value]}; baixa {counts[Priority.LOW.value]}; "
        f"rascunhos novos {result.drafts_created}"
    ]
    low = _spread_sample(result.by_priority(Priority.LOW), AUDIT_LOW_LINES)
    review = _review_first(result.by_priority(Priority.REVIEW))[:AUDIT_REVIEW_LINES]
    lines += [f"AUDITORIA baixa: {a.title} — {a.source_name}" for a in low]
    lines += [f"AUDITORIA rever: {a.title} — {a.priority_reason}" for a in review]
    stats = result.candidate_stats
    if stats is not None:
        methods = "; ".join(
            f"{method} {m.candidates} (só {m.exclusive}; do dia {m.today_candidates}, "
            f"só {m.today_exclusive})"
            for method, m in stats.by_method.items()
        )
        lines.append(
            f"CANDIDATOS: {stats.candidates} notícias, {stats.new_candidates} novas; "
            f"métodos: {methods or 'nenhum'}"
        )
    lines.append(_transport_line(result.collection))
    return lines


def _transport_line(collection: CollectResult) -> str:
    """Linha `TRANSPORTE` (DEC-070): limitações, novas tentativas e redirects do run."""
    counts = collection.transport_counts()
    return (
        f"TRANSPORTE: limitações {counts['limitação']}; "
        f"novas tentativas {counts['nova tentativa']}; "
        f"redirects seguidos {counts['redirect seguido']}; "
        f"redirects recusados {counts['redirect recusado']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="TensDireito Content Engine — motor editorial do TensDireito.com.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    parser.add_argument(
        "--config",
        metavar="DIR",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help=f"directório da configuração versionada (por defeito: {DEFAULT_CONFIG_DIR})",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        type=Path,
        default=None,
        help=f"base de dados SQLite (por defeito: ${DB_PATH_ENV}, senão {DEFAULT_DB_PATH})",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<comando>")
    subparsers.add_parser(
        "doctor",
        help="confirma que a aplicação está instalada e executável",
        description="Confirma que a aplicação está instalada e executável.",
    )
    subparsers.add_parser(
        "init",
        help="cria a base de dados e aplica as migrações pendentes",
        description="Cria a base de dados SQLite, se não existir, e aplica as migrações "
        "pendentes. Idempotente; escreve só o esquema, sem dados de negócio.",
    )
    sources = subparsers.add_parser(
        "sources",
        help="registo de fontes (config/sources.yaml)",
        description="Registo de fontes (config/sources.yaml).",
    )
    sources_actions = sources.add_subparsers(
        dest="sources_command", metavar="<acção>", required=True
    )
    sources_actions.add_parser(
        "validate",
        help="valida config/sources.yaml (local, sem rede, sem escrita)",
        description="Valida config/sources.yaml: esquema, IDs únicos, tiers, campos "
        "obrigatórios e invariantes do domínio. Local, sem rede e sem escrita.",
    )
    sources_actions.add_parser(
        "sync",
        help="sincroniza config/sources.yaml → SQLite (exige tde init)",
        description="Sincroniza o registo validado de config/sources.yaml com as tabelas "
        "source_registry e source_endpoint, pelo id, numa transacção única. Unidireccional "
        "(nunca escreve no YAML); preserva last_success_at e last_error; não cria a base de "
        "dados nem aplica migrações. Local, sem rede.",
    )
    collect_parser = subparsers.add_parser(
        "collect",
        help="recolhe os endpoints ACTIVE da base de dados (exige tde init)",
        description="Recolhe os endpoints ACTIVE do espelho SQLite com os collectors "
        "registados, num run, gravando raw_item sem duplicar. Não lê config/sources.yaml "
        "nem sincroniza; não cria a base de dados nem aplica migrações. Códigos: 0 sem "
        "falhas, 2 falhas parciais, 1 erro ou todos os endpoints falharam.",
    )
    collect_parser.add_argument(
        "--source",
        metavar="ID",
        default=None,
        help="recolhe só os endpoints ACTIVE desta fonte",
    )
    subparsers.add_parser(
        "normalize",
        help="normaliza os raw_item pendentes em source_document (exige tde init)",
        description="Normaliza os raw_item sem source_document, por ordem de id, num run, "
        "gravando um source_document por item rss, cada um numa transacção própria. Itens "
        "sem regra de extracção ficam pendentes, sem falha. Não lê config/sources.yaml nem "
        "acede à rede; não cria a base de dados nem aplica migrações. Códigos: 0 sem "
        "falhas, 2 falhas parciais, 1 erro ou todos os itens com falha.",
    )
    subparsers.add_parser(
        "ingest",
        help="sincroniza fontes, recolhe e normaliza (exige tde init)",
        description="Executa sources sync → collect → normalize na mesma base de dados. "
        "Não inicializa a base de dados. Falhas em sources sync interrompem a execução; "
        "falhas na recolha não impedem a normalização do que ficou persistido. Códigos: "
        "0 sem falhas, 2 com falhas parciais, 1 em caso de erro.",
    )
    daily_parser = subparsers.add_parser(
        "daily",
        help="recolhe, normaliza, deduplica e gera o relatório diário",
        description="Inicializa a base de dados se necessário, sincroniza as fontes, recolhe "
        "endpoints RSS ACTIVE, normaliza e deduplica os itens persistidos e escreve um "
        "relatório diário determinístico.",
    )
    daily_parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        metavar="AAAA-MM-DD",
        help="dia da janela (por defeito, hoje em Europe/Lisbon)",
    )
    daily_parser.description += (
        " Os rascunhos WhatsApp elegíveis são guardados na fila SQLite para revisão humana."
    )
    daily_parser.add_argument(
        "--summary-md",
        type=Path,
        default=None,
        metavar="FICHEIRO",
        help="acrescenta um resumo Markdown do run (p. ex. $GITHUB_STEP_SUMMARY)",
    )
    daily_parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        metavar="DIR",
        help=f"directório dos relatórios (por defeito: {DEFAULT_REPORT_DIR})",
    )
    prune_parser = subparsers.add_parser(
        "prune", help="apaga itens antigos da base para limitar o tamanho"
    )
    prune_parser.add_argument(
        "--days", type=int, default=60, metavar="N", help="idade mínima em dias (por defeito: 60)"
    )
    vigia_parser = subparsers.add_parser(
        "vigia",
        help="dispara o daily se a janela em curso não tiver run (DEC-071)",
        description="Vigia do agendamento: lê os runs do workflow daily no main e, se a "
        "janela em curso (08:07, 13:07 ou 18:07 UTC) não tiver um run bem-sucedido ou em "
        "curso uma hora depois do início, dispara-o. Usa o `gh`.",
    )
    vigia_parser.add_argument(
        "--dry-run", action="store_true", help="decide e mostra, mas não dispara"
    )
    llm_parser = subparsers.add_parser("llm", help="verifica o fornecedor de IA")
    llm_actions = llm_parser.add_subparsers(dest="llm_command", metavar="<acção>", required=True)
    llm_actions.add_parser("check", help="faz um pedido mínimo ao modelo configurado")
    drafts_parser = subparsers.add_parser(
        "drafts",
        help="lista, aprova e exporta rascunhos WhatsApp",
        description="Fila local de rascunhos WhatsApp. A aprovação e a exportação exigem "
        "verificação editorial ou oficial explícita.",
    )
    drafts_actions = drafts_parser.add_subparsers(
        dest="drafts_command", metavar="<acção>", required=True
    )
    drafts_actions.add_parser("list", help="lista os rascunhos pendentes")
    drafts_actions.add_parser(
        "sync-issues",
        help="cria issues GitHub para rascunhos pendentes não verificados",
    )
    close_parser = drafts_actions.add_parser(
        "close-stale",
        help="fecha issues de rascunho abertas há mais de N dias",
    )
    close_parser.add_argument(
        "--days", type=int, default=3, metavar="N", help="idade mínima em dias (por defeito: 3)"
    )
    approve_parser = drafts_actions.add_parser(
        "approve", help="aprova um rascunho após revisão humana"
    )
    approve_parser.add_argument("draft_id", type=int, metavar="ID")
    approve_parser.add_argument(
        "--verification-status",
        required=True,
        choices=(
            VerificationStatus.VERIFIED_EDITORIAL.value,
            VerificationStatus.VERIFIED_OFFICIAL.value,
        ),
        help="estado de verificação confirmado pela pessoa revisora",
    )
    export_parser = drafts_actions.add_parser(
        "export", help="exporta rascunhos aprovados e verificados"
    )
    export_parser.add_argument(
        "--verification-status",
        action="append",
        choices=(
            VerificationStatus.VERIFIED_EDITORIAL.value,
            VerificationStatus.VERIFIED_OFFICIAL.value,
        ),
        default=None,
        help="filtra por nível de verificação (repetível; por omissão, ambos)",
    )
    export_parser.add_argument(
        "--format",
        choices=("whatsapp", "json", "markdown"),
        default="whatsapp",
        help="formato da saída (por omissão, texto WhatsApp pronto a copiar)",
    )
    export_parser.add_argument(
        "--mark-published",
        action="store_true",
        help="marca como published os rascunhos exportados",
    )
    publish_parser = subparsers.add_parser(
        "publish",
        help="pré-visualiza conteúdos elegíveis para um destino de publicação",
        description="Formata uma mensagem WhatsApp a partir de um manifesto JSON. "
        "É uma pré-visualização local: não envia mensagens nem altera o estado publicado.",
    )
    publish_parser.add_argument(
        "--target",
        choices=("whatsapp",),
        required=True,
        help="destino de publicação",
    )
    publish_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        metavar="JSON",
        help="manifesto JSON com conteúdo e estado editorial",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        for line in doctor():
            print(line)
        return 0

    if args.command == "init":
        ok, lines = init(resolve_db_path(args.db, os.environ))
        stream = sys.stdout if ok else sys.stderr
        for line in lines:
            print(line, file=stream)
        return 0 if ok else 1

    if args.command == "sources" and args.sources_command == "validate":
        ok, lines = sources_validate(sources_path(args.config))
        stream = sys.stdout if ok else sys.stderr
        for line in lines:
            print(line, file=stream)
        return 0 if ok else 1

    if args.command == "sources" and args.sources_command == "sync":
        ok, lines = sources_sync(sources_path(args.config), resolve_db_path(args.db, os.environ))
        stream = sys.stdout if ok else sys.stderr
        for line in lines:
            print(line, file=stream)
        return 0 if ok else 1

    if args.command == "collect":
        code, out, err = collect(
            resolve_db_path(args.db, os.environ), default_registry(), args.source
        )
        for line in out:
            print(line)
        for line in err:
            print(line, file=sys.stderr)
        return code

    if args.command == "normalize":
        code, out, err = normalize(resolve_db_path(args.db, os.environ))
        for line in out:
            print(line)
        for line in err:
            print(line, file=sys.stderr)
        return code

    if args.command == "ingest":
        code, out, err = ingest(
            resolve_db_path(args.db, os.environ),
            args.config,
            default_registry(),
        )
        for line in out:
            print(line)
        for line in err:
            print(line, file=sys.stderr)
        return code

    if args.command == "daily":
        code, out, err = daily(
            resolve_db_path(args.db, os.environ),
            args.config,
            args.report_dir,
            default_registry(),
            args.date,
            args.summary_md,
            os.environ,
        )
        for line in out:
            print(line)
        for line in err:
            print(line, file=sys.stderr)
        return code

    if args.command == "prune":
        ok, lines = prune(resolve_db_path(args.db, os.environ), args.days)
        for line in lines:
            print(line, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "vigia":
        try:
            _, lines = run_vigia(dry_run=args.dry_run)
        except VigiaError as exc:
            print(f"VIGIA: ERRO — {exc}", file=sys.stderr)
            return 1
        for line in lines:
            print(line)
        return 0

    if args.command == "llm" and args.llm_command == "check":
        for line in llm_check(args.config, os.environ):
            print(line)
        return 0

    if args.command == "drafts" and args.drafts_command == "list":
        ok, lines = drafts_list(resolve_db_path(args.db, os.environ))
        for line in lines:
            print(line, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "drafts" and args.drafts_command == "sync-issues":
        ok, lines = drafts_sync_issues(resolve_db_path(args.db, os.environ), args.config)
        for line in lines:
            print(line, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "drafts" and args.drafts_command == "close-stale":
        ok, lines = drafts_close_stale(args.days)
        for line in lines:
            print(line, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "drafts" and args.drafts_command == "approve":
        ok, lines = drafts_approve(
            resolve_db_path(args.db, os.environ),
            args.draft_id,
            VerificationStatus(args.verification_status),
        )
        for line in lines:
            print(line, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "drafts" and args.drafts_command == "export":
        statuses = (
            tuple(VerificationStatus(value) for value in args.verification_status)
            if args.verification_status
            else (
                VerificationStatus.VERIFIED_EDITORIAL,
                VerificationStatus.VERIFIED_OFFICIAL,
            )
        )
        ok, lines = drafts_export(
            resolve_db_path(args.db, os.environ),
            statuses,
            args.format,
            args.mark_published,
        )
        for line in lines:
            print(line, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "publish" and args.target == "whatsapp":
        ok, lines = publish_whatsapp(args.input)
        stream = sys.stdout if ok else sys.stderr
        for line in lines:
            print(line, file=stream)
        return 0 if ok else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
