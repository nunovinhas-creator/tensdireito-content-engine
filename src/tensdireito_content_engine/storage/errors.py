"""Erros da camada `storage`."""


class StorageError(Exception):
    """Erro da base de dados ou das migrações, com mensagem determinista."""
