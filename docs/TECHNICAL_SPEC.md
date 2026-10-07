# Especificação Técnica

> Estado: **especificação para a fase de implementação (M1)**. O que já está implementado ou definido por milestone é indicado em cada secção (marcas *Implementado* e *Definido*); o resto continua por implementar. A linguagem, o gestor de projecto, o nome do pacote e o nome da CLI estão **decididos** (DEC-015 no [DECISION_LOG.md](DECISION_LOG.md)); nomes de módulos internos e de subcomandos podem ser ajustados na implementação, mantendo os conceitos.

## 1. Stack

| Área | Escolha v1 | Notas |
|------|-----------|-------|
| Linguagem | Python 3.12+ | Decidido (DEC-015). |
| Base de dados | SQLite (ficheiro local) | Migração prevista para PostgreSQL (ADR-002, DEC-013). Não é solução suficiente para execução agendada em runners efémeros. |
| Acesso a dados | `sqlite3` da biblioteca padrão, atrás de uma camada de repositório | Evitar ORM na v1 para reduzir dependências; reavaliar na migração para PostgreSQL. |
| Configuração | Ficheiros YAML versionados + variáveis de ambiente para segredos | |
| CLI | `argparse` (biblioteca padrão) | |
| Testes | `pytest` | |
| Qualidade | `ruff` (lint + format) | |
| Gestão de projecto e dependências | `uv` + `pyproject.toml` + `uv.lock` | Decidido (DEC-015). |
| Pacote | `tensdireito_content_engine` | Decidido (DEC-015). |
| CLI | `tde` | Decidido (DEC-015). |
| Automação | GitHub Actions (fase posterior) | Apenas invoca comandos CLI; só depois da decisão de persistência durável (D8). |
| Arquitectura | Monólito modular | Sem microserviços (DEC-016). |

### Política de dependências

- Preferir a biblioteca padrão.
- Cada dependência externa tem de ser justificada no PR que a introduz e listada na secção 7.
- Dependências esperadas na Fase 1 (a confirmar): cliente HTTP, parser de RSS/Atom, extractor de HTML, parser YAML.
- Implementado (M2.9; DEC-033): o cliente HTTP e o parser de RSS 2.0 do collector `rss` usam só a biblioteca padrão (`http.client`, `ssl`, `socket`, `ipaddress`, `urllib.robotparser`, `xml.parsers.expat`, `xml.etree.ElementTree`); `feedparser`, `httpx`/`requests` e `defusedxml` foram considerados e rejeitados.
- SDKs de fornecedores de IA só são instalados como *extras* opcionais (ex.: `uv sync --extra <fornecedor>`), nunca como dependência base.
- Nenhuma dependência é adicionada nas fases de documentação.

## 2. Estrutura de código proposta

```
tensdireito-content-engine/
├── pyproject.toml
├── uv.lock
├── README.md
├── docs/
├── config/
│   ├── sources.yaml          # source_registry + source_endpoint (SOURCES.md)
│   ├── taxonomy.yaml         # categorias, subcategorias, audiências, impact_type, legal_stage (EDITORIAL_POLICY.md)
│   ├── scoring.yaml          # pesos e limiares (SCORING.md)
│   └── llm.yaml              # fornecedor/modelo por tarefa (AI_RULES.md)
├── prompts/                  # prompts versionados, um ficheiro por tarefa e versão
├── src/tensdireito_content_engine/
│   ├── cli.py
│   ├── config.py             # configuração interna mínima (M2.2)
│   ├── domain/               # enums e entidades de domínio, sem persistência (DATA_MODEL.md; M2.2)
│   ├── storage/              # ligação SQLite + migrações numeradas (M2.6; DEC-026); repositórios por entidade depois
│   ├── sources/
│   ├── collectors/           # base.py (interface Collector), http.py (único transporte de rede; M2.9), rss.py, html_page.py, manual.py
│   ├── normalize/            # normalização mecânica + fingerprint (M2.3; DEC-021) + deduplicação exacta (M2.4; DEC-022)
│   ├── classify/
│   ├── cluster/
│   ├── verify/
│   ├── scoring/
│   ├── generate/             # um gerador por formato
│   ├── checks/               # validações automáticas pós-geração
│   ├── review/               # revisão humana e decisões editoriais
│   ├── export/
│   ├── report/
│   └── llm/                  # base.py (interface LLMProvider), null.py, <fornecedor>.py
├── tests/
│   └── fixtures/             # HTML/RSS sintéticos para testes offline (sem fontes nem URLs reais; DEC-034)
└── data/                     # (gitignored) base de dados SQLite, exports, relatórios
```

## 3. Interface de linha de comandos

Um único executável, `tde`. Cada etapa é um subcomando independente e idempotente. Execução local: `uv run tde <comando>`.

| Comando | Descrição | Escreve |
|---------|-----------|---------|
| `tde init` | Cria a base de dados e aplica migrações. | esquema |
| `tde sources validate` | Valida `config/sources.yaml`. | — |
| `tde sources sync` | Sincroniza `config/sources.yaml` → SQLite (unidireccional; só os campos projectados; exige base criada por `tde init`). Contrato no [ROADMAP.md](ROADMAP.md#m27--sincronização-explícita-de-sourcesyaml-para-sqlite) M2.7 (DEC-028, DEC-029). | `source_registry`, `source_endpoint` |
| `tde collect [--source ID] [--since DATA]` | Recolhe itens dos endpoints `ACTIVE`. | `raw_item`, `run` |
| `tde add-manual --url URL [--note TEXTO]` | Regista manualmente uma pista; tier pelo domínio validado, senão T4. | `raw_item` |
| `tde normalize` | Normaliza `raw_item` pendentes. | `source_document` |
| `tde classify` | Classifica documentos pendentes (propostas). | `source_document.proposed_*` |
| `tde cluster` | Cria ou actualiza eventos. | `event`, `event_document` |
| `tde verify [--event ID]` | Extrai claims, associa evidência, calcula verificação. | `claim`, `source_evidence`, `event.verification_status` |
| `tde score` | Calcula `editorial_score` e propõe estado editorial. | `score`, `event.editorial_status` |
| `tde generate --event ID --format FORMAT` | Gera conteúdo para um evento em `EDITORIAL_REVIEW`. | `content_piece` |
| `tde check [--content ID]` | Corre as validações automáticas. | `content_piece.checks`, `review_status` |
| `tde review list` | Lista conteúdos em `HUMAN_REVIEW_REQUIRED`. | — |
| `tde review approve\|reject\|needs-revision ID --reviewer NOME [--note TEXTO]` | Revisão humana. | `content_piece.review_status`, `editorial_decision` |
| `tde event promote\|watch\|reject\|archive\|reopen\|merge ID --reviewer NOME [--note TEXTO]` | Decisões editoriais sobre eventos (nota obrigatória onde [DATA_MODEL.md](DATA_MODEL.md#37-editorial_decisiondecision) o exige). | `event.editorial_status`, `editorial_decision` |
| `tde claim override\|add-evidence ...` | Override de verificação (nunca para `VERIFIED_OFFICIAL`) e evidência manual. | `claim`, `source_evidence`, `editorial_decision` |
| `tde export --out DIR` | Exporta conteúdos `APPROVED` ainda não exportados (Markdown/JSON). Não publica. | ficheiros, `exported_at` |
| `tde report [--run ID]` | Mostra o relatório de uma execução. | — |
| `tde run` | Executa `collect → normalize → classify → cluster → verify → score` e produz relatório. | tudo acima até `score` |

Não existe comando de publicação na V1.

Opções globais: `--db PATH`, `--config DIR`, `--dry-run` (não escreve), `--no-llm` (desactiva IA, usa só regras), `--verbose`.

Implementado: `tde doctor` (M2.1), `tde [--config DIR] sources validate` (M2.5), `tde [--db PATH] init` (M2.6; contrato e saída em [ROADMAP.md](ROADMAP.md#m26--storage-sqlite-e-migração-inicial)) e `tde [--config DIR] [--db PATH] sources sync` (M2.7; contrato e saída em [ROADMAP.md](ROADMAP.md#m27--sincronização-explícita-de-sourcesyaml-para-sqlite)) — não cria a base de dados nem aplica migrações (`tde init` continua a não sincronizar fontes), corre numa transacção única, não acede à rede e não tem `--dry-run`.

Implementado (M2.8, integrado no PR #14; DEC-031): `tde [--db PATH] collect [--source ID]` — contrato e saída em [ROADMAP.md](ROADMAP.md#m28--recolha-local-ciclo-de-vida-de-run-persistência-de-raw_item-e-contrato-collector). Lê os endpoints `ACTIVE` do espelho SQLite, sem sincronização implícita; cria e fecha um `run`; grava `raw_item` com `created_in_run`, com atomicidade por endpoint; actualiza `last_success_at`/`last_error`; códigos `0` (nenhum endpoint falhou, incluindo zero endpoints `ACTIVE`), `2` (falhas parciais) e `1` (falha de pré-condição ou todos os endpoints seleccionados falharam). Sem collectors concretos nem rede. `--since`, que consta da linha de `tde collect` na tabela como interface-alvo, não faz parte do M2.8 e não é aceite pela CLI.

Implementado (M2.9; DEC-032, DEC-033): `tde collect` não muda de interface, saídas nem códigos; o registo de produção passa a ter o collector `rss`. Sem endpoints `ACTIVE` (D1), nenhum pedido de rede é feito. Contrato em [ROADMAP.md](ROADMAP.md#m29--primeiro-collector-concreto-rss-com-transporte-https-restrito).

Implementado (M2.10; DEC-035): `tde sources validate` recusa um endpoint `ACTIVE` cuja fonte não esteja `VALIDATED` (`CANDIDATE` ou `INACTIVE`), com o erro `um endpoint ACTIVE exige fonte VALIDATED (fonte <id>: <ESTADO>)`, reportado por endpoint ao lado dos restantes erros (código `1`); se o `registry_status` da própria fonte for inválido, só esse erro é reportado. A regra vive na leitura do registo (`sources/registry.py`), pelo que `tde sources sync` recusa o mesmo registo, sem verificação própria (DEC-028 (3)). Interface, saídas dos casos válidos e códigos de saída não mudam; `tde collect` não muda. Nenhuma outra regra entre estados é verificada: `domains`, evidência (DEC-036), verificações V1–V5 e identidade de `validated_by` (além do prefixo `llm:`) ficam para a revisão humana do pull request. Contrato em [ROADMAP.md](ROADMAP.md#m210--validação-de-fontes).

Códigos de saída: `0` sucesso (incluindo "nada a publicar"); `1` erro; `2` sucesso parcial (algumas fontes falharam).

## 4. Interfaces internas

### 4.1 Collector

```python
class Collector(Protocol):
    endpoint_type: str                   # "rss" | "html_page" | "manual"
    def fetch(self, endpoint: SourceEndpoint, since: datetime | None) -> Iterable[RawItemIn]: ...
```

- Não normaliza nem interpreta conteúdo — apenas obtém e guarda o bruto.
- Respeita `rate_limit` e `user_agent` definidos na configuração.
- Falhas numa fonte não interrompem as restantes; ficam registadas no `run`.

Implementado (M2.8, integrado no PR #14; DEC-031): `RawItemIn` é o modelo de domínio `RawItem` (M2.3), sem entidade nova; `endpoint` é o `SourceEndpoint` de domínio lido do espelho SQLite; `collectors/` depende só de `domain` (não importa `storage`); os collectors são registados por `endpoint_type`, num registo vazio em produção no M2.8 (os testes usam collectors falsos); no M2.8, `since` é sempre `None`. Um endpoint `ACTIVE` sem collector registado conta como falha desse endpoint. `rate_limit`, `user_agent` e `robots.txt` aplicam-se aos collectors concretos, fora do M2.8.

Implementado (M2.9; DEC-032, DEC-033; contrato em [ROADMAP.md](ROADMAP.md#m29--primeiro-collector-concreto-rss-com-transporte-https-restrito)): primeiro collector concreto, `endpoint_type = "rss"` (só RSS 2.0). A rede fica num único transporte, `collectors/http.py`, injectado no collector; o parsing é uma função pura `bytes` → `RawItem`, testável offline. Política do transporte: só `https`, destino público, sem redirects, só `200`, `Content-Type` XML aceite, sem compressão, limites de tamanho e tempo, uma tentativa, pedidos sequenciais com intervalo mínimo por anfitrião, `User-Agent` com contacto e `robots.txt` verificado em execução; `DOCTYPE` recusado no XML. Até ao transporte de `fetch` (DEC-028), `rate_limit` e `user_agent` são valores fixos no código, não lidos da configuração. Erros de transporte e de conteúdo são falhas do endpoint (DEC-031). Mapeamento: `url` ← `<link>`, `title` ← `<title>`, `raw_content` ← elemento `<item>` serializado, `external_id` ← `<guid>`, `published_at_raw` ← `<pubDate>`; sem `canonical_url` (D12) nem interpretação de datas (D13).

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

`VerifiedEventBundle` contém o evento, as claims (com `verification_status` e `legal_stage`), as evidências e as fontes. O gerador **só** pode usar informação presente no bundle e só claims `VERIFIED_OFFICIAL` ou `VERIFIED_EDITORIAL` (ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-7--generate)).

Os blocos de código desta secção são esboços de interface para orientar a implementação, não código da aplicação.

## 5. Configuração

- `config/*.yaml` — versionados, sem segredos.
- Segredos (chaves de API) — exclusivamente em variáveis de ambiente (ex.: `TDE_LLM_API_KEY_<FORNECEDOR>`); em GitHub Actions via *repository secrets*. Ver [SECURITY.md](SECURITY.md).
- `TDE_DB_PATH` — caminho da base de dados (por defeito `data/tde.sqlite3`).
- Fuso horário de referência: `Europe/Lisbon` para apresentação; armazenamento em UTC (ISO 8601).
- Implementado (M2.2): `config.py` contém apenas nome, versão (a do pacote) e ambiente (`development` por defeito, `test`). Não lê variáveis de ambiente; os segredos acima entram quando tiverem consumidor.
- Implementado (M2.5): `config/sources.yaml` é localizado no directório de configuração — por defeito `config/`, relativo ao directório de trabalho, ou o indicado pela opção global `--config DIR` (secção 3). É lido como UTF-8 por `sources/` e validado por `tde sources validate` (local, sem rede, sem escrita); regras do formato em SOURCES.md §4 (DEC-023 a DEC-025).
- Implementado (M2.6): o caminho da base de dados é `--db PATH`, senão `TDE_DB_PATH`, senão `data/tde.sqlite3`, relativo ao directório de trabalho (DEC-026); o directório pai é criado por `tde init` se faltar. `TDE_DB_PATH` é lido só pela CLI, para os comandos com base de dados (`tde init`, `tde sources sync` desde o M2.7 e `tde collect` no M2.8), com a mesma precedência; só `tde init` cria a base de dados; `config.py` e `tde doctor` continuam sem ler variáveis de ambiente. `data/` está no `.gitignore`.

## 6. Requisitos não funcionais

| Requisito | Especificação |
|-----------|---------------|
| Idempotência | Repetir uma etapa sem dados novos não cria registos duplicados (chaves únicas por hash/URL). |
| Re-execução | Qualquer etapa pode ser corrida isoladamente sobre os dados existentes. |
| Rastreabilidade | As entidades com relação a `run` definida no modelo ([DATA_MODEL.md](DATA_MODEL.md)) guardam o `run` de criação (`created_in_run`); as restantes — por exemplo, `source_registry` e `source_endpoint`, espelho operacional do registo versionado — não têm essa relação (DEC-028). Toda a claim usada em conteúdo aprovado tem ≥1 evidência validada. |
| Determinismo | Com `--no-llm`, o resultado de uma etapa é determinista para os mesmos dados. |
| Tolerância a falhas | Falha de uma fonte ou chamada de IA não aborta a execução; fica registada. |
| Testabilidade | Testes correm offline com fixtures; nenhum teste chama a rede ou um fornecedor de IA. Desde o M2.9 (DEC-033), o transporte de rede é injectável e uma salvaguarda nos testes faz falhar qualquer tentativa de abrir ligação. |
| Observabilidade | Logs estruturados (JSON lines) por execução; relatório legível por humanos. |
| Língua | Conteúdo publicado em português europeu, segundo o AO1990 (DEC-017). A documentação técnica interna não está sujeita a esta norma. |
| Custo | Chamadas de IA contabilizadas por execução (tokens); limite configurável por execução. |

## 7. Registo de dependências

Dependências de execução: `pyyaml` (a CLI usa `argparse` da biblioteca padrão). O M2.9 não acrescenta dependências: o transporte HTTPS e o parser RSS usam a biblioteca padrão (DEC-033).

| Pacote | Motivo | Fase |
|--------|--------|------|
| `pytest` (grupo `dev`) | Testes (secção 1). Apenas desenvolvimento. | M2 — fundação |
| `ruff` (grupo `dev`) | Lint e formatação (secção 1). Apenas desenvolvimento. | M2 — fundação |
| `uv_build` (build backend) | Construção do pacote e entry point `tde`; backend nativo do `uv` (DEC-015). Apenas build. | M2 — fundação |
| `pyyaml` | Parser YAML para `config/sources.yaml` (secção 1: configuração em YAML; parser YAML previsto na política de dependências). A biblioteca padrão não lê YAML. Usado só com `SafeLoader`, sem conversão implícita de datas e com chaves repetidas recusadas. | M2.5 |

## 8. Execução

- **Manual (Fases 1–4):** `tde run`, seguido de `tde generate`, `tde check`, `tde review` e `tde export`, executados localmente.
- **Agendada (Fase 5+):** workflow GitHub Actions que corre `tde run` em horário definido e notifica com o relatório. **Só pode ser activada depois de decidida a persistência durável e o estado partilhado** (D8 em [ROADMAP.md](ROADMAP.md#decisões-pendentes)): um SQLite local num runner efémero não persiste entre execuções e não é solução suficiente para produção.
- Em nenhum modo o sistema publica conteúdo; a V1 termina em `APPROVED → EXPORT`.
