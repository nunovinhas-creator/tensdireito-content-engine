# Especificação Técnica

> Estado: **especificação para a fase de implementação**. Nada aqui está ainda implementado. Nomes de pacotes, módulos e comandos são propostas a confirmar no início da Fase 1 (ver [ROADMAP.md](ROADMAP.md)).

## 1. Stack

| Área | Escolha v1 | Notas |
|------|-----------|-------|
| Linguagem | Python 3.12+ | |
| Base de dados | SQLite (ficheiro local) | Migração prevista para PostgreSQL (ver ADR-002). |
| Acesso a dados | `sqlite3` da biblioteca padrão, atrás de uma camada de repositório | Evitar ORM na v1 para reduzir dependências; reavaliar na migração para PostgreSQL. |
| Configuração | Ficheiros YAML versionados + variáveis de ambiente para segredos | |
| CLI | `argparse` (biblioteca padrão) | |
| Testes | `pytest` | |
| Qualidade | `ruff` (lint + format) | |
| Gestão de dependências | `pyproject.toml` | Ferramenta de gestão (pip/uv) a decidir. |
| Automação | GitHub Actions (fase posterior) | Apenas invoca comandos CLI. |

### Política de dependências

- Preferir a biblioteca padrão.
- Cada dependência externa tem de ser justificada no PR que a introduz e listada na secção 7.
- Dependências esperadas na Fase 1 (a confirmar): cliente HTTP, parser de RSS/Atom, extractor de HTML, parser YAML.
- SDKs de fornecedores de IA só são instalados como *extras* opcionais (ex.: `pip install .[anthropic]`), nunca como dependência base.

## 2. Estrutura de código proposta

```
tensdireito-content-engine/
├── pyproject.toml
├── README.md
├── docs/
├── config/
│   ├── sources.yaml          # registo de fontes (SOURCES.md)
│   ├── taxonomy.yaml         # temas e tipos de alteração
│   ├── scoring.yaml          # pesos e limiares (SCORING.md)
│   └── llm.yaml              # fornecedor/modelo por tarefa (AI_RULES.md)
├── prompts/                  # prompts versionados, um ficheiro por tarefa e versão
├── src/tensdireito_engine/
│   ├── cli.py
│   ├── config.py
│   ├── models.py             # dataclasses das entidades (DATA_MODEL.md)
│   ├── storage/              # repositórios + esquema SQL + migrações
│   ├── sources/
│   ├── collectors/           # base.py (interface Collector), rss.py, html_page.py, manual.py
│   ├── normalize/
│   ├── classify/
│   ├── cluster/
│   ├── verify/
│   ├── scoring/
│   ├── generate/             # um gerador por formato
│   ├── review/
│   ├── report/
│   └── llm/                  # base.py (interface LLMProvider), null.py, <fornecedor>.py
├── tests/
│   └── fixtures/             # HTML/RSS reais guardados para testes offline
└── data/                     # (gitignored) base de dados SQLite, exports, relatórios
```

## 3. Interface de linha de comandos

Um único executável (nome provisório `tde`). Cada etapa é um subcomando independente e idempotente.

| Comando | Descrição | Escreve |
|---------|-----------|---------|
| `tde init` | Cria a base de dados e aplica migrações. | esquema |
| `tde sources validate` | Valida `config/sources.yaml`. | — |
| `tde collect [--source ID] [--since DATA]` | Recolhe itens das fontes activas. | `raw_item`, `run` |
| `tde add-manual --url URL [--note TEXTO]` | Regista manualmente uma pista (ex.: vista numa rede social). | `raw_item` |
| `tde normalize` | Normaliza `RawItem` pendentes. | `document` |
| `tde classify` | Classifica documentos pendentes. | `document.topics`, `document.change_type` |
| `tde cluster` | Agrupa documentos em acontecimentos. | `event`, `event_document` |
| `tde verify [--event ID]` | Extrai claims e associa evidência. | `claim`, `evidence`, `event.verification_status` |
| `tde score` | Calcula pontuações e decide selecção. | `score`, `event.status` |
| `tde generate --event ID --format FORMAT` | Gera conteúdo num formato. | `content_piece` |
| `tde review list` / `approve ID` / `reject ID --reason` | Revisão humana. | `content_piece.status`, `editorial_decision` |
| `tde export --status ready_to_publish --out DIR` | Exporta conteúdo aprovado (Markdown/JSON). | ficheiros |
| `tde report [--run ID]` | Mostra o relatório de uma execução. | — |
| `tde run` | Executa `collect → normalize → classify → cluster → verify → score` e produz relatório. | tudo acima |

Opções globais: `--db PATH`, `--config DIR`, `--dry-run` (não escreve), `--no-llm` (desactiva IA, usa só regras), `--verbose`.

Códigos de saída: `0` sucesso (incluindo "nada a publicar"); `1` erro; `2` sucesso parcial (algumas fontes falharam).

## 4. Interfaces internas

### 4.1 Collector

```python
class Collector(Protocol):
    source_type: str                     # "rss" | "html_page" | "manual"
    def fetch(self, source: Source, since: datetime | None) -> Iterable[RawItemIn]: ...
```

- Não normaliza nem interpreta conteúdo — apenas obtém e guarda o bruto.
- Respeita `rate_limit` e `user_agent` definidos na configuração.
- Falhas numa fonte não interrompem as restantes; ficam registadas no `run`.

### 4.2 LLMProvider

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, request: LLMRequest) -> LLMResponse: ...

@dataclass
class LLMRequest:
    task: str                 # "classify" | "extract_claims" | "match_evidence" | "summarize" | "generate:<formato>"
    prompt_id: str            # ex.: "extract_claims@v3"
    system: str
    input: str
    json_schema: dict | None  # quando se espera saída estruturada
    temperature: float = 0.0
    max_tokens: int = 2000

@dataclass
class LLMResponse:
    text: str
    parsed: dict | None
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
```

- Implementação `NullProvider` obrigatória (usada com `--no-llm` e nos testes).
- A escolha de fornecedor/modelo por tarefa vem de `config/llm.yaml`.
- Todas as chamadas são registadas na tabela `llm_call` (ver [DATA_MODEL.md](DATA_MODEL.md)).

### 4.3 Generator

```python
class Generator(Protocol):
    format: str                          # "whatsapp" | "article" | "seo_meta" | ...
    def generate(self, event: VerifiedEventBundle) -> ContentDraft: ...
```

`VerifiedEventBundle` contém o evento, as claims com evidência e as fontes. O gerador **só** pode usar informação presente no bundle.

## 5. Configuração

- `config/*.yaml` — versionados, sem segredos.
- Segredos (chaves de API) — exclusivamente em variáveis de ambiente (ex.: `TDE_LLM_API_KEY_<FORNECEDOR>`); em GitHub Actions via *repository secrets*. Ver [SECURITY.md](SECURITY.md).
- `TDE_DB_PATH` — caminho da base de dados (por defeito `data/tde.sqlite3`).
- Fuso horário de referência: `Europe/Lisbon` para apresentação; armazenamento em UTC (ISO 8601).

## 6. Requisitos não funcionais

| Requisito | Especificação |
|-----------|---------------|
| Idempotência | Repetir uma etapa sem dados novos não cria registos duplicados (chaves únicas por hash/URL). |
| Re-execução | Qualquer etapa pode ser corrida isoladamente sobre os dados existentes. |
| Rastreabilidade | Todo o registo guarda `run_id` de criação; toda a claim publicada tem ≥1 evidência. |
| Determinismo | Com `--no-llm`, o resultado de uma etapa é determinista para os mesmos dados. |
| Tolerância a falhas | Falha de uma fonte ou chamada de IA não aborta a execução; fica registada. |
| Testabilidade | Testes correm offline com fixtures; nenhum teste chama a rede ou um fornecedor de IA. |
| Observabilidade | Logs estruturados (JSON lines) por execução; relatório legível por humanos. |
| Língua | Conteúdo produzido em português europeu. |
| Custo | Chamadas de IA contabilizadas por execução (tokens); limite configurável por execução. |

## 7. Registo de dependências

Nenhuma dependência adicionada nesta fase (apenas documentação). Esta tabela será preenchida na Fase 1.

| Pacote | Motivo | Fase |
|--------|--------|------|
| — | — | — |

## 8. Execução

- **Manual (Fases 1–3):** `tde run` seguido de `tde review` e `tde generate`, executados localmente.
- **Agendada (Fase 4+):** workflow GitHub Actions que corre `tde run` em horário definido, guarda a base de dados/relatório como artefacto ou em armazenamento persistente (decisão pendente — ver ambiguidades em [ROADMAP.md](ROADMAP.md)) e notifica com o relatório.
