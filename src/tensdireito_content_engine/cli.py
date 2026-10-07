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
from tensdireito_content_engine.config import DEFAULT_CONFIG_DIR, sources_path
from tensdireito_content_engine.sources import SourceRegistryError, load_sources
from tensdireito_content_engine.storage import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    StorageError,
    init_database,
    resolve_db_path,
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

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
