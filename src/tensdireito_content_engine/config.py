"""Configuração interna mínima da aplicação.

Nesta fase contém apenas valores necessários à fundação: não lê ficheiros,
variáveis de ambiente, segredos nem serviços externos. A configuração versionada
(`config/*.yaml`) e os segredos (variáveis de ambiente) descritos em
TECHNICAL_SPEC.md §5 serão introduzidos quando tiverem consumidor.
"""

from dataclasses import dataclass
from enum import StrEnum

from tensdireito_content_engine import __version__

APP_NAME = "TensDireito Content Engine"


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
