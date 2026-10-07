"""Leitura segura e local de YAML para a configuração versionada.

Lê o ficheiro em UTF-8 e usa `yaml.SafeLoader` (sem construção de objectos Python) com
duas restrições (DEC-025):

- as datas não são convertidas implicitamente: ficam texto e são interpretadas por quem
  as consome, para que o fuso nunca seja assumido pelo parser;
- uma chave repetida no mesmo mapeamento é um erro (o YAML não as permite e o
  `SafeLoader` guardaria em silêncio só a última);
- a merge key `<<` não faz parte do formato: é um erro, e nenhum mapeamento é fundido.
"""

from pathlib import Path

import yaml
from yaml.constructor import ConstructorError

_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"
_MERGE_TAG = "tag:yaml.org,2002:merge"


class YamlLoadError(ValueError):
    """Ficheiro YAML inexistente, ilegível ou sintacticamente inválido."""


class _StrictSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            seen: set[object] = set()
            for key_node, _ in node.value:
                if key_node.tag == _MERGE_TAG:
                    raise ConstructorError(
                        "ao construir um mapeamento",
                        node.start_mark,
                        "merge key '<<' não suportada",
                        key_node.start_mark,
                    )
                key = self.construct_object(key_node, deep=deep)
                try:
                    repeated = key in seen
                except TypeError:
                    continue  # chave não hashable: o construtor base reporta o erro
                if repeated:
                    raise ConstructorError(
                        "ao construir um mapeamento",
                        node.start_mark,
                        f"chave repetida: {key!r}",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


_StrictSafeLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP_TAG]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path) -> object:
    """Lê e interpreta um ficheiro YAML. Apenas leitura; sem rede."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise YamlLoadError(f"ficheiro não encontrado: {path}") from None
    except IsADirectoryError:
        raise YamlLoadError(f"não é um ficheiro: {path}") from None
    except UnicodeDecodeError:
        raise YamlLoadError(f"ficheiro não está em UTF-8: {path}") from None
    except OSError as exc:
        raise YamlLoadError(f"não foi possível ler {path}: {exc.strerror}") from None
    try:
        return yaml.load(text, Loader=_StrictSafeLoader)
    except yaml.YAMLError as exc:
        raise YamlLoadError(f"YAML inválido em {path}: {_describe(exc)}") from None


def _describe(exc: yaml.YAMLError) -> str:
    if isinstance(exc, yaml.MarkedYAMLError):
        problem = exc.problem or exc.context or "erro de sintaxe"
        mark = exc.problem_mark or exc.context_mark
        if mark is not None:
            return f"{problem} (linha {mark.line + 1}, coluna {mark.column + 1})"
        return problem
    return str(exc)
