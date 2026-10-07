"""Interface de linha de comandos `tde`.

Usa `argparse` (biblioteca padrão), conforme TECHNICAL_SPEC.md §1, para não
introduzir dependências externas.
"""

import argparse
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from tensdireito_content_engine import __version__
from tensdireito_content_engine.collect import CollectError, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry, default_registry
from tensdireito_content_engine.config import DEFAULT_CONFIG_DIR, sources_path
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

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
