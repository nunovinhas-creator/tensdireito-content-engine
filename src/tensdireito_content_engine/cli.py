"""Interface de linha de comandos `tde`.

Usa `argparse` (biblioteca padrão), conforme TECHNICAL_SPEC.md §1, para não
introduzir dependências externas.
"""

import argparse
import os
import platform
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from tensdireito_content_engine import __version__
from tensdireito_content_engine.collect import CollectError, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry, default_registry
from tensdireito_content_engine.config import DEFAULT_CONFIG_DIR, sources_path
from tensdireito_content_engine.daily import DEFAULT_REPORT_DIR, DailyResult, run_daily
from tensdireito_content_engine.normalize_command import run_normalize
from tensdireito_content_engine.sources import SourceRegistryError, load_sources
from tensdireito_content_engine.storage import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    SourceSyncError,
    StorageError,
    init_database,
    resolve_db_path,
    sync_sources,
)

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
) -> tuple[int, list[str], list[str]]:
    """Executa o pipeline diário e traduz o resultado para a CLI."""
    try:
        result = run_daily(
            db_path,
            sources_path(config_dir),
            report_dir,
            registry,
            day=day,
        )
    except (StorageError, CollectError, SourceRegistryError, OSError, ValueError) as exc:
        return 1, [], [f"daily: ERRO — {exc}"]
    return _daily_lines(result)


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
        f"relatório gerado: {result.report_path}",
    ]
    errors = [
        f"- {outcome.id}: {outcome.error}"
        for outcome in collection.endpoints
        if outcome.error
    ]
    return code, out, errors


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
    daily_parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        metavar="DIR",
        help=f"directório dos relatórios (por defeito: {DEFAULT_REPORT_DIR})",
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
        )
        for line in out:
            print(line)
        for line in err:
            print(line, file=sys.stderr)
        return code

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
