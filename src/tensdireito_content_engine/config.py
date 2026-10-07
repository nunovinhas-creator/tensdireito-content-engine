"""Configuração interna mínima da aplicação.

Contém apenas valores necessários à fundação e a localização da configuração
versionada (`config/*.yaml`, TECHNICAL_SPEC.md §2, §5): por defeito o directório
`config/` relativo ao directório de trabalho, ou o indicado em `--config DIR`
(TECHNICAL_SPEC.md §3). Não lê variáveis de ambiente, segredos nem serviços externos;
os segredos serão introduzidos quando tiverem consumidor.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tensdireito_content_engine import __version__

APP_NAME = "TensDireito Content Engine"
DEFAULT_CONFIG_DIR = Path("config")
SOURCES_FILENAME = "sources.yaml"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"


@dataclass(frozen=True, slots=True, kw_only=True)
class AppConfig:
    app_name: str = APP_NAME
    version: str = __version__
    environment: Environment = Environment.DEVELOPMENT

    def __post_init__(self) -> None:
        if not isinstance(self.environment, Environment):
            raise ValueError(f"environment inválido: {self.environment!r}")
        if not self.app_name.strip():
            raise ValueError("app_name não pode ser vazio")
        if not self.version.strip():
            raise ValueError("version não pode ser vazia")


def load_config(environment: Environment = Environment.DEVELOPMENT) -> AppConfig:
    """Devolve a configuração da aplicação. Determinista; sem efeitos externos."""
    return AppConfig(environment=environment)


def sources_path(config_dir: Path = DEFAULT_CONFIG_DIR) -> Path:
    """Caminho do registo de fontes dentro do directório de configuração."""
    return Path(config_dir) / SOURCES_FILENAME
