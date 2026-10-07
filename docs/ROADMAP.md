# Roadmap

> Estado actual: **Fase 0 — Architecture / Documentation phase.** Milestone M1 (fecho das decisões arquitecturais e editoriais) concluído com o PR do M1, depois de revisto. M2 em curso: M2.1 (fundação executável), M2.2 (modelos de domínio), M2.3 (normalização e identidade) e M2.4 (deduplicação exacta por `text_hash`) concluídos e integrados (M2.3 no PR #5, M2.4 no PR #6); M2.5 (registo de fontes e validação de fontes) concluído e integrado (PR #8); M2.6 (storage SQLite e migração inicial) implementado, a integrar. Os critérios de saída da Fase 0 continuam dependentes de D1.

Cada fase termina com critérios de saída verificáveis. Uma fase só começa quando os critérios da anterior estão cumpridos e as decisões pendentes relevantes estão tomadas.

## Milestones

| Milestone | Âmbito | Estado |
|-----------|--------|--------|
| Prompt 1 | Documentação inicial da arquitectura e especificação técnica. | Concluído |
| **M1** | Decisões arquitecturais e editoriais fundamentais: modelo de verificação, taxonomia V1, modelo de fontes, guia de estilo, política editorial, revisão humana, separação score/verificação, estados editoriais, persistência, tooling, decision log. Apenas documentação. | **Concluído com o PR do M1, depois de revisto** |
| M2 | Implementação por unidades: M2.1 fundação executável; M2.2 modelos de domínio; M2.3 normalização e identidade (DEC-021); M2.4 deduplicação exacta por `text_hash` (DEC-022) — usa o `text_hash` do M2.3, faz apenas deduplicação exacta, sem clustering nem deduplicação aproximada; M2.5 registo de fontes e validação de fontes (ver [M2.5](#m25--registo-de-fontes-e-validação-de-fontes)); M2.6 storage SQLite e migração inicial (ver [M2.6](#m26--storage-sqlite-e-migração-inicial)). | **Em curso** — M2.1 a M2.5 concluídos e integrados (M2.4 no PR #6, M2.5 no PR #8); M2.6 implementado, a integrar |

### M2.5 — registo de fontes e validação de fontes

**Estado:** concluído e integrado (PR #8).

**Objectivo:** preparar a camada de fontes para os futuros collectors, sem os implementar: ler o registo versionado `config/sources.yaml` ([SOURCES.md](SOURCES.md#4-registo-configsourcesyaml) §4) para os modelos de domínio `SourceRegistry` e `SourceEndpoint` do M2.2 e validá-lo com `tde sources validate` ([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#3-interface-de-linha-de-comandos) §3).

**Entregáveis previstos:**
- Leitura de `config/sources.yaml`, no formato de SOURCES.md §4, para `SourceRegistry` e `SourceEndpoint`, respeitando os enums e invariantes do M2.2 sem os enfraquecer (ex.: fonte `CANDIDATE` sem `domains`; `VALIDATED`/`ACTIVE` com `validated_at` e `validated_by`). `validated_at` só é aceite com fuso explícito; nenhum fuso é assumido.
- Comando `tde sources validate`, local, determinista e sem escrita, que aplica as regras de SOURCES.md §4: esquema, IDs únicos, tiers válidos e campos obrigatórios; recusa endpoints `ACTIVE` sem `url` e sem `validated_at`. Regras que a documentação não define não são inventadas.
- Testes offline com registos fictícios (fixtures), sem fontes nem URLs reais.
- O parser YAML, se introduzido, segue a política de dependências de [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#1-stack) §1 (justificado no PR de implementação).

**Implementação:** `src/tensdireito_content_engine/sources/` (`registry.py`: conversão e regras; `yaml_loader.py`: leitura YAML segura) e `tde [--config DIR] sources validate` em `cli.py`. O comando escreve `sources: OK` e as contagens (código de saída `0`) ou `sources: ERRO` e todos os erros encontrados, pela ordem do ficheiro, em stderr (código de saída `1`). Representação das enumerações: estados em maiúsculas como na documentação (`CANDIDATE` → `candidate`); `entity_type`, `endpoint_type` e `tier` tal como o valor interno. Campos fora do formato de SOURCES.md §4 são recusados, com `validated_by` aceite por ser exigido pelo domínio para `VALIDATED`/`ACTIVE`. `validated_at` em ISO 8601 com fuso explícito é convertido para UTC; sem fuso é recusado. `fetch` é verificado como mapeamento, mas não tem correspondência nos modelos do M2.2 e não é convertido. Decisões de formato: DEC-023 (schema fechado), DEC-024 (estados em maiúsculas), DEC-025 (UTF-8 e chaves únicas). `config/sources.yaml` foi criado vazio (`[]`), à espera de D1. Dependência introduzida: `pyyaml` (TECHNICAL_SPEC.md §7).

**Dependência de D1:** as regras de validação já estão definidas e não dependem de D1. O **conteúdo** do registo depende de D1 e fica fora do M2.5: o M2.5 não acrescenta fontes concretas, URLs, feeds, endpoints nem `domains`, e não marca nenhuma fonte ou endpoint como `VALIDATED`/`ACTIVE`. A validação manual de uma fonte (URL, termos de utilização, `robots.txt`) e a decisão `VALIDATE_SOURCE` em `editorial_decision` (que exige persistência) não são feitas por `tde sources validate`.

**Exclusões:** collectors; RSS; HTML; HTTP; scraping; qualquer acesso à rede (incluindo verificar se um URL responde); descoberta automática de fontes; SQLite, migrações e ORM; deduplicação; clustering; `SourceDocument`; `SourceEvidence`; claims; verificação; scoring; IA; scheduler; WhatsApp; publicação. Não altera D12 (não calcula `canonical_url`) nem D13 (não interpreta `published_at_raw`); ambas continuam OPEN.

### M2.6 — storage SQLite e migração inicial

**Estado:** implementado, a integrar. Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção.

**Objectivo:** criar a camada `storage` ([ARCHITECTURE.md](ARCHITECTURE.md) §5; [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#2-estrutura-de-código-proposta) §2) e a primeira migração SQLite, aplicada por `tde init`, preparando a persistência de `source_registry`, `source_endpoint`, `raw_item`, `source_document` e `run` para as unidades que a vão usar (sincronização do registo, collectors, NORMALIZE). O M2.6 cria a base de dados e o esquema; não escreve dados de negócio. Decisões: DEC-026 (migrações e âmbito da migração inicial) e DEC-027 (relação entre `config/sources.yaml` e SQLite).

**Âmbito (entregáveis da implementação):**

1. **Localização da base de dados.** Ficheiro SQLite local. Caminho resolvido por esta ordem: opção global `--db PATH` ([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#3-interface-de-linha-de-comandos) §3); senão a variável `TDE_DB_PATH`; senão `data/tde.sqlite3`, relativo ao directório de trabalho ([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#5-configuração) §5). O directório pai é criado se não existir. `data/` passa a constar do `.gitignore` (TECHNICAL_SPEC.md §2 já o descreve como ignorado; hoje não está). A base de dados nunca é versionada.
2. **Comando `tde init`** (TECHNICAL_SPEC.md §3: "Cria a base de dados e aplica migrações"; escreve só o esquema):
   - base de dados inexistente → cria-a e aplica todas as migrações por ordem;
   - base existente → aplica apenas as migrações pendentes; sem pendentes, não altera nada (idempotente);
   - saída: `init: OK`, o caminho da base de dados e as migrações aplicadas nesta execução (eventualmente nenhuma), código `0`; em erro, `init: ERRO` e o motivo em stderr, código `1`, sem migração parcial;
   - erros: ficheiro que não é uma base SQLite; migração registada na base que o código não conhece (base mais recente que o código); migração aplicada cujo conteúdo foi alterado (checksum diferente); migração pendente com versão inferior à mais elevada já aplicada (quebraria a ordem só para a frente).
   - Não cria nenhum `run` nem nenhum registo de negócio. Não sincroniza `config/sources.yaml` (ver *YAML vs SQLite*). Não acede à rede.
   - `--dry-run`, `--verbose` e `--no-llm` não fazem parte do M2.6. `tde doctor` mantém-se sem acesso a base de dados nem a variáveis de ambiente.
3. **Estratégia de migrações (DEC-026).** Ficheiros SQL numerados, `storage/migrations/NNNN_<nome>.sql` (DATA_MODEL.md §4), começando em `0001_init.sql`, incluídos no pacote e lidos como recursos do pacote. Só para a frente: sem migrações de reversão; uma migração aplicada nunca é editada — qualquer alteração é uma migração nova. Cada migração é aplicada numa transacção, juntamente com o seu registo numa tabela de controlo `schema_migration` (`version` PK, `checksum` SHA-256 do ficheiro, `applied_at` em UTC); falha → rollback completo. Sem `PRAGMA user_version` (específico de SQLite).
4. **Esquema inicial — `0001_init.sql`** (ver *Esquema*): `schema_migration`, `run`, `source_registry`, `source_endpoint`, `raw_item`. `source_document` fica para uma migração posterior (motivo abaixo).
5. **Isolamento da camada SQL (DEC-013).** Todo o SQL e todo o uso de `sqlite3` vivem em `src/tensdireito_content_engine/storage/`. `domain/`, `normalize/` e `sources/` não importam `storage` nem `sqlite3`; a dependência é só `storage → domain`. A CLI chama funções de `storage`, sem SQL. O M2.6 implementa apenas a ligação (com `PRAGMA foreign_keys = ON` em cada ligação, configuração de ligação isolada em `storage`) e o executor de migrações; os repositórios de leitura/escrita de cada entidade chegam com as unidades que os consomem.
6. **Portabilidade futura para PostgreSQL (DEC-013).** O SQL das migrações usa só construções com equivalente directo em PostgreSQL: tipos `TEXT`, `INTEGER`, `REAL`; `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`. Não usa `AUTOINCREMENT`, `WITHOUT ROWID`, tabelas `STRICT`, `INSERT OR REPLACE`, `PRAGMA` dentro das migrações, nem valores por defeito dependentes do formato de data do SQLite (`CURRENT_TIMESTAMP`). Colunas `json` são `TEXT` com JSON válido (`JSONB` em PostgreSQL); datas são `TEXT` ISO 8601 em UTC com fuso explícito (`TIMESTAMPTZ` em PostgreSQL), escritas pela camada `storage` a partir de `datetime` com fuso. `created_at`/`updated_at` são preenchidos pela camada `storage` (relógio injectável nos testes), não pela base de dados. O M2.6 não cria migrações PostgreSQL, não instala driver PostgreSQL e não testa contra PostgreSQL (Fase 6).

**Esquema (a partir de [DATA_MODEL.md](DATA_MODEL.md) §2; nenhum campo novo de negócio):**

| Tabela | Na `0001` | Colunas | Restrições |
|--------|-----------|---------|------------|
| `schema_migration` | Sim | `version`, `checksum`, `applied_at` | PK `version`. Tabela técnica de controlo das migrações (DEC-026); não é entidade de negócio. |
| `run` | Sim | DATA_MODEL.md §2.9: `id`, `command`, `started_at`, `finished_at`, `status`, `stats` (json), `outcome`, `report_path`; `created_at`, `updated_at` (§4) | PK `id` (integer). |
| `source_registry` | Sim | DATA_MODEL.md §2.1: `id`, `name`, `entity_type`, `tier`, `categories` (json), `domains` (json), `registry_status`, `validated_at`, `validated_by`, `notes`; `created_at`, `updated_at` | PK `id` (text). |
| `source_endpoint` | Sim | DATA_MODEL.md §2.1: `id`, `source_id`, `endpoint_type`, `url`, `fetch` (json), `endpoint_status`, `validated_at`, `validated_by`, `last_success_at`, `last_error`; `created_at`, `updated_at` | PK `id` (text; único em todo o registo, como já valida o M2.5); FK `source_id` → `source_registry`. |
| `raw_item` | Sim | DATA_MODEL.md §2.1: `id`, `source_endpoint_id`, `url`, `external_id`, `title`, `raw_content`, `fetched_at`, `published_at_raw`, `content_hash`, `manual_note`, `created_in_run`; `created_at`, `updated_at` | PK `id` (integer); FK `source_endpoint_id` → `source_endpoint` (nulo para pistas manuais); FK `created_in_run` → `run`; `UNIQUE (source_endpoint_id, url, content_hash)`. |
| `source_document` | **Não** — migração posterior | — | Ver abaixo. |

Regras do esquema:
- Nulidade: `NOT NULL` só onde DATA_MODEL.md ou os invariantes dos modelos de domínio do M2.2/M2.3 já tornam o campo obrigatório (ex.: `url`, `title`, `raw_content`, `fetched_at`, `content_hash` em `raw_item`; `source_id`, `endpoint_type`, `endpoint_status` em `source_endpoint`); campos que a documentação marca como nulos ficam nulos. O esquema não enfraquece nem acrescenta invariantes.
- Os valores das enumerações são guardados no valor interno em minúsculas (DATA_MODEL.md, convenção de nomes; DEC-024) e validados pelos modelos de domínio antes de qualquer escrita. A `0001` não duplica as enumerações em `CHECK`.
- Índices além dos implicados por PK/UNIQUE não fazem parte da `0001`; entram com a unidade que os justifique.
- `created_in_run` aparece onde DATA_MODEL.md o lista explicitamente (`raw_item`). Em `source_registry`/`source_endpoint`, a sua aplicabilidade é decidida com a sincronização do registo.
- `published_at_raw` é guardado tal como obtido; o M2.6 não o interpreta (D13).
- Limitação conhecida, a tratar com `tde add-manual`: em SQLite e PostgreSQL, `NULL` em `source_endpoint_id` não colide numa restrição `UNIQUE`, pelo que a unicidade de `raw_item` não impede, sozinha, pistas manuais repetidas. O M2.6 cria a restrição como documentada e não resolve este caso.

**Porque `source_document` não entra na `0001`:** os campos que DATA_MODEL.md §2.1 e o modelo de domínio `SourceDocument` (M2.2) tornam obrigatórios ainda não têm regra de cálculo — `canonical_url` depende de D12 (OPEN; o M2.3 não o calcula), e `language`, `source_tier` e `document_kind` não são atribuídos pela normalização (DEC-021). Criar a tabela agora obrigaria a decidir a nulidade destas colunas — enfraquecendo o modelo de domínio ou bloqueando qualquer escrita — e a fixar nomes das colunas de classificação (`proposed_*`, `relevance_flag`, `classified_by`) antes da etapa que as usa. A tabela entra numa migração seguinte (`0002_…`), na unidade que persistir a etapa NORMALIZE, depois de essa unidade definir como trata `canonical_url` sob D12. A estratégia de migrações do M2.6 é o que permite acrescentá-la sem retrabalho.

**YAML vs SQLite (DEC-027):**
- `config/sources.yaml` continua a ser a **fonte de verdade** de `source_registry` e `source_endpoint` (DATA_MODEL.md §2.1; DEC-023). O M2.6 não altera essa decisão.
- As tabelas `source_registry` e `source_endpoint` são um **espelho operacional**: existem para que `raw_item.source_endpoint_id` e, depois, `source_document.source_id` tenham chaves estrangeiras, e para guardar o estado de execução que não pertence ao ficheiro versionado (`last_success_at`, `last_error`; DEC-023).
- Sincronização futura (fora do M2.6): **unidireccional YAML → SQLite**, por comando explícito e local, só depois de o registo passar as regras de `tde sources validate`; actualiza os campos do YAML pelo `id`; preserva os campos operacionais; nunca escreve no YAML. O tratamento de fontes/endpoints retirados do YAML é decidido nessa unidade, sem apagar linhas referenciadas por `raw_item` (DATA_MODEL.md §4: nada usado como evidência é apagado).
- Uma alteração a uma fonte faz-se no YAML, por pull request; nunca directamente na base de dados.
- No M2.6, `source_registry` e `source_endpoint` ficam vazias: `tde init` não as preenche e nenhuma fonte é inserida.

**Persistência e D8:** o M2.6 permite persistência SQLite **local**, para execução manual. Não resolve D8: um SQLite local num runner efémero continua a não ser solução para execução agendada nem para estado partilhado (DEC-013). A base de dados não é versionada, não é artefacto de CI e não é partilhada. D8 continua OPEN e bloqueante para a Fase 5.

**D1, D12 e D13:** continuam OPEN. O M2.6 não os desbloqueia nem os decide: não insere fontes, endpoints, URLs nem `domains` (D1); não calcula nem guarda `canonical_url` (D12); não interpreta `published_at_raw` nem assume fuso (D13).

**Exclusões:** collectors; RSS, HTTP e HTML; scraping; qualquer acesso à rede; fornecedores de IA; execução agendada e GitHub Actions; publicação; sincronização de `config/sources.yaml` para SQLite; escrita de `raw_item`, `run` ou fontes por qualquer comando; repositórios por entidade; tabela `source_document`; `event`, `event_document`, `claim`, `source_evidence`, `score`, `content_piece`, `editorial_decision`, `llm_call`; migrações e driver PostgreSQL; ORM; `--dry-run`; resolução de D1, D8, D12 e D13. Não altera os modelos de domínio, a normalização, a deduplicação nem `tde sources validate`.

**Critérios de aceitação (verificáveis na implementação):**
1. **Criação inicial:** `tde init` sem base de dados cria o ficheiro no caminho resolvido (`--db`, depois `TDE_DB_PATH`, depois `data/tde.sqlite3`), cria o directório pai se faltar, aplica a `0001` e termina com código `0`.
2. **Idempotência:** uma segunda execução de `tde init` termina com código `0`, não aplica nenhuma migração e não altera o esquema nem `schema_migration`.
3. **Migrações:** com migrações fictícias em teste, só as pendentes são aplicadas, por ordem numérica; uma migração que falha não deixa alterações nem registo em `schema_migration`; uma migração aplicada com checksum diferente, uma versão registada desconhecida do código e uma migração pendente com versão inferior à mais elevada já aplicada terminam com código `1`; um ficheiro que não é SQLite termina com código `1`.
4. **Esquema esperado:** após `0001`, existem exactamente `schema_migration`, `run`, `source_registry`, `source_endpoint` e `raw_item`, com as colunas, PK, FK, `UNIQUE` e `NOT NULL` desta secção; `source_document` não existe; as FK são aplicadas (inserir `raw_item` com `source_endpoint_id` inexistente falha); todas as tabelas de negócio ficam vazias.
5. **Isolamento SQL:** um teste confirma que `sqlite3` só é importado em `storage/` e que `domain/`, `normalize/` e `sources/` não importam `storage`.
6. **Portabilidade:** um teste confirma que os ficheiros de migração não contêm `AUTOINCREMENT`, `WITHOUT ROWID`, `STRICT`, `INSERT OR REPLACE`, `PRAGMA` nem `CURRENT_TIMESTAMP`; colunas json e datas são `TEXT`.
7. **Determinismo:** a mesma sequência de migrações produz o mesmo esquema (comparado sem `applied_at`); datas escritas pela camada `storage` estão em UTC ISO 8601 com fuso.
8. **CLI:** `tde init` aparece em `tde --help`; `tde doctor` e `tde sources validate` mantêm o comportamento actual.
9. **Testes offline:** todos os testes usam bases de dados em directórios temporários, sem rede, sem fornecedor de IA e sem fontes nem URLs reais (TECHNICAL_SPEC.md §6, Testabilidade); nenhum teste escreve em `data/`.
10. **Validação do repositório:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` e `uv run tde doctor` passam.

**Testes:** offline, com fixtures (bases de dados temporárias e migrações fictícias para os casos de erro), sem rede e sem fornecedor de IA, conforme TECHNICAL_SPEC.md §6.

**Dependências:** nenhuma prevista — `sqlite3` faz parte da biblioteca padrão (TECHNICAL_SPEC.md §1). Se a implementação vier a exigir alguma, tem de ser justificada no PR de implementação e registada em TECHNICAL_SPEC.md §7; nenhuma é adicionada nesta definição.

**Implementação:** `src/tensdireito_content_engine/storage/` — `database.py` (resolução do caminho `--db` → `TDE_DB_PATH` → `data/tde.sqlite3`, com valor vazio tratado como ausente; ligação com `PRAGMA foreign_keys = ON` e transacções explícitas; recusa de directório ou ficheiro sem cabeçalho SQLite; datas UTC ISO 8601 com `+00:00`), `migrator.py` (leitura de `migrations/NNNN_<nome>.sql` como recursos do pacote, checksum SHA-256 dos bytes do ficheiro, verificação das migrações aplicadas e aplicação de cada pendente numa transacção com o seu registo em `schema_migration`), `init.py` (`init_database`) e `migrations/0001_init.sql`. `tde [--db PATH] init` em `cli.py` escreve `init: OK — <caminho>` e `migrações aplicadas: <nomes>` (ou `nenhuma`), código `0`; em erro, `init: ERRO — <caminho>` e `- <motivo>` em stderr, código `1`. Além dos erros do contrato, também terminam em erro: nome de ficheiro de migração fora do formato e versão repetida. Nulidade na `0001`: `NOT NULL` nos campos obrigatórios do domínio (M2.2/M2.3) e em `created_at`/`updated_at`, sempre preenchidos pela camada `storage`; `run.*` (sem modelo de domínio) e `raw_item.created_in_run` ficam nulos. Sem dependências novas.

## Fase 0 — Arquitectura e documentação *(actual)*

- [x] Documentação técnica inicial em `docs/`.
- [x] Revisão e aprovação da arquitectura.
- [x] M1 — decisões fundamentais fechadas e registadas em [DECISION_LOG.md](DECISION_LOG.md).
- [ ] Decisões pendentes restantes resolvidas ou explicitamente adiadas (ver abaixo).

**Critério de saída:** documentação aprovada; lista de fontes T1 prioritárias acordada (D1).

## Fase 1 — Fundação e recolha (manual)

- Projecto Python gerido com `uv` (`pyproject.toml`, `uv.lock`), pacote `tensdireito_content_engine`, CLI `tde`, `ruff`, `pytest`.
- Camada `storage` com SQLite e migrações numeradas para `source_registry`, `source_endpoint`, `raw_item`, `source_document` e `run`: a migração inicial (M2.6) cobre `run`, `source_registry`, `source_endpoint` e `raw_item`; `source_document` entra numa migração seguinte, com a persistência da etapa NORMALIZE (DEC-026).
- Registo de fontes + `tde sources validate`.
- Collectors `rss`, `html_page`, `manual` — apenas para endpoints validados.
- NORMALIZE com deduplicação exacta.
- Validação manual de 5–10 fontes (prioridade T1), registando endpoints reais só após confirmação.
- Relatório mínimo da execução.

**Critério de saída:** `tde collect && tde normalize` corre localmente, de forma idempotente, sobre as fontes validadas; testes offline com fixtures.

## Fase 2 — Classificação, agrupamento e pontuação

- `taxonomy.yaml` (taxonomia V1) e CLASSIFY por regras.
- Interface `LLMProvider` + `NullProvider` + primeira implementação de fornecedor (após D3).
- CLASSIFY assistida por IA.
- CLUSTER com actualização de eventos existentes (similaridade lexical + sinais fortes).
- SCORE com `scoring.yaml` (sem componente de verificação) e relatório, incluindo "nada suficientemente importante para publicar".
- Calibração com 2–4 semanas de dados reais.

**Critério de saída:** `tde run` produz relatório útil com eventos ordenados; editor confirma que a ordenação é razoável.

## Fase 3 — Verificação e rastreabilidade

- Entidades `claim` e `source_evidence`, com `legal_stage`.
- Extracção de claims e associação a evidência com validação literal de excertos.
- Cálculo determinista de `VERIFIED_OFFICIAL` / `VERIFIED_EDITORIAL` / `UNVERIFIED` / `CONTRADICTED`.
- Gate de verificação na proposta editorial; watchlist com motivos.
- Comandos de override (limitado), evidência manual e fusão de eventos.

**Critério de saída:** nenhum evento chega a `EDITORIAL_REVIEW` sem passar o gate de verificação; nenhuma claim é `VERIFIED_OFFICIAL` sem evidência T1 validada e adequada ao estágio.

## Fase 4 — Produção editorial e revisão humana

- GENERATE para `whatsapp`, `article`, `seo_meta`, segundo o [STYLE_GUIDE.md](STYLE_GUIDE.md).
- Validações automáticas pós-geração (incluindo estágio legal e atribuição).
- REVIEW (`APPROVED`, `REJECTED`, `NEEDS_REVISION`, com revisor, data e nota) e EXPORT.

**Critério de saída:** fluxo completo manual, de recolha a conteúdo `APPROVED` exportado, com rastreabilidade claim → fonte. Sem publicação automática.

## Fase 5 — Automação

**Pré-requisito bloqueante:** antes de activar qualquer execução agendada via GitHub Actions, tem de ser tomada e registada no [DECISION_LOG.md](DECISION_LOG.md) uma decisão sobre **persistência durável e estado partilhado** (D8). Um SQLite local num runner efémero **não** é solução suficiente para produção: o estado perde-se entre execuções e não é partilhado com a revisão humana.

- Workflow GitHub Actions agendado para `tde run`.
- Persistência conforme a decisão D8.
- Notificação com o relatório da execução.

**Critério de saída:** execuções agendadas estáveis durante 2 semanas sem intervenção; geração e revisão continuam manuais.

## Fase 6 — Evolução (a avaliar)

- Migração para PostgreSQL.
- Formatos `newsletter` e `social_post`.
- Integração de publicação (ex.: CMS do TensDireito.com) e uso do estado `PUBLISHED` — requer decisão.
- Recolha automatizada de redes sociais — requer decisão (termos, custo, RGPD).
- Calibração de pesos por categoria, audiência, histórico de desempenho e tipo de notícia.
- Similaridade semântica (embeddings) para clustering.
- Interface de revisão web com autenticação.

## Decisões pendentes

| # | Decisão | Fase | Estado / notas |
|---|---------|------|----------------|
| D1 | Fontes T1 prioritárias e confirmação de endpoints reais de cada uma | 1 | **Pendente (OPEN).** Lista candidata em [SOURCES.md](SOURCES.md). Só será fechada quando as fontes prioritárias e os respectivos endpoints forem validados manualmente; nenhum URL, feed, RSS ou API é assumido até lá. |
| D2 | Selecção de fontes T2/T3 (imprensa) | 1–2 | **Pendente.** Decisão editorial. |
| D3 | Fornecedor(es) de IA inicial(is) e orçamento mensal | 2 | **Pendente.** Interface agnóstica já definida. |
| D4 | Âmbito temático (taxonomia) | 2 | **Fechada no M1** — taxonomia V1 extensível (DEC-006). |
| D5 | Verificação na ausência de fonte oficial | 3 | **Fechada no M1** — máximo `VERIFIED_EDITORIAL`; override nunca produz `VERIFIED_OFFICIAL` (DEC-004). |
| D6 | Guia de estilo por formato | 4 | **Fechada no M1** — [STYLE_GUIDE.md](STYLE_GUIDE.md) (DEC-008); nota de responsabilidade proporcional ao risco (DEC-018). |
| D7 | Quem revê e aprova | 4 | **Parcialmente fechada** — formato do registo de revisão definido (DEC-014); pessoas concretas e eventual autenticação a decidir. |
| D8 | Persistência durável e estado partilhado em modo agendado (ex.: storage externo, PostgreSQL gerido) | **Antes da Fase 5** | **Pendente e bloqueante** para qualquer execução agendada (DEC-013). O M2.6 (SQLite local) não a resolve. |
| D9 | Frequência das execuções agendadas | 5 | **Pendente.** |
| D10 | Destino de publicação e integração com o TensDireito.com | 6 | **Pendente.** Na V1 apenas exportação de ficheiros. |
| D11 | Norma ortográfica do conteúdo publicado | 4 | **Fechada no M1 (CLOSED)** — AO1990, variante europeia, para todo o conteúdo público; documentação interna fora do âmbito; citações, legislação e nomes oficiais preservados (DEC-017). |
| D12 | Regra de `canonical_url`: que parâmetros são "de tracking" e se se normalizam esquema, domínio, barra final ou fragmento | 1 | **Pendente (OPEN).** DATA_MODEL.md exige `canonical_url` "sem parâmetros de tracking" sem os enumerar. Não se inventa nem assume nenhuma lista de parâmetros. Até decisão, o M2.3 não calcula `canonical_url` e preserva o URL tal como obtido (DEC-021). |
| D13 | Formatos aceites em `published_at_raw` e tratamento de data sem hora ou data/hora sem fuso | 1 | **Pendente (OPEN).** Nenhum fuso (incluindo `Europe/Lisbon`) é assumido silenciosamente. Até decisão, só ISO 8601 com fuso explícito é convertido para UTC; os restantes casos ficam nulos, com o original preservado (DEC-021). |
