# Roadmap

> Estado actual: **Fase 0 — Architecture / Documentation phase.** Milestone M1 (fecho das decisões arquitecturais e editoriais) concluído com o PR do M1, depois de revisto. M2 em curso: M2.1 (fundação executável), M2.2 (modelos de domínio), M2.3 (normalização e identidade) e M2.4 (deduplicação exacta por `text_hash`) concluídos e integrados (M2.3 no PR #5, M2.4 no PR #6); M2.5 (registo de fontes e validação de fontes) concluído e integrado (PR #8); M2.6 (storage SQLite e migração inicial) concluído e integrado (PR #10); M2.7 (sincronização explícita de `sources.yaml` para SQLite) concluído e integrado (PR #12); M2.8 (recolha local: ciclo de vida de `run`, persistência de `raw_item` e contrato `Collector`) concluído e integrado (PR #14); M2.9 (primeiro collector concreto: `rss`, com transporte HTTPS restrito) concluído e integrado (PR #16); M2.10 (validação de fontes) concluído e integrado (PR #18); M2.11 (persistência da etapa NORMALIZE) concluído e integrado (PR #20); M2.12 (definição documental de CLASSIFY rules-only) concluída, com implementação pendente. A validação real das primeiras fontes (D1) continua por fazer e continua a bloquear fontes reais e os gates de fase; não é um bloqueio técnico para especificar, implementar ou testar CLASSIFY com fixtures sintéticas.

Cada fase termina com critérios de saída verificáveis. Uma fase só começa quando os critérios da anterior estão cumpridos e as decisões pendentes relevantes estão tomadas.

## Milestones

| Milestone | Âmbito | Estado |
|-----------|--------|--------|
| Prompt 1 | Documentação inicial da arquitectura e especificação técnica. | Concluído |
| **M1** | Decisões arquitecturais e editoriais fundamentais: modelo de verificação, taxonomia V1, modelo de fontes, guia de estilo, política editorial, revisão humana, separação score/verificação, estados editoriais, persistência, tooling, decision log. Apenas documentação. | **Concluído com o PR do M1, depois de revisto** |
| M2 | Implementação por unidades: M2.1 fundação executável; M2.2 modelos de domínio; M2.3 normalização e identidade (DEC-021); M2.4 deduplicação exacta por `text_hash` (DEC-022) — usa o `text_hash` do M2.3, faz apenas deduplicação exacta, sem clustering nem deduplicação aproximada; M2.5 registo de fontes e validação de fontes (ver [M2.5](#m25--registo-de-fontes-e-validação-de-fontes)); M2.6 storage SQLite e migração inicial (ver [M2.6](#m26--storage-sqlite-e-migração-inicial)); M2.7 sincronização explícita de `sources.yaml` para SQLite (DEC-028, DEC-029; ver [M2.7](#m27--sincronização-explícita-de-sourcesyaml-para-sqlite)); M2.8 recolha local: ciclo de vida de `run`, persistência de `raw_item` e contrato `Collector`, sem collectors concretos nem rede (DEC-031; ver [M2.8](#m28--recolha-local-ciclo-de-vida-de-run-persistência-de-raw_item-e-contrato-collector)); M2.9 primeiro collector concreto, `rss` (RSS 2.0), com transporte HTTPS restrito, sem endpoints reais (DEC-032, DEC-033; ver [M2.9](#m29--primeiro-collector-concreto-rss-com-transporte-https-restrito)). M2.10 validação de fontes: processo, registo de evidência e regra automática "endpoint `ACTIVE` só em fonte `VALIDATED`", sem validar fontes reais (DEC-035, DEC-036; ver [M2.10](#m210--validação-de-fontes)). A validação manual das primeiras fontes (D1) é actividade posterior ao M2.10, segundo DEC-034 e DEC-036. M2.11 persistência da etapa NORMALIZE: `source_document`, migração `0002` e `tde normalize` (DEC-037 a DEC-041; ver [M2.11](#m211--persistência-da-etapa-normalize)). M2.12 definição documental de CLASSIFY rules-only (ver [M2.12](#m212--classify-rules-only-definição-documental)). | **Em curso** — M2.1 a M2.11 concluídos e integrados (M2.4 no PR #6, M2.5 no PR #8, M2.6 no PR #10, M2.7 no PR #12, M2.8 no PR #14, M2.9 no PR #16, M2.10 no PR #18 e M2.11 no PR #20); M2.12 — CLASSIFY rules-only: definição documental concluída / implementação pendente (esta definição aguarda integração) |

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

**Estado:** concluído e integrado (PR #10). Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção.

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
- `created_in_run` aparece onde DATA_MODEL.md o lista explicitamente (`raw_item`). Em `source_registry`/`source_endpoint`, a sua aplicabilidade é decidida com a sincronização do registo. (Decidido no M2.7: não se aplica — DEC-028.)
- `published_at_raw` é guardado tal como obtido; o M2.6 não o interpreta (D13).
- Limitação conhecida, a tratar com `tde add-manual`: em SQLite e PostgreSQL, `NULL` em `source_endpoint_id` não colide numa restrição `UNIQUE`, pelo que a unicidade de `raw_item` não impede, sozinha, pistas manuais repetidas. O M2.6 cria a restrição como documentada e não resolve este caso.

**Porque `source_document` não entra na `0001`:** os campos que DATA_MODEL.md §2.1 e o modelo de domínio `SourceDocument` (M2.2) tornam obrigatórios ainda não têm regra de cálculo — `canonical_url` depende de D12 (OPEN; o M2.3 não o calcula), e `language`, `source_tier` e `document_kind` não são atribuídos pela normalização (DEC-021). Criar a tabela agora obrigaria a decidir a nulidade destas colunas — enfraquecendo o modelo de domínio ou bloqueando qualquer escrita — e a fixar nomes das colunas de classificação (`proposed_*`, `relevance_flag`, `classified_by`) antes da etapa que as usa. A tabela entra numa migração seguinte (`0002_…`), na unidade que persistir a etapa NORMALIZE, depois de essa unidade definir como trata `canonical_url` sob D12. A estratégia de migrações do M2.6 é o que permite acrescentá-la sem retrabalho.

**YAML vs SQLite (DEC-027):**
- `config/sources.yaml` continua a ser a **fonte de verdade** de `source_registry` e `source_endpoint` (DATA_MODEL.md §2.1; DEC-023). O M2.6 não altera essa decisão.
- As tabelas `source_registry` e `source_endpoint` são um **espelho operacional**: existem para que `raw_item.source_endpoint_id` e, depois, `source_document.source_id` tenham chaves estrangeiras, e para guardar o estado de execução que não pertence ao ficheiro versionado (`last_success_at`, `last_error`; DEC-023).
- Sincronização futura (fora do M2.6): **unidireccional YAML → SQLite**, por comando explícito e local, só depois de o registo passar as regras de `tde sources validate`; actualiza os campos do YAML pelo `id`; preserva os campos operacionais; nunca escreve no YAML. O tratamento de fontes/endpoints retirados do YAML é decidido nessa unidade, sem apagar linhas referenciadas por `raw_item` (DATA_MODEL.md §4: nada usado como evidência é apagado). Decidido no M2.7 (DEC-029).
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

### M2.7 — sincronização explícita de `sources.yaml` para SQLite

**Estado:** concluído e integrado (PR #12). Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção. Decisões: DEC-027 (fonte de verdade e sentido da sincronização), DEC-028 (contrato da sincronização), DEC-029 (identidade e reconciliação) e DEC-030 (estado de validação operacional sem `editorial_decision`).

**Objectivo:** projectar o registo de fontes validado de `config/sources.yaml` nas tabelas `source_registry` e `source_endpoint` criadas pela `0001` (M2.6), através de um comando explícito e local. O SQLite é o **espelho operacional dos campos do registo actualmente projectados pelo domínio/storage** — não é um espelho completo do YAML (ver *Campos*). As tabelas existem para as chaves estrangeiras de `raw_item` e para o estado de execução (DEC-027).

**Fonte de verdade (DEC-027):**
- `config/sources.yaml` continua a ser a fonte de verdade de fontes e endpoints.
- A sincronização é **unidireccional YAML → SQLite** e nunca escreve no YAML. Alterações manuais no SQLite não chegam ao YAML; nos campos projectados, são sobrescritas na sincronização seguinte.
- A sincronização só opera sobre um registo que passe as regras de `tde sources validate`, usando a mesma leitura e validação do M2.5, sem regras paralelas.

**Âmbito (entregáveis da implementação):**

1. **Comando `tde [--config DIR] [--db PATH] sources sync`** (DEC-028). É a única operação que escreve fontes e endpoints na base de dados. `tde init` continua a não sincronizar fontes (M2.6). Local, sem rede.
2. **Pré-condições, verificadas antes de qualquer escrita** (DEC-028):
   - YAML inválido → `sources sync: ERRO`, com os mesmos erros de `tde sources validate`, código `1`; a base de dados não é alterada.
   - Base de dados inexistente no caminho resolvido (`--db`, depois `TDE_DB_PATH`, depois `data/tde.sqlite3`) → erro, código `1`, pedindo `tde init`. O sync **não cria** a base de dados nem o directório pai. Nota para a implementação: `storage.connect()` cria hoje o ficheiro se não existir; a existência tem de ser verificada antes de abrir qualquer ligação.
   - Esquema não conforme (ficheiro que não é SQLite, migrações pendentes, migração registada desconhecida do código, checksum diferente) → erro, código `1`, pedindo `tde init`. O sync **não aplica** migrações.
3. **Reconciliação pelo `id`** (ver *Identidade e reconciliação*): insere, actualiza, mantém inalteradas ou remove linhas, sem duplicados.
4. **Transacção única** (DEC-028): toda a sincronização corre numa transacção explícita. Qualquer erro ou conflito de reconciliação → rollback integral; nunca fica estado parcialmente sincronizado. Os conflitos são detectados antes de escrever e listados todos.
5. **Saída determinística** (DEC-028): `sources sync: OK — <caminho>` e as contagens de inseridos, actualizados, inalterados e removidos, código `0`; em erro, `sources sync: ERRO — <caminho>` e `- <motivo>` (todos os motivos) em stderr, código `1`. O código `2` (sucesso parcial) não se aplica.
6. **Repositório em `storage`**: as leituras e escritas de `source_registry` e `source_endpoint` vivem em `src/tensdireito_content_engine/storage/` (M2.6, regra 5). `storage` recebe objectos de `domain` (`SourceRegistry`, `SourceEndpoint`) e não importa `sources`; a CLI lê o registo com `sources` e chama `storage`, sem SQL.

**Identidade e reconciliação (DEC-029):**

| Situação | Regra |
|----------|-------|
| Correspondência de fonte | `source_registry.id` = `id` da fonte no YAML. |
| Correspondência de endpoint | `source_endpoint.id` = `id` do endpoint no YAML (único em todo o registo, M2.5). |
| IDs | Não há identificadores substitutos: o PK é o `id` do YAML e é preservado. Mudar um `id` no YAML equivale a remover a entrada antiga e inserir uma nova (sujeito às regras de remoção). |
| Duplicados | Impossíveis: o PK impede-os e o M2.5 já recusa IDs repetidos. |
| Entrada nova no YAML | Inserida. |
| Campo projectado alterado | Actualizado pelo `id`; os campos operacionais são preservados. |
| Fonte ou endpoint removido do YAML, **sem** `raw_item` a referenciá-lo | Removido do SQLite. Uma fonte removida arrasta a avaliação de cada um dos seus endpoints removidos. |
| Fonte ou endpoint removido do YAML, **com** `raw_item` a referenciá-lo (directamente ou por um endpoint da fonte) | A sincronização falha e nada é removido (rollback integral). Não se força `INACTIVE` no SQLite nem se acrescenta uma coluna de "removido": para retirar uma entrada já usada, mantém-se no YAML (por exemplo, como `INACTIVE`). Nada usado como evidência é apagado (DATA_MODEL.md §4). |
| Endpoint existente muda `source_id` ou `endpoint_type`, **sem** `raw_item` a referenciá-lo | A alteração é aplicada. |
| Endpoint existente muda `source_id` ou `endpoint_type`, **com** `raw_item` a referenciá-lo | A sincronização falha; exige-se um endpoint novo, com `id` novo. A proveniência histórica de `raw_item` nunca é reinterpretada retroactivamente. |
| Ordem das escritas | Inserir/actualizar fontes → inserir/actualizar endpoints → remover endpoints → remover fontes (compatível com a FK `source_endpoint.source_id`, sem `ON DELETE`). |

**Campos:**

| Tabela | Projectados do YAML (sobrescritos) | Operacionais (nunca tocados pelo sync) | Geridos pela `storage` | Fora da projecção do M2.7 |
|--------|------------------------------------|----------------------------------------|------------------------|---------------------------|
| `source_registry` | `id`, `name`, `entity_type`, `tier`, `categories`, `domains`, `registry_status`, `validated_at`, `validated_by`, `notes` | — | `created_at` (só na inserção); `updated_at` | — |
| `source_endpoint` | `id`, `source_id`, `endpoint_type`, `url`, `endpoint_status`, `validated_at`, `validated_by` | `last_success_at`, `last_error` | `created_at` (só na inserção); `updated_at` | `fetch` |

- Valores guardados como no M2.6: estados no valor interno em minúsculas (DEC-024), datas em UTC ISO 8601 com fuso explícito, listas em JSON (`TEXT`).
- `updated_at` só muda quando um campo projectado muda efectivamente (comparação na forma guardada). Uma sincronização sem alterações não escreve nada nem altera timestamps (DEC-028).
- `last_success_at` e `last_error` mantêm-se em qualquer actualização, incluindo mudança de `url` ou de estado (DEC-023, DEC-027).
- **`fetch` — limitação deliberada** (DEC-028): o M2.5 não transporta `fetch` para o domínio e o M2.7 não altera o domínio nem reabre o M2.5 para o transportar. A coluna `source_endpoint.fetch` fica nula; uma alteração apenas em `fetch` no YAML não é detectada nem conta como actualização. Uma unidade futura que precise de `fetch` (ex.: collectors) define primeiro o seu transporte no domínio.

**Rastreabilidade por `run`** (DEC-028): o M2.7 não cria `run`, não acrescenta `created_in_run` e não altera o esquema. `source_registry` e `source_endpoint` não têm relação com `run` no modelo actual (TECHNICAL_SPEC.md §6, Rastreabilidade).

**Validação de fontes e `editorial_decision`** (DEC-030): nesta fase, `validated_at` e `validated_by` do registo constituem o estado de validação operacional de uma fonte ou endpoint `VALIDATED`/`ACTIVE`. O sync espelha esses campos tal como passam em `tde sources validate`; não cria nem exige `editorial_decision`. A decisão `VALIDATE_SOURCE` fica para a unidade futura que introduzir `editorial_decision`, que pode rever esta regra.

**Portabilidade (DEC-013):** todo o SQL em `storage/`; sem ORM; só `SELECT`, `INSERT`, `UPDATE` e `DELETE` simples, com equivalente directo em PostgreSQL; sem `INSERT OR REPLACE` (apagar e reinserir destruiria os campos operacionais e violaria as FK), sem `PRAGMA` fora da configuração da ligação e sem construções exclusivas de SQLite. Sem migrações novas.

**Dependências:** M2.5 (`load_sources`, regras de validação, IDs únicos); M2.6 (`0001`, `schema_migration`, verificação de migrações, resolução do caminho da base de dados). Nenhuma dependência externa nova.

**D1, D8, D12 e D13:** continuam OPEN e não são afectados. Com `config/sources.yaml` vazio (`[]`, por D1), o sync não tem efeito real até D1; o comportamento verifica-se com fixtures. O sync não insere fontes por suposição.

**Exclusões:** collectors; RSS, HTTP e HTML; qualquer acesso à rede; conteúdo do registo (D1); `source_document`; NORMALIZE; D12; D13; IA; publicação; execução agendada e GitHub Actions; persistência durável/distribuída (D8); PostgreSQL; sincronização SQLite → YAML; criação da base de dados ou aplicação de migrações pelo sync; migrações, tabelas ou colunas novas; `fetch`; `run` e `created_in_run`; `editorial_decision`; `--dry-run`; escrita de `raw_item`. Não altera `tde sources validate`, o domínio, o formato do YAML, `tde init` nem `tde doctor`.

**Critérios de aceitação (verificáveis na implementação):**
1. **Sincronização inicial:** um YAML válido (fixture) sincroniza para uma base criada por `tde init`; os campos projectados correspondem aos objectos de domínio (estados em minúsculas, datas UTC com `+00:00`, listas em JSON); `fetch` fica nulo.
2. **Idempotência:** uma segunda execução termina com código `0`, contagens `0` inseridos, `0` actualizados, `N` inalterados, `0` removidos, sem escrita; `created_at` e `updated_at` mantêm-se.
3. **Actualização:** alterar um campo projectado no YAML reflecte-se pelo `id`; `updated_at` muda só nessa linha; `created_at` mantém-se.
4. **`fetch`:** uma alteração apenas em `fetch` não gera actualização e a coluna continua nula.
5. **Estado operacional:** `last_success_at` e `last_error` preenchidos por fixture mantêm-se após qualquer sincronização, incluindo mudança de `url` ou de estado.
6. **Remoção sem referências:** fonte ou endpoint retirado do YAML é apagado e contado em removidos.
7. **Remoção com referências:** entrada referenciada por `raw_item` (fixture) → código `1`, nada removido, base inalterada.
8. **Mudança estrutural:** mudar `source_id` ou `endpoint_type` de um endpoint referenciado → código `1`, base inalterada; sem referências, a alteração é aplicada.
9. **YAML inválido:** código `1`, com os mesmos erros de `tde sources validate`; base inalterada.
10. **Atomicidade:** uma falha injectada a meio da escrita deixa a base igual ao estado anterior.
11. **Base inexistente:** código `1`, pedindo `tde init`; nenhum ficheiro nem directório criado.
12. **Esquema não conforme:** migrações pendentes, desconhecidas ou com checksum diferente → código `1`, pedindo `tde init`; nenhuma migração aplicada.
13. **Fonte de verdade:** o YAML não é modificado (checksum antes e depois); uma edição manual de um campo projectado no SQLite é revertida pela sincronização seguinte.
14. **Sem `run`:** o sync não cria linhas em `run` nem altera o esquema.
15. **Isolamento e portabilidade:** `sqlite3` só em `storage/`; `storage` não importa `sources`; sem `INSERT OR REPLACE` nem construções exclusivas de SQLite nas consultas novas.
16. **CLI:** `tde sources sync` aparece em `tde sources --help`; `tde doctor`, `tde init` e `tde sources validate` mantêm o comportamento.
17. **Testes offline:** bases de dados em directórios temporários, sem rede, sem fornecedor de IA e sem fontes nem URLs reais; nenhum teste escreve em `data/`.
18. **Validação do repositório:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` e `uv run tde doctor` passam.

**Implementação:** `src/tensdireito_content_engine/storage/source_sync.py` (`sync_sources`) e `tde [--config DIR] [--db PATH] sources sync` em `cli.py`. A CLI lê o registo com `load_sources` (M2.5) e passa os objectos de domínio a `storage`, sem SQL; `storage` não importa `sources`. Ordem: (1) YAML inválido → `sources sync: ERRO — <caminho do YAML>` e os mesmos erros de `tde sources validate`, sem abrir a base de dados; (2) base inexistente → erro antes de `connect()`, sem criar ficheiro nem directório; (3) esquema verificado com as funções do executor de migrações (`applied_migrations`/`pending_migrations`), sem aplicar nenhuma — os erros são prefixados por `esquema não conforme:` e pedem `tde init`; (4) numa transacção explícita (`BEGIN` … `COMMIT`), leitura dos campos projectados existentes e dos endpoints referenciados por `raw_item`, cálculo do plano (inserir/actualizar/inalterado/remover, comparando na forma guardada) e de todos os conflitos de DEC-029; havendo conflitos, `ROLLBACK` sem nenhuma escrita; senão, escritas pela ordem de DEC-029 e `COMMIT`; qualquer erro SQLite → `ROLLBACK`. `UPDATE` só nas colunas projectadas e `updated_at`; `INSERT` com `fetch`, `last_success_at` e `last_error` nulos e `created_at` = `updated_at`; `DELETE` só das entradas retiradas sem referências. Listas guardadas com `json.dumps` (UTF-8, sem escape). Saída: `sources sync: OK — <caminho da base>` e as linhas `inseridos`, `actualizados`, `inalterados`, `removidos` (totais de fontes e endpoints), código `0`; em erro, `sources sync: ERRO — <caminho>` e `- <motivo>` por motivo em stderr, código `1`, em que `<caminho>` é o do YAML quando o YAML é inválido e o da base de dados nos restantes erros. Sem migrações nem dependências novas.

### M2.8 — recolha local: ciclo de vida de `run`, persistência de `raw_item` e contrato `Collector`

**Estado:** concluído e integrado (PR #14). Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção. Decisão: DEC-031 (contrato de `tde collect` e ciclo de vida de `run`). Respeita DEC-013, DEC-021, DEC-026, DEC-027, DEC-028, DEC-029 e DEC-030.

**Objectivo:** implementar a infra-estrutura e a orquestração da etapa COLLECT ([CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-1--collect), etapa 1) sem rede: abrir e fechar um `run`, seleccionar os endpoints `ACTIVE` do espelho SQLite, chamar o `Collector` registado para o `endpoint_type` de cada um, persistir de forma idempotente os `RawItem` devolvidos, com `created_in_run`, e actualizar o estado operacional do endpoint (`last_success_at`, `last_error`). O M2.8 **não** implementa nenhum collector concreto nem transporte de rede: em produção, o registo de collectors fica vazio; os testes usam collectors falsos.

**Âmbito (entregáveis da implementação):**

1. **Contrato `Collector`** ([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#41-collector) §4.1), em `src/tensdireito_content_engine/collectors/base.py`: atributo `endpoint_type` e `fetch(endpoint, since) -> Iterable[RawItem]`. `endpoint` é o `SourceEndpoint` de domínio; `RawItem` é o modelo de domínio do M2.3 (corresponde ao `RawItemIn` da especificação; não há entidade nova). `collectors/` depende só de `domain`: não importa `storage` nem `sqlite3`. No M2.8, `since` é sempre `None`.
2. **Registo de collectors por `endpoint_type`:** mecanismo que associa cada `endpoint_type` a, no máximo, um `Collector`. Na configuração de produção fica vazio; os testes injectam collectors falsos. Nenhum collector `rss`, `html_page` ou `manual` é implementado.
3. **Comando `tde [--db PATH] collect [--source ID]`** (DEC-031). Local, sem rede. `--since` não faz parte do M2.8 e não é aceite pela CLI; `--dry-run` também não.
4. **Persistência em `storage`:** criação e finalização de `run`; leitura dos endpoints `ACTIVE`, devolvidos como `SourceEndpoint` de domínio; inserção idempotente de `raw_item`; actualização de `last_success_at` e `last_error`. Todo o SQL fica em `src/tensdireito_content_engine/storage/` (M2.6, regra 5); `storage` continua a depender só de `domain` e não importa `collectors` nem `sources`.
5. **Orquestração** fora de `storage` e de `collectors` (na CLI ou num módulo próprio), sem SQL: liga a selecção de endpoints, o registo de collectors e a persistência.

**Pré-condições, verificadas por esta ordem antes de criar o `run`** (DEC-031):
- Base de dados inexistente no caminho resolvido (`--db`, depois `TDE_DB_PATH`, depois `data/tde.sqlite3`) → erro, código `1`, pedindo `tde init`. A existência é verificada antes de abrir qualquer ligação, como no M2.7: não se cria ficheiro nem directório.
- Esquema não conforme (ficheiro que não é SQLite, migrações pendentes, migração registada desconhecida do código, checksum diferente) → erro, código `1`, pedindo `tde init`, com a mesma verificação do M2.7. Nenhuma migração é aplicada.
- `--source ID` indicado e sem linha correspondente em `source_registry` → erro, código `1`.
- Numa falha de pré-condição, não se cria `run` e a base de dados não é alterada.
- O comando não lê `config/sources.yaml` nem sincroniza implicitamente (DEC-028): opera sobre o espelho SQLite tal como está. Manter o espelho actualizado com `tde sources sync` é responsabilidade de quem opera.

**Selecção de endpoints:** linhas de `source_endpoint` com `endpoint_status` `ACTIVE` (valor interno `active`; DEC-024), ordenadas por `id`; com `--source ID`, apenas as que têm `source_id = ID`. Endpoints `CANDIDATE`, `VALIDATED` ou `INACTIVE` nunca são passados a um collector. Uma fonte existente sem endpoints `ACTIVE` resulta em zero endpoints seleccionados, o que não é erro.

**Ciclo de vida do `run`** ([DATA_MODEL.md](DATA_MODEL.md#29-run) §2.9; DEC-031):
1. **Início** (depois das pré-condições): numa transacção própria, insere-se um `run` com `command = "collect"`, `started_at`, `finished_at = NULL` e `status = NULL`. Não existe estado `running`.
2. **Fim:** numa transacção própria, gravam-se `finished_at`, `status` e `stats`. `outcome` e `report_path` ficam nulos no M2.8.
3. **Estados finais:** `success` — nenhum endpoint seleccionado falhou (incluindo zero endpoints seleccionados); `partial` — pelo menos um endpoint teve sucesso e pelo menos um falhou; `failed` — todos os endpoints seleccionados (pelo menos um) falharam.
4. Um `run` com `finished_at IS NULL` representa uma execução interrompida ou não concluída. O M2.8 não fecha nem corrige `run` interrompidos.
5. Não há modelo de domínio `Run` nem enumerações novas: o tratamento de `run` fica em `storage` e na orquestração, com os valores de `status` de DATA_MODEL.md §2.9.

**`stats`** (JSON em `TEXT`), com os endpoints pela ordem de selecção:

```json
{
  "endpoints": [
    {"id": "<endpoint_id>", "result": "success", "new": 0, "existing": 0, "error": null}
  ],
  "totals": {"selected": 0, "succeeded": 0, "failed": 0, "new": 0, "existing": 0}
}
```

`result` é `success` ou `failed`; num endpoint que falhou, `new` e `existing` são `0` (rollback) e `error` contém o motivo.

**Processamento de cada endpoint** (DEC-031):
- **Sem collector registado** para o `endpoint_type` → falha desse endpoint, com o motivo `sem collector para endpoint_type <tipo>`. Não é falha de pré-condição.
- **Com collector:** chama-se `fetch(endpoint, None)` e todos os itens devolvidos são persistidos numa transacção do endpoint. Cada `RawItem` tem de ter `source_endpoint_id` igual ao `id` do endpoint; um item com outro valor, ou nulo, é falha do endpoint (a proveniência de `raw_item` não é reinterpretada — DEC-029).
- **Identidade de `raw_item`:** `(source_endpoint_id, url, content_hash)` (DATA_MODEL.md §2.1; `content_hash` do domínio, DEC-021). Um item cuja identidade já existe — de uma execução anterior ou de um item anterior do mesmo `fetch` — não é inserido nem alterado e conta como `existing`. A verificação faz-se com `SELECT` antes do `INSERT`, dentro da transacção do endpoint; sem `INSERT OR IGNORE`, `INSERT OR REPLACE` nem `ON CONFLICT`.
- **Item novo:** `INSERT` com os campos do `RawItem`, o `content_hash`, `created_in_run` = `id` do `run` em curso e `created_at` = `updated_at`, preenchidos pela `storage`.
- **Sucesso do endpoint:** na mesma transacção, `last_success_at` = instante do fim do processamento do endpoint (UTC) e `last_error = NULL`; commit. Um erro anterior deixa de figurar como erro actual.
- **Falha do endpoint** (excepção do collector, na chamada ou durante a iteração; item inválido; collector em falta): rollback da transacção do endpoint — nenhum item desse endpoint fica gravado nesta execução e os `raw_item` anteriores ficam intactos; depois, numa transacção própria, `last_error` = motivo, com `last_success_at` preservado. A falha fica em `stats` e o processamento continua no endpoint seguinte.
- `last_success_at` e `last_error` são campos operacionais (DEC-027): a sua actualização pelo collect não altera nenhum campo projectado nem `source_endpoint.updated_at`, que continua a indicar só alterações aos campos projectados (DEC-028).
- **Erro da camada `storage`** (por exemplo, erro SQLite) não é falha de endpoint: rollback da transacção em curso e termina com código `1`; o `run` fica com `finished_at IS NULL` (execução interrompida).

**Saída e códigos de saída** (DEC-031):
- Execução concluída: resumo em stdout — `collect: OK — <caminho da base>` (código `0`, `success`), `collect: PARCIAL — <caminho>` (código `2`, `partial`) ou `collect: ERRO — <caminho>` (código `1`, `failed`), seguido de `run: <id>`, `endpoints: <seleccionados>`, `com sucesso: <n>`, `com falha: <n>`, `itens novos: <n>` e `itens existentes: <n>`; cada endpoint que falhou é indicado em stderr como `- <endpoint_id>: <motivo>`.
- Falha de pré-condição ou erro da `storage`: `collect: ERRO — <caminho da base>` e `- <motivo>` em stderr, código `1`.
- Zero endpoints `ACTIVE` é sucesso: código `0`, `run` em `success` com zero itens.

**Idempotência:** uma nova execução sem dados novos cria um novo `run`, não cria `raw_item`, conta os itens já existentes como `existing`, não altera os `raw_item` anteriores e actualiza o estado operacional de cada endpoint segundo o resultado actual.

**Esquema e portabilidade (DEC-013, DEC-026):** usa a `0001` do M2.6 sem alterações — sem migrações, tabelas, colunas nem índices novos. `raw_item.created_in_run` passa a ser preenchido para os itens criados por `tde collect`. Só `SELECT`, `INSERT` e `UPDATE` simples, com equivalente directo em PostgreSQL; sem `PRAGMA` fora da configuração da ligação.

**Dependências:** M2.3 (`RawItem`, `content_hash`); M2.6 (`0001`, verificação de migrações, resolução do caminho da base de dados); M2.7 (espelho de `source_endpoint`, verificação de esquema). Nenhuma dependência externa nova.

**D1, D8, D12 e D13:** continuam OPEN e não são afectados. Com `config/sources.yaml` vazio (`[]`, por D1) e sem collectors concretos, `tde collect` não recolhe nada até unidades posteriores; o comportamento verifica-se com fixtures e collectors falsos.

**Exclusões:** collectors `rss`, `html_page` e `manual`; HTTP e qualquer acesso à rede; `robots.txt`; `User-Agent`; rate limiting; transporte concreto de `fetch` (continua fora da projecção — DEC-028); `--since`; `tde add-manual` (e a limitação do `NULL` em `UNIQUE`); NORMALIZE; `source_document`; migração `0002`; D1, D8, D12 e D13; IA; execução agendada; PostgreSQL; `editorial_decision`; `--dry-run`; `tde run` e `tde report`; política de retenção; modelo de domínio `Run`. Não altera `tde doctor`, `tde init`, `tde sources validate`, `tde sources sync`, o domínio nem o formato do YAML.

**Critérios de aceitação (verificáveis na implementação):**
1. **Zero endpoints `ACTIVE`:** código `0`; é criado um `run` com `command = "collect"`, `status = success`, `finished_at` preenchido e zero itens; nenhum `raw_item` criado.
2. **Sucesso com collector falso:** os itens devolvidos ficam em `raw_item` com `created_in_run` do `run` criado; `last_success_at` preenchido e `last_error` nulo, mesmo que antes tivesse um erro; `run` em `success`, código `0`.
3. **Idempotência:** segunda execução com os mesmos itens cria um novo `run`, zero `raw_item` novos, `existing` igual ao número de itens, e os `raw_item` anteriores ficam inalterados (incluindo `created_in_run`); itens repetidos no mesmo `fetch` contam como `existing`.
4. **Falha isolada:** com um endpoint cujo collector falso falha a meio da iteração e outro com sucesso, nenhum item do primeiro fica gravado nesta execução, os seus `raw_item` anteriores e `last_success_at` mantêm-se, `last_error` é preenchido; o segundo é processado; `run` em `partial`, código `2`.
5. **Todos falham:** `run` em `failed`, código `1`, com `finished_at` e `stats` preenchidos.
6. **Endpoint sem collector:** um endpoint `ACTIVE` cujo `endpoint_type` não tem collector registado conta como falha desse endpoint (`last_error` preenchido), não impede os restantes e não é erro de pré-condição.
7. **Endpoints não `ACTIVE`:** endpoints `CANDIDATE`, `VALIDATED` ou `INACTIVE` nunca são passados a um collector; os endpoints são processados por ordem de `id`.
8. **`--source`:** restringe aos endpoints da fonte indicada; fonte inexistente → código `1`, sem `run`; fonte sem endpoints `ACTIVE` → `success` com zero itens.
9. **Pré-condições:** base inexistente → código `1`, pedindo `tde init`, sem ficheiro nem directório criados; esquema não conforme → código `1`, pedindo `tde init`, sem migração aplicada; em ambos os casos não é criado `run`.
10. **Execução interrompida:** um erro da `storage` injectado durante o processamento termina com código `1`, deixa o `run` com `finished_at IS NULL` e sem itens da transacção interrompida.
11. **Isolamento das camadas:** `collectors/` não importa `storage` nem `sqlite3`; `storage` não importa `collectors` nem `sources`; SQL só em `storage/`; sem `INSERT OR IGNORE`, `INSERT OR REPLACE` nem `ON CONFLICT`; o collect não altera campos projectados nem `updated_at` de `source_endpoint`, nem lê ou altera `config/sources.yaml`.
12. **CLI:** `tde collect` aparece em `tde --help`, com `--source` e sem `--since`.
13. **Comportamento existente preservado:** `tde doctor`, `tde init`, `tde sources validate` e `tde sources sync` mantêm o comportamento; o esquema não muda; os testes existentes continuam a passar.
14. **Testes offline:** bases de dados em directórios temporários, collectors falsos, sem rede, sem fornecedor de IA e sem fontes nem URLs reais; nenhum teste escreve em `data/`.
15. **Validação do repositório:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` e `uv run tde doctor` passam.

**Implementação:** contrato e registo em `src/tensdireito_content_engine/collectors/base.py` (`Collector`, `CollectorRegistry`, `default_registry()` vazio); orquestração em `src/tensdireito_content_engine/collect.py` (`run_collect`), sem SQL; `tde [--config DIR] [--db PATH] collect [--source ID]` em `cli.py`. Em `storage`: `schema.py` (verificação de base existente e de esquema, partilhada com `tde sources sync`, mensagens inalteradas), `runs.py` (`start_run`, `finish_run`), `endpoints.py` (`source_exists`, `active_endpoints`, `mark_endpoint_success`, `record_endpoint_failure`), `raw_items.py` (`save_endpoint_items`) e `transaction` em `database.py` (`BEGIN` … `COMMIT`; erro SQLite → `ROLLBACK` e `StorageError` encadeado com a excepção original). Os itens de cada endpoint são materializados e validados (instância de `RawItem` e `source_endpoint_id` igual ao endpoint) antes de qualquer escrita; depois, numa transacção, `SELECT` por identidade antes de cada `INSERT` e `last_success_at`/`last_error = NULL`. Uma falha de endpoint regista `last_error` numa transacção própria. O motivo de uma excepção do collector é `o collector falhou: <tipo>: <mensagem>`; o de um item inválido indica a posição do item (a partir de 1). Um ficheiro que não é SQLite é reportado como `esquema não conforme`, pedindo `tde init`. Sem migrações, sem alterações ao esquema e sem dependências novas.

### M2.9 — primeiro collector concreto: `rss`, com transporte HTTPS restrito

**Estado:** concluído e integrado (PR #16). Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção. Decisões: DEC-032 (contrato do collector `rss`) e DEC-033 (transporte HTTPS restrito dos collectors de produção). Respeita DEC-013, DEC-021, DEC-027, DEC-028, DEC-029, DEC-030 e DEC-031, sem as alterar. DEC-034 (protocolo de validação de fontes) é registada em conjunto, mas aplica-se numa unidade separada (ver *Âmbito: porquê `rss` e porquê sem validação de fontes*).

**Objectivo:** dar ao `tde collect` do M2.8 o primeiro `Collector` concreto, para `endpoint_type = rss` (RSS 2.0), e a primeira — e única — camada de rede do sistema: um transporte HTTPS restrito, que só obtém o URL de endpoints `ACTIVE` já validados e revistos por pull request. O M2.9 **não** acrescenta endpoints reais: com `config/sources.yaml` vazio (`[]`, por D1), `tde collect` continua a não fazer nenhum pedido de rede em produção. O comportamento verifica-se com fixtures sintéticas e transporte falso, offline.

**Âmbito: porquê `rss` e porquê sem validação de fontes.**
- **Verificação do estado actual.** O repositório não contém evidência de que alguma fonte candidata publique RSS: nenhuma fonte foi validada, `config/sources.yaml` está vazio e SOURCES.md §6 não assume RSS, feeds nem APIs. A escolha de `rss` **não** se apoia na existência de feeds nas fontes prioritárias; apoia-se na arquitectura actual:
  1. É o único tipo de endpoint que não precisa de `fetch`. `html_page` precisa de `fetch.selectors`, que DEC-028 mantém fora do domínio; transportá-lo alargaria a unidade ao domínio, ao M2.5 e ao M2.7.
  2. `manual` não tem semântica definida (relação com `tde add-manual`; limitação do `NULL` em `UNIQUE`, M2.6) e não exige rede, pelo que não estabelece o transporte.
  3. RSS é estruturado: o mapeamento para `RawItem` dispensa extracção de HTML e selectores — não é scraping.
  4. [SECURITY.md](SECURITY.md#2-recolha-responsável) §2 prefere feeds a páginas.
  5. O transporte HTTPS restrito (DEC-033) é reutilizável por um futuro `html_page`.
- **Risco assumido:** se a validação (D1) mostrar que nenhuma fonte prioritária publica RSS 2.0 — por exemplo, só Atom —, o collector fica sem endpoints; o transporte mantém o valor. Atom fica fora do M2.9 (questão aberta Q2).
- **Validação de fontes em unidade separada.** Validar uma fonte é trabalho humano: `validated_by` tem de ser uma pessoa (DEC-014; invariante do domínio), e a evidência obtém-se nas fontes oficiais, não por inferência do modelo. Juntá-la ao M2.9 faria depender os critérios de aceitação do código de trabalho manual, e o código de endpoints reais. O M2.9 entrega o collector sem endpoints reais; a validação das primeiras fontes segue o protocolo de [SOURCES.md](SOURCES.md#8-protocolo-de-validação-de-fontes) §8 (DEC-034), numa unidade própria, que pode correr em paralelo. Nenhum endpoint real entra em `config/sources.yaml` no M2.9.

**Entregáveis da implementação:**
1. **Transporte HTTPS** em `src/tensdireito_content_engine/collectors/http.py` (DEC-033): a única responsabilidade de rede do sistema. Faz um `GET` a um URL, aplica a política de DEC-033 e devolve a resposta (código HTTP, `Content-Type`, corpo em bytes) ou falha com um motivo. Não interpreta o conteúdo. É injectável no collector (os testes usam um transporte falso), e a resolução de nomes e a abertura da ligação são injectáveis no próprio transporte.
2. **Collector `rss`** em `src/tensdireito_content_engine/collectors/rss.py` (DEC-032): `endpoint_type = EndpointType.RSS`; `fetch(endpoint, since)` obtém o corpo de `endpoint.url` através do transporte e passa-o a uma função de parsing pura, `bytes` → `list[RawItem]`, sem rede. `since` continua a ser sempre `None` e é ignorado.
3. **`robots.txt`** verificado em execução, antes do pedido do feed, pelo mesmo transporte e com `urllib.robotparser` (DEC-033).
4. **Registo de produção:** `default_registry()` passa a conter o collector `rss` com o transporte real. Sem endpoints `ACTIVE` (D1), nenhum pedido é feito.
5. **Sem outras alterações:** CLI (`tde collect [--source ID]`, saídas e códigos do M2.8), orquestração (`collect.py`), `storage`, esquema, domínio e formato do YAML ficam como estão.

**Camadas:**

| Módulo | Responsabilidade | Pode importar | Não pode |
|--------|------------------|---------------|----------|
| `collectors/http.py` | Rede: política de URL e destino, pedido, limites, `robots.txt` (DEC-033). | `domain`, biblioteca padrão (`urllib.request`, `urllib.robotparser`, `http.client`, `ssl`, `socket`, `ipaddress`). | XML, `storage`, `sqlite3`. |
| `collectors/rss.py` | Parsing de RSS 2.0 e mapeamento para `RawItem` (DEC-032). | `domain`, `collectors/http.py` (só a interface do transporte), biblioteca padrão XML. | Módulos de rede directamente, `storage`, `sqlite3`. |
| `collect.py` (M2.8) | Orquestração; trata excepções do collector como falha do endpoint (DEC-031). | Inalterado. | — |
| `storage` | Inalterado. | — | `collectors`. |

Só `collectors/http.py` importa módulos de rede da biblioteca padrão; um teste verifica-o, como o M2.6 verifica `sqlite3`.

**Mapeamento RSS 2.0 → `RawItem`** (DEC-032; campos do M2.3, sem campos novos):

| Campo de `RawItem` | Origem | Ausente ou vazio |
|--------------------|--------|------------------|
| `source_endpoint_id` | `endpoint.id` | — |
| `url` | Texto de `<link>` do `<item>`, sem espaço exterior; mais nada é alterado (parâmetros, fragmento, maiúsculas). Tem de ser URL absoluto `http`/`https`. | Item inválido → falha do endpoint. |
| `title` | Texto de `<title>` do `<item>`, sem alteração (a normalização do título é do NORMALIZE, DEC-021). | Item inválido → falha do endpoint. |
| `raw_content` | Serialização determinística, em texto, do elemento `<item>` completo, tal como lido pelo parser (inclui `description`, `content:encoded`, categorias, `enclosure` e extensões). Não é texto extraído; o collector não escolhe entre `description` e `content:encoded`. | Nunca vazio (o elemento existe). |
| `fetched_at` | Instante UTC da resposta do feed, igual para todos os itens dessa resposta; relógio injectável. | — |
| `external_id` | Texto de `<guid>`, sem espaço exterior. `isPermaLink` não é interpretado; o `guid` nunca substitui `<link>`. | Nulo. |
| `published_at_raw` | Texto de `<pubDate>`, sem espaço exterior e sem interpretação (D13). | Nulo. |
| `manual_note` | — | Nulo. |

- **URL canónico:** não é calculado nem guardado; `RawItem` não tem esse campo e D12 continua OPEN. O `url` é preservado tal como obtido (DEC-021).
- **Feed:** a raiz tem de ser `<rss>` com exactamente um `<channel>`; o atributo `version` não é condição. Atom (`<feed>`), RSS 1.0/RDF ou outra raiz → falha do endpoint, `formato não suportado`.
- **Sem itens:** um `<channel>` válido sem `<item>` é sucesso com zero itens, não falha.
- **Ordem e duplicados:** itens pela ordem do documento. Itens repetidos no mesmo feed ou já gravados contam como `existing` (identidade `(source_endpoint_id, url, content_hash)` do M2.8); o collector não deduplica. O mesmo `<link>` com conteúdo diferente gera outro `raw_item`, como no M2.8.
- **Item inválido:** nenhum valor é inventado e nenhum item é descartado em silêncio. Um item sem `<title>` ou `<link>` utilizáveis faz falhar o endpoint, com a posição do item (a partir de 1); pela atomicidade do M2.8, nenhum item desse endpoint é gravado nessa execução.
- **XML:** XML malformado → falha. Qualquer declaração `DOCTYPE` → falha, antes de processar entidades (DEC-033). A codificação é a do próprio documento (BOM ou declaração XML; UTF-8 por omissão); o `charset` do `Content-Type` não é usado. Codificação não suportada pelo parser ou bytes inválidos → falha.
- **Links dos itens:** nunca são seguidos. Documentos oficiais associados (CONTENT_PIPELINE.md, etapa 1) não são recolhidos no M2.9.

**Transporte HTTPS restrito** (DEC-033): só `https`, sem credenciais no URL, porta omitida ou `443`, anfitrião por nome; todos os endereços resolvidos têm de ser públicos; redirects não são seguidos; só `200` é sucesso; `Content-Type` do feed em `application/rss+xml`, `application/xml` ou `text/xml`; sem compressão (`Content-Encoding` diferente de `identity` → falha); corpo até 5 MiB (feed) e 512 KiB (`robots.txt`); 20 s por operação de rede e 60 s no total por pedido; verificação TLS nunca desactivada; uma tentativa, sem repetições; `User-Agent` identificável com contacto (Q1); pedidos sequenciais, com intervalo mínimo de 5 s entre pedidos ao mesmo anfitrião na mesma execução; `robots.txt` uma vez por anfitrião e por execução. `fetch` do YAML continua fora da projecção (DEC-028): `frequency`, `rate_limit_seconds` e `max_items` não têm efeito no M2.9. Pormenor em DEC-033.

**Erros:** todos os erros de transporte e de conteúdo são excepções do collector, com tipos próprios em `collectors/` (um para transporte, outro para o conteúdo do feed) e mensagens deterministas que não incluem o corpo da resposta. O M2.8 já os trata como falha do endpoint (`o collector falhou: <tipo>: <mensagem>` em `last_error` e `stats`; DEC-031); `last_success_at` é preservado e os restantes endpoints continuam. Exemplos de motivo: `HTTP 404`; `redirect não seguido: 301`; `Content-Type não aceite: text/html`; `resposta excede 5 MiB`; `tempo esgotado`; `destino não público`; `XML malformado: <mensagem do parser>`; `DOCTYPE não permitido`; `formato não suportado: <raiz>`; `item 3: sem link`; `robots.txt não permite`. Um erro da `storage` continua a terminar com código `1` e `run` por concluir (M2.8).

**Persistência:** `raw_item` continua a ser a unidade persistida. Os campos de `RawItem` (M2.3) chegam para RSS 2.0: `url` ← `<link>`, `title` ← `<title>`, `raw_content` ← elemento `<item>`, `external_id` ← `<guid>`, `published_at_raw` ← `<pubDate>`, `fetched_at` ← resposta. Não há redirects, por isso o URL obtido é sempre o URL validado do endpoint e não precisa de registo próprio; metadados HTTP (código, `ETag`, `Content-Type`) não são guardados. Sem `source_document`, sem migrações, sem colunas novas e sem alterações ao domínio.

**Dependências criadas para unidades futuras (registadas, não resolvidas):**
- **NORMALIZE:** para itens `rss`, `raw_content` é XML do `<item>`; a unidade que persistir NORMALIZE terá de definir como extrai o texto (`description` / `content:encoded`) desse XML. Não depende de D12.
- **D12:** o `url` de cada item é o `<link>` sem alterações (pode conter parâmetros de tracking); `canonical_url` será calculado a partir dele quando D12 for decidida. O M2.9 não restringe D12.
- **D13:** `pubDate` de RSS 2.0 usa o formato RFC 822, que DEC-021 não converte; até D13, a normalização deixa `published_at` nulo nesses itens. O M2.9 não interpreta datas.
- **Retenção e crescimento:** como `raw_content` inclui todo o `<item>`, qualquer alteração de um elemento no feed produz um novo `raw_item` (identidade do M2.8). A estabilidade do feed entre pedidos é verificada na validação técnica (SOURCES.md §8).

**Dependências externas:** nenhuma nova. Biblioteca padrão: `urllib.request`, `http.client`, `ssl`, `socket`, `ipaddress`, `urllib.robotparser`, `xml.etree.ElementTree`/`pyexpat`. Ver DEC-033 para as alternativas rejeitadas (`feedparser`, `httpx`/`requests`, `defusedxml`).

**D1, D8, D12 e D13:** continuam OPEN. O M2.9 não acrescenta fontes, endpoints, URLs nem `domains`; não agenda execuções nem resolve persistência durável (`tde collect` continua manual e local); não calcula `canonical_url`; não interpreta `published_at_raw`.

**Exclusões:** Atom; RSS 1.0/RDF; `html_page`; `manual`; `tde add-manual`; seguir links dos itens ou recolher documentos associados; scraping; endpoints ou fontes reais em `config/sources.yaml`; validação manual de fontes (unidade separada, DEC-034); transporte de `fetch` para o domínio; `--since`; pedidos condicionais (`ETag`, `If-Modified-Since`); repetições; pedidos paralelos; cache HTTP; cookies e autenticação; proxies configurados pelo projecto; comando ou função pública para obter um URL arbitrário; NORMALIZE; `source_document`; migrações; scheduler, cron, daemon, jobs, GitHub Actions; D8; publicação; IA; alterações a `tde sources validate` (incluindo a regra "endpoint `ACTIVE` só em fonte `VALIDATED`" — Q4). Não altera `tde doctor`, `tde init`, `tde sources validate`, `tde sources sync`, `tde collect`, o domínio nem o formato do YAML.

**Critérios de aceitação (verificáveis na implementação):**
1. **Registo:** `default_registry()` devolve um registo com exactamente um collector, para `rss`; endpoints `html_page` e `manual` continuam a falhar como `sem collector para endpoint_type <tipo>` (DEC-031).
2. **Produção sem endpoints reais:** `config/sources.yaml` continua `[]`; `tde collect` numa base sem endpoints `ACTIVE` termina com código `0`, sem nenhum pedido de rede.
3. **Feed válido:** um feed RSS 2.0 sintético produz um `RawItem` por `<item>`, pela ordem do documento, com os campos do mapeamento; `raw_content` é igual em duas leituras do mesmo corpo (determinismo do `content_hash`).
4. **Campos opcionais:** itens sem `<guid>` ou sem `<pubDate>` produzem `external_id` / `published_at_raw` nulos; `published_at_raw` é o texto original sem interpretação; nenhum outro campo é afectado.
5. **Item inválido:** um item sem `<title>` ou sem `<link>` absoluto `http`/`https` faz falhar o endpoint com a posição do item; nenhum item desse endpoint é gravado; os `raw_item` anteriores e `last_success_at` mantêm-se.
6. **Feed vazio:** um `<channel>` sem itens → endpoint com sucesso, zero itens, `last_success_at` actualizado.
7. **Formato e XML:** Atom, RSS 1.0, raiz desconhecida, XML malformado, documento com `DOCTYPE` (incluindo entidades internas e externas) e bytes numa codificação inválida → falha do endpoint, sem expansão de entidades nem acesso a recursos externos.
8. **Codificação:** feeds sintéticos em UTF-8 (com e sem BOM) e em ISO-8859-1 declarado são lidos correctamente, com caracteres portugueses preservados; o `charset` do `Content-Type` é ignorado.
9. **HTTP:** respostas `3xx`, `4xx` e `5xx`, `Content-Type` não aceite ou ausente, `Content-Encoding` comprimido, `Content-Length` acima do limite, corpo que excede o limite durante a leitura e tempo esgotado → falha do endpoint, com motivo determinista e sem processar corpo parcial.
10. **URL e destino:** `http`, credenciais no URL, porta diferente de `443`, IP literal e nome que resolve para um endereço não público (loopback, privado, link-local, reservado, multicast) → falha antes de qualquer ligação.
11. **`robots.txt`:** `200` que proíbe o URL → falha; `200` que permite, `404`/`410` (ou outro `4xx`) → pedido do feed feito; `5xx`, `3xx`, tempo esgotado ou erro → falha, sem pedir o feed; um pedido de `robots.txt` por anfitrião e por execução.
12. **Ritmo:** pedidos sequenciais; entre dois pedidos ao mesmo anfitrião na mesma execução decorre pelo menos o intervalo mínimo, verificado com relógio e espera injectados (sem espera real nos testes); nenhuma repetição após falha.
13. **`User-Agent`:** todos os pedidos levam o `User-Agent` definido (Q1); sem cookies nem cabeçalhos de autenticação.
14. **Idempotência (M2.8):** duas execuções com o mesmo feed criam dois `run`, `raw_item` só na primeira, e `existing` igual ao número de itens na segunda.
15. **Estado operacional (M2.8):** sucesso → `last_success_at` actualizado e `last_error` nulo; falha de transporte ou de conteúdo → `last_error` com o motivo e `last_success_at` preservado; `updated_at` e campos projectados de `source_endpoint` inalterados; códigos `0`/`2`/`1` como em DEC-031.
16. **Isolamento:** só `collectors/http.py` importa módulos de rede; `collectors/` não importa `storage` nem `sqlite3`; `storage` não importa `collectors`; `rss.py` não abre ligações (recebe o transporte).
17. **Esquema e domínio:** nenhuma migração, tabela, coluna, campo de domínio ou dependência nova; `uv.lock` inalterado.
18. **Testes offline:** fixtures sintéticas com domínios reservados (`example.org`, `.test`; RFC 2606), sem fontes nem URLs reais; uma salvaguarda nos testes faz falhar qualquer tentativa de abrir ligação de rede; a versão do Expat usada é ≥ 2.4.1 (verificada por teste); nenhum teste escreve em `data/`.
19. **Comportamento existente preservado:** `tde doctor`, `tde init`, `tde sources validate`, `tde sources sync` e `tde collect` mantêm a interface e as saídas; os testes existentes continuam a passar.
20. **Validação do repositório:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` e `uv run tde doctor` passam.

**Implementação:** transporte em `src/tensdireito_content_engine/collectors/http.py` (`HttpsTransport`, com uma única operação pública, `fetch_feed(url)`; `TransportError`; `User-Agent` e limites como constantes do módulo). Usa `http.client`, `ssl`, `socket`, `ipaddress` e `urllib.robotparser`; não usa `urllib.request`, pelo que variáveis de ambiente de proxy não são lidas (o projecto não configura proxies — DEC-033 §7). A resolução valida todos os endereços (`is_global` e nenhuma das categorias loopback, privado, link-local, multicast, reservado, não especificado; endereços IPv4 mapeados em IPv6 avaliados como IPv4) e a ligação TCP é aberta ao primeiro endereço verificado, sem segunda resolução, com SNI e verificação TLS para o nome do anfitrião: o endereço ligado é sempre um dos verificados. `robots.txt` é pedido uma vez por anfitrião e por instância do transporte (`default_registry()` cria uma por execução de `tde collect`), o resultado — incluindo a indisponibilidade — fica guardado para essa execução, e um `robots.txt` que não seja UTF-8 é tratado como indisponível. O intervalo de 5 s conta do fim do pedido anterior ao mesmo anfitrião (incluindo `robots.txt` e pedidos falhados). Um corpo mais curto do que o `Content-Length` declarado é falha (`resposta incompleta`), porque `http.client` não o assinala. Collector e parser em `src/tensdireito_content_engine/collectors/rss.py` (`RssCollector`, `parse_feed`, `FeedError`): uma primeira passagem com `xml.parsers.expat` recusa `DOCTYPE` antes de qualquer entidade, e só depois `xml.etree.ElementTree` constrói o documento; `raw_content` é `ET.tostring(<item>, encoding="unicode")` sem o espaço que segue o elemento; o texto de `<title>`, `<link>`, `<guid>` e `<pubDate>` é o conteúdo textual do primeiro elemento com esse nome no `<item>`. `default_registry()` em `collectors/base.py` regista `RssCollector(HttpsTransport())`. Testes offline em `tests/test_rss_parser.py`, `tests/test_http_transport.py` e `tests/test_rss_collect.py`, com fixtures sintéticas em `tests/fixtures/rss/`, um servidor falso em `tests/_fake_http.py` e a salvaguarda de rede em `tests/conftest.py`. Sem migrações, sem alterações ao esquema, ao domínio, à CLI ou ao YAML, e sem dependências novas.

**Questões abertas antes da implementação:**
- **Q1 — contacto do `User-Agent` (fechada na implementação).** SECURITY.md §2 exige um `User-Agent` identificável com contacto. O responsável do projecto indicou como contacto o URL público do repositório, `https://github.com/nunovinhas-creator/tensdireito-content-engine` (sem endereço de correio). `User-Agent`: `tensdireito-content-engine/<versão> (+https://github.com/nunovinhas-creator/tensdireito-content-engine)`, fixo no código e não configurável em `sources.yaml`; o token `tensdireito-content-engine` é o usado na avaliação de `robots.txt`.
- **Q2 — Atom (não bloqueante).** Fora do M2.9. Se a validação (DEC-034) mostrar que fontes prioritárias só publicam Atom, decide-se então se Atom entra como variante de `rss` ou como novo `endpoint_type` (que exige decisão registada — DATA_MODEL.md §2.1).
- **Q3 — valores dos limites (não bloqueante).** 5 MiB / 512 KiB, 20 s / 60 s e 5 s ficam fixados por DEC-033, sem evidência de fontes reais. Se a validação técnica das primeiras fontes (DEC-034, V3) mostrar que não servem, ajustam-se por pull request, com actualização de DEC-033.
- **Q4 — `ACTIVE` só em fonte `VALIDATED` (não bloqueante).** O protocolo de DEC-034 exige-o, mas `tde sources validate` não o verifica hoje. A regra é procedimental no M2.9; passá-la a validação automática é decisão da unidade de validação de fontes. **Resolvida no M2.10 por DEC-035:** passa a regra automática de `tde sources validate`.

### M2.10 — validação de fontes

**Estado:** concluído e integrado (PR #18). Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção. A validação real de fontes (D1) não faz parte da unidade e continua por fazer. Decisões: DEC-035 (regra automática "endpoint `ACTIVE` só em fonte `VALIDATED`", Q4) e DEC-036 (validador, resultados e registo de evidência). Aplica DEC-034 (cinco verificações e correspondência com os estados) e respeita DEC-014, DEC-023, DEC-024, DEC-027 a DEC-033, sem as alterar.

**Objectivo:** validar documentalmente fontes e endpoints candidatos antes de serem considerados activáveis pelo sistema. O M2.10 fixa o processo — quem valida, que evidência é necessária, como se regista, que resultados permitem cada passagem de estado — e torna automática a única regra entre estados verificável a partir do YAML. **Não valida nenhuma fonte real:** a validação das fontes T1 prioritárias (D1) é actividade posterior, feita por pessoas, um pull request por passagem de estado, segundo este contrato. Mantém-se a regra central: descobrir não é verificar; verificar não é aprovar; aprovar não é publicar (DEC-002).

**O que é validado (DEC-034; SOURCES.md §8.1–§8.2):**

| Entidade | Estado pedido | Verificações exigidas com `ok` | Outras condições |
|----------|---------------|--------------------------------|------------------|
| Fonte | `VALIDATED` | V1 (existência da fonte), V4 da fonte (adequação editorial, tier confirmado) | `domains` confirmados; `validated_at`/`validated_by`. |
| Endpoint | `VALIDATED` | V2 (existência do endpoint), V3 (validade técnica), V5 (autorização de recolha) | `url` = URL confirmado, final, sem redirects; `validated_at`/`validated_by`. |
| Endpoint | `ACTIVE` | V4 do endpoint | Endpoint já `VALIDATED` (pull request anterior); fonte `VALIDATED`; collector registado para o `endpoint_type`; o próprio pull request é a decisão explícita de activar. |

As perguntas e a natureza da evidência de cada verificação são as de SOURCES.md §8.1, sem alterações. Para V3, o contrato é o do collector do tipo: hoje só existe para `rss` (DEC-032, DEC-033), pelo que endpoints `html_page` e `manual` não podem obter V3 `ok` nem passar a `VALIDATED` enquanto não houver collector e contrato para esses tipos.

**Quem valida (DEC-036; DEC-014):**
- `checked_by` (cada verificação) e `validated_by` (cada passagem de estado) identificam uma **pessoa**, de forma declarativa, sem autenticação na V1. Nunca um modelo de IA — `llm:*` ou qualquer outro identificador de modelo —, uma conta de automação ou um bot. O domínio já recusa `validated_by` com prefixo `llm:` (M2.2); o resto verifica-se na revisão.
- O `validated_by` de uma passagem consta como `checked_by` de pelo menos uma das verificações exigidas para esse estado.
- A passagem produz efeito com o merge do pull request por uma pessoa com permissão de merge. Na V1 não se exige revisor diferente do validador. A lista nominal de validadores não é fixada (D7 — pessoas concretas — continua em aberto); nenhum nome é inventado.
- **Papel do modelo:** pode ajudar a preparar o registo, rever a sua forma ou resumir observações fornecidas por uma pessoa. Não fornece nem completa URLs, feeds ou endpoints (SOURCES.md §8.3), não executa as verificações, não decide o resultado e nunca é `checked_by` nem `validated_by`.

**Evidência (DEC-036):**
- **Onde:** `docs/source_validation/<source_id>.md`, um ficheiro Markdown versionado por fonte, cobrindo a fonte e os seus endpoints, criado ou alterado no mesmo pull request que muda o estado em `config/sources.yaml`. A descrição do pull request remete para o ficheiro.
- **Conteúdo:** (a) identificação — `source_id` e os `endpoint_id` abrangidos; (b) registos de verificação com os campos de SOURCES.md §8.4, sem alterações: `source_id`/`endpoint_id`, `check` (V1–V5), `checked_at` (ISO 8601 com fuso explícito), `checked_by`, `method`, `observation`, `result` (`ok` · `falha` · `não aplicável`, com motivo quando não é `ok`); (c) secção de limitações; (d) lista das passagens de estado pedidas (entidade, estado anterior → estado novo, `validated_at`, `validated_by`).
- **Histórico:** o ficheiro é só acrescentado. Registos anteriores, incluindo verificações falhadas, nunca são apagados nem reescritos; uma revalidação acrescenta registos novos. O histórico do git liga cada registo ao pull request que o introduziu.
- **Auditoria:** fonte, endpoint, data da validação, pessoa, evidência V1–V5, resultado e limitações ficam no ficheiro; o estado resultante fica em `config/sources.yaml`; ambos são revistos no mesmo pull request.
- **Sem persistência nova:** o ficheiro não é lido pelo sistema; nenhuma tabela, campo do YAML, comando ou verificação automática da evidência é criado.

**Resultados e limitações (DEC-036):**
- Uma passagem de estado exige `ok` em **todas** as verificações exigidas para o estado pedido (tabela acima). `falha`, ausência de registo ou `não aplicável` numa verificação exigida impedem a passagem; a entrada mantém o estado anterior e os registos ficam no ficheiro.
- `não aplicável` só regista que uma verificação não se aplica à entidade (por exemplo, V3 numa fonte); nunca substitui `ok` numa verificação exigida.
- Nenhuma verificação é inferida de outra: V3 `ok` não implica V5 nem V4; V1 não implica V2 (DEC-034).
- Limitações registam-se na secção própria, com a verificação e a questão aberta a que se referem. Uma limitação que torne negativa ou desconhecida a resposta à pergunta da verificação obriga a `falha`, não a `ok` com reserva. Exemplos: um feed só em Atom falha V3 (`formato não suportado`, DEC-032) e regista a limitação Q2; um feed acima dos limites de DEC-033 falha V3 e regista a limitação Q3.
- Formatos de `<pubDate>` ou parâmetros de tracking observados nos itens podem ser registados como observação; não são critério de V3 e não decidem D12 nem D13.

**Passagens de estado (DEC-036; SOURCES.md §8.2):**
- Cada passagem é um pull request que altera `config/sources.yaml` e o ficheiro de evidência.
- Uma entrada não avança dois estados no mesmo pull request: um endpoint passa a `VALIDATED` num pull request e a `ACTIVE` noutro, posterior, que é a decisão explícita de activar. A fonte e os seus endpoints podem mudar de estado no mesmo pull request, cada um uma vez.
- `url` continua nulo em `CANDIDATE`, mesmo com V2 registada; só é preenchido na passagem a `VALIDATED`.
- `INACTIVE` continua a seguir SOURCES.md §7 (decisão registada por pull request); o M2.10 não define revalidação periódica.

**Q4 — regra automática (DEC-035):** `tde sources validate` passa a recusar um endpoint `ACTIVE` cuja fonte não esteja `VALIDATED` (`CANDIDATE` ou `INACTIVE`), com a mensagem `um endpoint ACTIVE exige fonte VALIDATED (fonte <id>: <ESTADO>)`, reportada por endpoint, ao lado dos restantes erros. Se o estado da própria fonte for inválido, só esse erro é reportado. Por DEC-028 (3), `tde sources sync` deixa de sincronizar esse registo, sem verificação própria. Nenhuma outra regra entre estados é acrescentada (um endpoint `VALIDATED` numa fonte `CANDIDATE` continua válido).

**Entregáveis da implementação:**
1. **Regra de DEC-035** em `src/tensdireito_content_engine/sources/registry.py`, na leitura do registo, com testes offline sintéticos em `tests/test_sources_registry.py` (e no teste de `tde sources sync`, para o registo recusado).
2. **Formato do registo de evidência** em `docs/source_validation/README.md`: estrutura do ficheiro por fonte, campos de SOURCES.md §8.4, secção de limitações, lista de passagens de estado, regras de resultado e de validador, e um modelo apenas com marcadores (`<source_id>`, `<pessoa>`, …) — sem fontes, URLs, pessoas nem resultados reais.
3. **Documentação actualizada com a implementação:** TECHNICAL_SPEC.md §3 (regra de `tde sources validate`), SOURCES.md §4 (lista de verificações de `tde sources validate`) e §8.2 (a regra deixa de ser procedimental), e o estado desta secção.
4. **Sem outras alterações:** domínio, esquema, migrações, formato do YAML, `tde collect`, `tde init`, `tde doctor`, collectors e transporte ficam como estão; `config/sources.yaml` continua `[]`.

**Dependências:** DEC-034 (verificações e estados); DEC-030 (`validated_at`/`validated_by` como estado de validação operacional); DEC-023/DEC-024 (formato do YAML, inalterado); DEC-028 (3) (o sync só aceita registo válido); DEC-032/DEC-033 (contrato de V3 para `rss`); M2.5 (`tde sources validate`) e M2.2 (`validated_by` humano no domínio). A actividade de validação real depende do M2.10 integrado e de D1 (que fontes T1 são prioritárias).

**Questões e decisões que continuam OPEN:**
- **D1** — que fontes T1 são prioritárias e os seus endpoints. O M2.10 define como se valida, não quais; D1 fecha quando as fontes prioritárias tiverem passado por este processo.
- **D7** (parcial) — pessoas concretas que revêem e validam.
- **D12** (`canonical_url`, parâmetros de tracking) e **D13** (formatos de `published_at_raw`, datas sem hora, datas/horas sem fuso, fuso horário) — não são critério de validação e não são decididas.
- **Q2** (Atom) e **Q3** (valores dos limites de DEC-033) — dependem de evidência V3 real. Até serem decididas, um endpoint afectado falha V3 e não passa a `VALIDATED`; a limitação fica registada.
- **Q5 — V5 sem termos de utilização publicados (bloqueante só para o caso).** SOURCES.md §8.1 pergunta se os termos e o `robots.txt` permitem a recolha, mas não diz o que fazer quando a entidade não publica termos de utilização ou eles são omissos sobre recolha automática. Não se infere permissão: até decisão registada, esse caso não pode ter V5 `ok` e o endpoint não passa a `VALIDATED`.
- **Q6 — critério de estabilidade de V3 (não bloqueante).** SOURCES.md §8.1 exige "dois pedidos espaçados com itens estáveis" sem fixar o intervalo nem o critério de estabilidade. Até decisão, o registo de V3 indica o intervalo usado, o número de itens e o conjunto de `<link>`/`<guid>` de cada pedido, e o que foi comparado; o juízo é da pessoa e fica revisto no pull request.
- **Q7 — prazo de validade e revalidação (não bloqueante).** Não está definido quanto tempo uma verificação continua válida antes de uma passagem de estado, nem se `VALIDATED`/`ACTIVE` exigem revalidação periódica. Até decisão, aplica-se a revisão mensal de SOURCES.md §7, e cada registo mostra o seu `checked_at`.

**Exclusões:** fontes, URLs, feeds, `domains` ou endpoints reais em `config/sources.yaml`; validação real de fontes ou endpoints e qualquer evidência real; ficheiros de evidência de fontes reais; pedidos de rede a endpoints reais; novos collectors (`html_page`, `manual`); Atom e outros formatos RSS; novos transportes, alterações a DEC-033, proxies; comando para obter um URL arbitrário ou para executar verificações; verificação automática do ficheiro de evidência; campos novos no YAML, no domínio ou no esquema; SQLite (tabelas, colunas, migrações); `editorial_decision`; scheduler, cron, GitHub Actions; publicação; WhatsApp; IA como validador ou como origem de URLs; NORMALIZE, D12 e D13; qualquer unidade posterior.

**Critérios de conclusão da definição (este documento):**
1. Objectivo, entidades validadas e verificações exigidas por estado definidos (tabela acima), com V1–V5 de SOURCES.md §8.1 sem alterações.
2. Validador humano definido, incluindo a proibição de `llm:*`, de modelos, contas de automação e bots em `checked_by`/`validated_by`, e o papel limitado do modelo (DEC-036).
3. Localização, conteúdo e regra de histórico da evidência definidos (DEC-036), sem persistência nova.
4. Resultados que permitem e que impedem cada passagem de estado, e forma de registar limitações, definidos.
5. Relação entre `VALIDATED` e `ACTIVE` definida, incluindo pull requests distintos e a decisão explícita de activar.
6. Q4 resolvida por decisão registada (DEC-035).
7. Exclusões e dependências explícitas; D1, D7, D12, D13, Q2 e Q3 mantidas em aberto; lacunas de V1–V5 identificadas como Q5–Q7, sem resposta inferida.
8. Sem alterações a `src/`, `tests/`, `config/`, `pyproject.toml` nem `uv.lock`.

**Critérios de aceitação da implementação:**
1. **Q4:** um registo com endpoint `ACTIVE` em fonte `CANDIDATE` ou `INACTIVE` falha `tde sources validate` (código `1`) com a mensagem de DEC-035 para cada endpoint afectado, ao lado dos restantes erros; com a fonte `VALIDATED`, o mesmo registo é válido.
2. **Sem regras novas além de Q4:** um endpoint `VALIDATED` (ou `CANDIDATE`/`INACTIVE`) numa fonte `CANDIDATE` continua válido; as mensagens e regras existentes do M2.5 mantêm-se.
3. **Estado da fonte inválido:** se o `registry_status` da fonte for inválido, só esse erro é reportado para a relação com os endpoints.
4. **Sync:** `tde sources sync` com o registo do critério 1 termina com código `1` e não altera a base de dados (DEC-028).
5. **Collect inalterado:** `tde collect` e DEC-031 não mudam.
6. **Registo de evidência:** `docs/source_validation/README.md` existe, descreve o formato de DEC-036 e contém só marcadores; não existe nenhum ficheiro de evidência de fonte real.
7. **Sem dados reais:** `config/sources.yaml` continua `[]`; testes e fixtures usam só dados sintéticos e domínios reservados (RFC 2606), sem rede.
8. **Sem alterações estruturais:** domínio, esquema, migrações, formato do YAML, dependências e `uv.lock` inalterados.
9. **Validação do repositório:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run tde doctor` e `uv lock --check` passam.

**Implementação:** regra de DEC-035 em `src/tensdireito_content_engine/sources/registry.py`, na leitura do registo, ao lado da regra "endpoint `ACTIVE` exige `url` e `validated_at`". O estado da fonte é o `registry_status` lido do YAML, ou `CANDIDATE` (valor por omissão do domínio, M2.2) quando o campo falta; se o valor for inválido, a regra não é avaliada e só o erro do estado é reportado. Cada endpoint `ACTIVE` numa fonte `CANDIDATE` ou `INACTIVE` produz `um endpoint ACTIVE exige fonte VALIDATED (fonte <id>: <ESTADO>)`, com o prefixo de localização dos restantes erros (`sources[i].endpoints[j] (id=…)`), pela ordem do ficheiro. `tde sources sync` recusa o registo pela leitura comum (DEC-028 (3)), sem código próprio. Formato do registo de evidência e modelo só com marcadores em [`docs/source_validation/README.md`](source_validation/README.md); nenhum ficheiro de evidência de fonte real. Testes offline e sintéticos em `tests/test_sources_registry.py`, `tests/test_cli.py` e `tests/test_source_sync.py`; os testes existentes com endpoints `ACTIVE` passam a usar fonte `VALIDATED`. Sem alterações ao domínio, ao esquema, às migrações, ao formato do YAML, a `tde collect`, aos collectors, ao transporte nem às dependências; `config/sources.yaml` continua `[]`.

### M2.11 — persistência da etapa NORMALIZE

**Estado:** concluído e integrado (PR #20). Esta secção é o contrato da unidade; a implementação está descrita em *Implementação*, no fim da secção. Decisões: DEC-037 (`canonical_url` nulo enquanto D12 estiver OPEN), DEC-038 (`language` só por declaração explícita), DEC-039 (`document_kind` nulo = não determinado), DEC-040 (extracção de texto de itens `rss`) e DEC-041 (contrato de `tde normalize`, `source_document` e `0002`). Aplica DEC-021, DEC-022 e DEC-026, e respeita DEC-013 e DEC-027 a DEC-036, sem as alterar.

**Objectivo:** persistir a etapa NORMALIZE ([CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-2--normalize), etapa 2). Os `raw_item` pendentes passam a `source_document`, Nível 2 (DATA_MODEL.md §2.1), através de um comando explícito e local, `tde normalize`, com a tabela criada pela migração `0002`. Desta forma, `tde collect && tde normalize` (critério de saída da Fase 1) corre localmente, de forma idempotente, verificado com fixtures sintéticas.

**Contexto:** o M2.3 e o M2.4 definiram a normalização mecânica e a deduplicação exacta sem persistência (DEC-021, DEC-022). O M2.8 e o M2.9 gravam `raw_item` (para `rss`, `raw_content` é o XML do `<item>` — DEC-032). DEC-026 adiou `source_document` para "a unidade que persistir NORMALIZE, depois de essa unidade definir como trata `canonical_url` sob D12". O M2.9 deixou registada a dependência de extracção de texto do `<item>`. O NORMALIZE é a etapa seguinte ao COLLECT em todos os resultados possíveis de D1, ao contrário de `html_page`, Atom ou `manual`, cuja necessidade depende da validação real das fontes.

**Âmbito (entregáveis da implementação):**

1. **Migração `0002_source_document.sql`** em `src/tensdireito_content_engine/storage/migrations/`, que cria só a tabela `source_document` (ver *Esquema*), com um índice não único em `text_hash`. Não altera nenhuma tabela da `0001`.
2. **Modelo de domínio `SourceDocument`** (M2.2) alinhado com a tabela, sem campos além dela: `canonical_url`, `language`, `document_kind` e `text` passam a opcionais (DEC-037 a DEC-040); acrescentam-se `raw_item_id`, `text_hash`, `duplicate_of` e `status`. `status` usa uma enumeração com os valores de DATA_MODEL.md §2.1 (`normalized`, `classified`, `clustered`, `ignored`), dos quais o M2.11 só atribui `normalized` e `ignored`. Invariantes: `text` nulo ⇔ `text_hash` nulo; `text_hash`, quando existe, é SHA-256 hexadecimal em minúsculas; `duplicate_of` não nulo ⇒ `status = ignored` e `text_hash` não nulo; `language`, quando existe, tem 2 ou 3 letras ASCII minúsculas; `source_id` nulo ⇒ `T4` (invariante existente); `created_in_run` pertence à persistência e não está no domínio, como em `RawItem`. A escrita pode receber os valores sem `id` (atribuído pela base de dados); a forma do objecto de entrada é escolha de implementação, sem campos nem regras além deste contrato.
3. **Extracção de texto `rss` (DEC-040)** em `src/tensdireito_content_engine/normalize/`, como função pura de `raw_content` → texto extraído (ou nenhum), mais a `xml:lang` efectiva do elemento escolhido (DEC-038). Usa só a biblioteca padrão (`xml.parsers.expat`, `xml.etree.ElementTree`, `html.parser`), sem rede. As funções do M2.3/M2.4 mantêm-se, e o `text_hash` é o fingerprint de DEC-021 sobre o texto normalizado.
4. **Repositório em `storage`:** leitura dos `raw_item` pendentes com o `endpoint_type` do seu endpoint e o `tier`/`registry_status` da sua fonte; procura do representante por `text_hash`; inserção de `source_document`. Todo o SQL fica em `storage/`, e `storage` continua a depender só de `domain` (não importa `normalize`, `collectors` nem `sources`).
5. **Orquestração** fora de `storage` e de `normalize` (num módulo próprio, como `collect.py`, ou na CLI), sem SQL: pré-condições, `run`, ciclo de vida dos itens, códigos de saída.
6. **Comando `tde [--db PATH] normalize`** em `cli.py` (ver *Comando*).
7. **Documentação actualizada com a implementação** (ver *Documentação a actualizar*).

**Esquema — `source_document` (`0002`; DATA_MODEL.md §2.1; DEC-037 a DEC-041):**

| Coluna | Tipo | Nulo | Restrições | Origem | Semântica |
|--------|------|------|------------|--------|-----------|
| `id` | `INTEGER` | Não | PK | Base de dados | Identificador do documento. |
| `raw_item_id` | `INTEGER` | Não | FK → `raw_item(id)`; `UNIQUE` | `raw_item.id` | Relação 1:1 com a captura bruta (DATA_MODEL.md §1). |
| `source_id` | `TEXT` | Sim | FK → `source_registry(id)` | `source_endpoint.source_id` do endpoint do `raw_item` | Fonte resolvida. No M2.11 nunca é nulo nos documentos criados (as pistas manuais são `unsupported`); a coluna admite nulo para pistas manuais futuras (SOURCES.md §3.4). |
| `canonical_url` | `TEXT` | Sim | — | — | Sempre nulo no M2.11: "por calcular — D12 OPEN" (DEC-037). O URL original está em `raw_item.url`. |
| `title` | `TEXT` | Não | — | `raw_item.title` normalizado (DEC-021) | Título normalizado. |
| `text` | `TEXT` | Sim | — | Extracção de DEC-040 + normalização de DEC-021 | Texto limpo. Nulo = sem texto útil no item (nada fabricado). |
| `language` | `TEXT` | Sim | — | `xml:lang` efectiva (DEC-038) | Subetiqueta primária em minúsculas (ex.: `pt`). Nulo = língua desconhecida; nunca presumida. |
| `published_at` | `TEXT` | Sim | — | `raw_item.published_at_raw` pela regra de DEC-021 | UTC ISO 8601 com fuso explícito. Só ISO 8601 com fuso explícito é convertido; o `pubDate` RFC 822 de RSS fica nulo até D13. Nunca inventada. |
| `source_tier` | `TEXT` | Não | — | `source_registry.tier` se `registry_status` = `VALIDATED` no momento da normalização; senão `T4` | SOURCES.md §3.1; DATA_MODEL.md §2.1. |
| `document_kind` | `TEXT` | Sim | — | — | Sempre nulo no M2.11: "não determinado" (DEC-039). `other` nunca representa desconhecido. |
| `text_hash` | `TEXT` | Sim | Índice não único | Fingerprint de DEC-021 sobre `text` | Nulo se e só se `text` é nulo. |
| `duplicate_of` | `INTEGER` | Sim | FK → `source_document(id)` | Deduplicação persistida (DEC-022, DEC-041 (7)) | `id` do representante com o mesmo `text_hash`; nulo nos representantes e nos documentos sem texto. |
| `status` | `TEXT` | Não | — | DEC-041 (7) | `normalized` (representante ou sem texto) ou `ignored` (duplicado exacto). |
| `created_in_run` | `INTEGER` | Não | FK → `run(id)` | `run` em curso | Execução de `tde normalize` que criou o documento (DEC-041 (10)). |
| `created_at` / `updated_at` | `TEXT` | Não | — | Camada `storage` (relógio injectável) | UTC ISO 8601 com fuso. No M2.11, `updated_at` = `created_at` (as linhas não são alteradas). |

- **Fora da `0002`:** `proposed_category`, `proposed_subcategory`, `proposed_impact_type`, `proposed_legal_stage`, `relevance_flag` e `classified_by` pertencem ao CLASSIFY e entram numa migração dessa unidade (DEC-026). Nenhuma outra coluna é acrescentada.
- Os valores das enumerações (`source_tier`, `status`) são guardados no valor interno e validados pelo domínio antes da escrita, sem `CHECK` (como na `0001`).
- **Portabilidade (DEC-013, DEC-026):** as mesmas regras da `0001` — só `TEXT`/`INTEGER`, `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL` e `CREATE INDEX` simples. Sem `AUTOINCREMENT`, `WITHOUT ROWID`, `STRICT`, `INSERT OR REPLACE`, `PRAGMA` nem `CURRENT_TIMESTAMP`; sem `ON DELETE`/`ON CONFLICT`.

**Migração `0002`:**
- **Objectivo:** criar `source_document` (DEC-026 (4)).
- **Base vazia:** `tde init` aplica a `0001` e a `0002` por ordem, cada uma na sua transacção, com registo em `schema_migration`.
- **Base existente com só a `0001`:** `tde init` aplica apenas a `0002`, sem alterar dados nem tabelas existentes; uma segunda execução não aplica nada. Até lá, `tde sources sync`, `tde collect` e `tde normalize` terminam com `esquema não conforme` e pedem `tde init` (comportamento existente de DEC-028/DEC-031, inalterado).
- **Imutável depois de aplicada:** a `0001` não é editada; qualquer alteração futura a `source_document` é uma migração nova.
- **Compatibilidade:** as FK apontam para `raw_item`, `source_registry` e `run` da `0001`. DEC-029 não muda: uma fonte com documentos tem sempre `raw_item` nos seus endpoints, o que já impede a sua remoção ou alteração estrutural pelo sync.

**Comando `tde [--db PATH] normalize`** (DEC-041):

- **Entradas:** a base de dados no caminho resolvido (`--db`, depois `TDE_DB_PATH`, depois `data/tde.sqlite3`). Não lê `config/sources.yaml`, não sincroniza, não acede à rede, não usa IA. Sem opções próprias (`--source`, `--since`, `--dry-run` e `--no-llm` não fazem parte do M2.11).
- **Pré-condições, por esta ordem, antes de criar o `run`:** base existente (verificada antes de abrir qualquer ligação: não cria ficheiro nem directório); esquema conforme, incluindo a `0002` (mesma verificação do M2.7/M2.8: ficheiro que não é SQLite, migrações pendentes, desconhecidas ou com checksum diferente → erro). Em falha: `normalize: ERRO — <caminho>` e `- <motivo>` em stderr, código `1`, pedindo `tde init` quando aplicável; nenhum `run`, nenhuma migração e nenhuma escrita.
- **`run`** (DEC-031): no início, numa transacção própria, `command = "normalize"`, `started_at`, `finished_at` e `status` nulos. No fim, numa transacção própria, `finished_at`, `status` e `stats`. `outcome` e `report_path` ficam nulos.
- **Selecção:** `raw_item` sem `source_document` (pendentes), por ordem crescente de `id`.
- **Processamento de cada pendente, por ordem:**
  1. **`unsupported`** (não é falha; o item continua pendente; não há escrita): `source_endpoint_id` nulo (`sem endpoint`) ou `endpoint_type` diferente de `rss` (`sem regra de extracção para endpoint_type <tipo>`).
  2. **Extracção** (DEC-040) e **língua** (DEC-038). `raw_content` ilegível → **`failed`**, com o motivo `raw_content: XML malformado: <mensagem do parser>`, `raw_content: DOCTYPE não permitido` ou `raw_content: raiz não suportada: <raiz>`; não há escrita e o item continua pendente.
  3. **Construção** dos campos (ver *Esquema*). Um erro de validação do domínio → **`failed`**, com o motivo `<mensagem do domínio>`.
  4. **Inserção numa transacção do item:** procura de um documento existente com o mesmo `text_hash` e `duplicate_of` nulo. Se existir → `duplicate_of` = o seu `id`, `status = ignored` (**`duplicate`**). Senão → `duplicate_of` nulo, `status = normalized` (**`normalized`**). `text_hash` nulo → sem procura, `normalized`. Depois, `INSERT` com `created_in_run` e `created_at` = `updated_at`, e commit. O representante já registado nunca é substituído nem alterado; dentro da mesma execução, o primeiro pela ordem de `id` é o representante (DEC-022).
- **Erro da `storage`** (por exemplo, erro SQLite): rollback da transacção do item, código `1`, `run` com `finished_at` nulo (execução interrompida), como em DEC-031. Os documentos já confirmados mantêm-se, porque cada um é completo e coerente.
- **Estados finais e códigos:** `success` / código `0` (nenhum `failed`, incluindo zero pendentes e execuções só com `unsupported`); `partial` / código `2` (pelo menos um documento criado e pelo menos um `failed`); `failed` / código `1` (pelo menos um `failed` e nenhum documento criado).
- **`stats`** (JSON em `TEXT`):

```json
{
  "items": [
    {"raw_item_id": 0, "result": "failed", "reason": "<motivo>"}
  ],
  "totals": {"pending": 0, "normalized": 0, "duplicates": 0, "without_text": 0, "unsupported": 0, "failed": 0}
}
```

  `items` lista só os pendentes `unsupported` e `failed`, por ordem de `id`. `normalized` e `duplicates` contam documentos criados com `status` `normalized` e `ignored`; `without_text` conta, entre os `normalized`, os que têm `text` nulo; `pending` = total seleccionado = `normalized + duplicates + unsupported + failed`.
- **Saída:** em stdout, `normalize: OK — <caminho>` (código `0`), `normalize: PARCIAL — <caminho>` (código `2`) ou `normalize: ERRO — <caminho>` (código `1`), seguido de `run: <id>`, `pendentes: <n>`, `normalizados: <n>`, `duplicados: <n>`, `sem texto: <n>`, `não suportados: <n>` e `com falha: <n>`. Cada `failed` é indicado em stderr como `- raw_item <id>: <motivo>`.
- **Idempotência:** uma segunda execução sem `raw_item` novos cria um novo `run`, não cria `source_document`, não altera nenhuma linha existente e conta `0` pendentes, ou só os `unsupported`/`failed` anteriores, que são tentados de novo. Sem `raw_item`, termina com `success` e zero itens.
- **Sem efeitos laterais noutras tabelas:** `raw_item`, `source_registry`, `source_endpoint` e `config/sources.yaml` não são alterados; `last_success_at`/`last_error` não mudam.

**Fronteiras decididas:**

| Tema | No M2.11 | Fundamento |
|------|----------|------------|
| `canonical_url` | Sempre nulo; D12 OPEN | DEC-037 |
| `language` | Só `xml:lang` explícita; senão nulo | DEC-038 |
| `document_kind` | Sempre nulo (não determinado) | DEC-039 |
| Texto `rss` | `content:encoded` → `description`; HTML removido; sem texto → nulo | DEC-040 |
| `source_tier` | Tier da fonte `VALIDATED`, senão `T4`; pistas manuais (§3.4) ficam `unsupported` | SOURCES.md §3.1/§3.4; DEC-041 (8) |
| `published_at` | Regra de DEC-021; RFC 822 → nulo até D13 | DEC-021; D13 |
| `duplicate_of` | Representante já registado mantém-se; duplicados `ignored` | DEC-022; DEC-041 (7) |
| `proposed_*`, `relevance_flag`, `classified_by` | Fora da tabela | DEC-026 |
| Filtro de língua (`ignored` para não-`pt`) | Fora do M2.11. CONTENT_PIPELINE.md coloca-o no NORMALIZE, mas a excepção "fontes marcadas como multilíngues" não tem representação no registo (DEC-023), e com `language` quase sempre nulo o filtro não teria efeito fiável | Q10 |
| Janela temporal `max_age_days` | Fora do M2.11. CONTENT_PIPELINE.md coloca-a no NORMALIZE, mas: `published_at` é nulo nos itens RSS até D13; a excepção "documentos oficiais procurados como evidência" pertence à Fase 3; e nenhum ficheiro de configuração a define (aparece também em SCORING.md) | Q11 |

**Dependências:** M2.3 (normalização de título, texto e `published_at`; fingerprint), M2.4 (regra de DEC-022), M2.6 (`0001`, executor de migrações, resolução do caminho), M2.7/M2.8 (verificação de esquema, `run`, `raw_item` com `created_in_run`), M2.9 (forma de `raw_content` dos itens `rss`, salvaguarda de `DOCTYPE`). Decisões: DEC-021, DEC-022, DEC-026, DEC-031, DEC-032, DEC-033 §10, DEC-037 a DEC-041. Nenhuma dependência externa nova; nenhuma depende de D1, D7, Q2, Q3, Q5, Q6 ou Q7.

**Dados reais:** o M2.11 **não** introduz nem valida fontes, endpoints, URLs, feeds ou documentos reais. `config/sources.yaml` continua `[]`. Sem endpoints `ACTIVE`, não há `raw_item` em produção, e `tde normalize` termina com `success` e zero pendentes. Fixtures e testes usam só dados sintéticos com domínios reservados (RFC 2606).

**Exclusões:** cálculo de `canonical_url` e decisão de D12; detecção de língua pelo conteúdo e qualquer outra declaração além de `xml:lang` (Q8); regra de `document_kind` (Q9); filtro de língua (Q10); `max_age_days` (Q11); interpretação de datas além de DEC-021 (D13); extracção de HTML de páginas completas e collector `html_page`; `manual` e `tde add-manual` (incluindo a resolução de tier pelo domínio de SOURCES.md §3.4); Atom (Q2); transporte de `fetch`; colunas e etapa CLASSIFY; CLUSTER, `event`, `event_document`, VERIFY, `claim`, `source_evidence`; deduplicação aproximada; `editorial_decision`; `tde run`, `tde report` e relatório; política de retenção; `--source`, `--since`, `--dry-run`, `--no-llm`; IA; rede; execução agendada (D8); PostgreSQL; alterações a `raw_item`, à `0001`, ao collector `rss`, ao transporte, a `tde collect`, `tde sources validate`, `tde sources sync`, `tde doctor`, ao formato do YAML e a `config/`; fontes reais.

**Questões abertas (não resolvidas por inferência):**
- **D1, D7, D13, Q2, Q3, Q5, Q6, Q7** — continuam como no M2.10; nenhuma bloqueia o M2.11.
- **D12** — continua OPEN (DEC-037). Não há fundamento documental para uma lista de parâmetros de tracking.
- **Q8 — detecção de língua** (não bloqueante): regra para determinar `language` quando o item não declara `xml:lang` (pelo conteúdo, por outras declarações como `dc:language`, ou por `<channel><language>`, que exigiria alterar DEC-032). Até decisão, nulo.
- **Q9 — regra de `document_kind`** (não bloqueante para o M2.11; bloqueante antes da Fase 3): que etapa e que regra determinam o tipo de documento. Até decisão, nulo.
- **Q10 — filtro de língua e fontes multilíngues** (não bloqueante): se e onde se aplica o `ignored` para documentos não-`pt`, e como se representa uma fonte multilíngue no registo (alteraria DEC-023).
- **Q11 — janela temporal `max_age_days`** (não bloqueante): onde se configura, a que data se aplica enquanto `published_at` for nulo (D13) e como se concretiza a excepção para evidência oficial (Fase 3).

**Critérios de aceitação (verificáveis na implementação):**
1. **Migração:** numa base vazia, `tde init` aplica `0001` e `0002`; numa base com só a `0001` e dados, aplica apenas a `0002` e os dados ficam intactos; uma segunda execução não aplica nada. `source_document` tem exactamente as colunas, tipos, nulidade, PK, FK (`raw_item`, `source_registry`, `source_document`, `run`), `UNIQUE (raw_item_id)` e índice em `text_hash` do *Esquema*; as FK são aplicadas; nenhuma tabela da `0001` muda.
2. **Portabilidade:** a `0002` passa a verificação de construções proibidas do M2.6, e o SQL novo não usa `INSERT OR IGNORE`, `INSERT OR REPLACE` nem `ON CONFLICT`.
3. **Execução sobre a estrutura actual:** com `raw_item` criados por `tde collect` com o collector `rss` e transporte falso numa base criada por `tde init`, `tde normalize` cria um `source_document` por `raw_item` `rss` pendente, com `raw_item_id` e `created_in_run` correctos.
4. **`canonical_url`:** é nulo em todos os documentos, incluindo itens cujo `url` tem parâmetros (ex.: `utm_source`) ou fragmento; `raw_item.url` é preservado.
5. **`language`:** `xml:lang="pt-PT"` no `<item>` → `pt`; `xml:lang` no elemento escolhido prevalece sobre o do `<item>`; sem declaração, `xml:lang=""` ou valor fora da forma → nulo, mesmo em fonte T1 `VALIDATED`; `<channel><language>` não tem efeito.
6. **`document_kind`:** é nulo em todos os documentos; nenhum documento recebe `other`.
7. **Selecção do texto:** com `content:encoded` e `description`, o texto vem só de `content:encoded`; sem `content:encoded`, ou com `content:encoded` vazio depois da remoção de HTML, vem de `description`; `content:encoded` é reconhecido pelo URI do namespace, com o prefixo `ns0:` da serialização do M2.9.
8. **`raw_content` preservado:** `raw_item` (incluindo `raw_content` e `content_hash`) fica igual antes e depois de `tde normalize`.
9. **HTML:** HTML em CDATA e HTML escapado produzem o mesmo texto; entidades convertidas; etiquetas removidas; `script`/`style` e comentários descartados; os elementos de bloco de DEC-040 separam linhas e as etiquetas em linha não separam palavras; atributos não geram texto; o resultado é normalizado por DEC-021.
10. **Sem texto útil:** um item sem `content:encoded` nem `description` com texto → documento `normalized` com `text` e `text_hash` nulos e o título preservado; dois documentos destes nunca são duplicados entre si.
11. **`published_at`:** `pubDate` RFC 822 → nulo; um valor ISO 8601 com fuso explícito em `published_at_raw` (fixture) → UTC; sem fuso → nulo.
12. **`source_tier`:** fonte `VALIDATED` → tier da fonte; fonte `CANDIDATE` ou `INACTIVE` no momento da normalização → `T4`; `source_id` = fonte do endpoint.
13. **Deduplicação (DEC-022):** dois pendentes com o mesmo texto na mesma execução → o de menor `id` é `normalized` e o outro `ignored`, com `duplicate_of` igual ao primeiro; numa execução posterior, um novo item com o mesmo texto é `ignored` com `duplicate_of` igual ao representante já registado, que não é alterado.
14. **Sem classificação:** `source_document` não tem `proposed_*`, `relevance_flag` nem `classified_by`.
15. **Atomicidade:** um item com `raw_content` ilegível → `failed`, sem linha, os restantes processados, `run` em `partial` (código `2`) ou `failed` (código `1`, se nenhum documento foi criado); um erro da `storage` injectado → código `1`, `run` com `finished_at` nulo e sem linha do item interrompido.
16. **`run` (DEC-031):** cada execução após as pré-condições cria um `run` com `command = "normalize"`, fechado com `status` e `stats` do contrato; zero pendentes → `success`, código `0`; `unsupported` (endpoint `html_page` em fixture; `raw_item` sem endpoint) → contado, sem documento, item continua pendente, sem falha.
17. **Idempotência:** uma segunda execução sem `raw_item` novos não cria documentos nem altera linhas; os `failed`/`unsupported` são tentados de novo e contados.
18. **Pré-condições:** base inexistente → código `1`, sem ficheiro nem directório criados; esquema com a `0002` pendente ou não conforme → código `1`, pedindo `tde init`, sem migração aplicada; em ambos os casos, sem `run`.
19. **Isolamento:** SQL só em `storage/`; `storage` não importa `normalize`, `collectors` nem `sources`; `normalize/` não importa `storage`, `sqlite3` nem módulos de rede; só `collectors/http.py` importa módulos de rede.
20. **CLI:** `tde normalize` aparece em `tde --help`, sem opções próprias; `tde doctor`, `tde init`, `tde sources validate`, `tde sources sync` e `tde collect` mantêm interface e saídas.
21. **Determinismo:** a mesma base e o mesmo relógio injectado produzem os mesmos documentos, `text_hash` e `stats`.
22. **Sem dados reais:** `config/sources.yaml` continua `[]`; fixtures sintéticas com domínios reservados (RFC 2606); sem rede (salvaguarda do M2.9); nenhum teste escreve em `data/`.
23. **Sem dependências novas:** `pyproject.toml` sem dependências novas e `uv.lock` inalterado.
24. **Validação do repositório:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run tde doctor` e `uv lock --check` passam.

**Testes:** offline e deterministas, com bases de dados em directórios temporários, relógio injectado e fixtures sintéticas (`raw_item` construídos directamente ou por `tde collect` com transporte falso). Cobrem:
- a extracção (função pura, sem base de dados): candidatos, CDATA/escapado, prefixo `ns0:`, `script`/`style`, comentários, elementos de bloco e em linha, entidades, vazio, XML inválido, `DOCTYPE`, raiz errada;
- a língua;
- a migração `0002` em base vazia e em base existente;
- o esquema (colunas, FK, `UNIQUE`, índice);
- o domínio (novas invariantes de `SourceDocument`);
- o comando: pré-condições, `run`, estados e códigos, `stats`, saída, `unsupported`, atomicidade, erro da `storage`, idempotência, deduplicação na mesma execução e entre execuções, tier;
- o isolamento das camadas e a portabilidade do SQL.

Os testes existentes que fixam o conjunto de tabelas depois de `tde init`, ou os campos obrigatórios de `SourceDocument`, são actualizados para o novo contrato, sem enfraquecer as restantes verificações.

**Documentação a actualizar na implementação:**
- este ROADMAP (estado e *Implementação* do M2.11);
- [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §3 (`tde normalize` implementado; caminho da base também usado por `tde normalize`) e §5;
- [DATA_MODEL.md](DATA_MODEL.md) (cabeçalho, §2.1 `source_document` "implementado", §4);
- [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md), etapa 2;
- [DECISION_LOG.md](DECISION_LOG.md) ("Implementado em" de DEC-037 a DEC-041).

[SOURCES.md](SOURCES.md) e `config/` não mudam.

**Critérios de conclusão da definição (este documento):**
1. N1–N4 decididos por DEC-037 a DEC-040, sem lista de parâmetros de tracking e com D12 OPEN.
2. Contrato do comando, do `run`, da tabela e da migração `0002` definido (DEC-041 e esta secção).
3. Fronteiras de `source_tier`, `published_at`, `duplicate_of`, `proposed_*`, filtro de língua e `max_age_days` explícitas.
4. Questões abertas listadas sem resposta inferida.
5. Sem alterações a `src/`, `tests/`, `config/`, `pyproject.toml` nem `uv.lock`.

**Implementação:** migração `src/tensdireito_content_engine/storage/migrations/0002_source_document.sql` (16 colunas, `UNIQUE (raw_item_id)` e índice não único `source_document_text_hash`). Domínio: `SourceDocument` em `domain/sources.py`, com `id` nulo antes da escrita e as invariantes do *Âmbito* (2); enumeração `DocumentStatus` em `domain/enums.py`. Extracção em `normalize/rss.py` (`extract_rss_item`, `html_to_text`, `RawContentError`): primeira passagem com `xml.parsers.expat` que recusa `DOCTYPE`, depois `xml.etree.ElementTree`; `html.parser` com `convert_charrefs`; uma etiqueta de bloco vazia (`<br/>`) conta como uma só etiqueta (uma quebra). `text_hash` por `text_fingerprint` em `normalize/identity.py`, a mesma função SHA-256 que `fingerprint` (M2.3) usa. Repositório em `storage/source_documents.py`: `pending_raw_items` lê os pendentes em lotes de 100 por `id` crescente, limitados ao maior `raw_item.id` existente no início da execução, e cada lote só é lido depois de processado o anterior, pelo que os `unsupported`/`failed` não são relidos na mesma execução; `insert_source_document` procura o representante (`text_hash` igual e `duplicate_of` nulo, menor `id`) e insere na mesma transacção. Orquestração em `src/tensdireito_content_engine/normalize_command.py` (`run_normalize`), sem SQL; `tde [--db PATH] normalize` em `cli.py`. Um `tier` inválido de uma fonte `VALIDATED` é erro de validação do domínio (`failed`), com o motivo `source_tier tem de ser SourceTier: <valor>`. Testes offline em `tests/test_rss_extraction.py` e `tests/test_normalize_command.py`; os testes existentes que fixavam o conjunto de tabelas, as migrações e os campos de `SourceDocument` foram actualizados. Sem dependências novas; `config/sources.yaml` continua `[]`.

### M2.12 — CLASSIFY rules-only: definição documental

**Estado:** definição documental concluída; implementação pendente. Esta secção consolida o contrato pretendido. As decisões DEC-042 a DEC-045 estão em proposta e Q12–Q16 permanecem abertas; a respectiva revisão humana é pré-condição para implementar as partes por elas abrangidas. Não é criada qualquer implementação nesta unidade.

**M2.12 — CLASSIFY rules-only: definição documental concluída / implementação pendente.**

**Objectivo:** classificar deterministicamente cada `source_document` elegível, produzindo propostas por documento e persistindo-as para o CLUSTER. A unidade não precisa de fontes reais: a implementação e os testes usam documentos sintéticos. D1 não bloqueia tecnicamente CLASSIFY; continua a bloquear fontes reais, validação end-to-end com fontes reais e os gates de saída das fases.

#### M2.12 CONTRACT

1. **Fronteira funcional e entrada**
   - CLASSIFY recebe exclusivamente linhas persistidas de `source_document` cujo `status = normalized`, por `id` crescente, lidas do SQLite pela camada `storage`.
   - `status = ignored` (incluindo duplicados com `duplicate_of`), `classified` e `clustered` nunca entram. CLASSIFY não reabre nem reclassifica esses documentos. Documentos sem `source_document` não entram.
   - `text = NULL` continua elegível: só o `title` pode fornecer correspondências. Não se substitui texto ausente por título nem por conteúdo externo. Se o título também não sustentar uma regra, os campos ficam sem proposta e a relevância fica `uncertain`.
   - `language = NULL` significa desconhecida e não impede a execução; CLASSIFY não infere língua, não traduz nem filtra por língua. `document_kind = NULL` significa não determinado; não é inferido do texto, fonte, tier ou endpoint.
   - `source_id`, `canonical_url`, `published_at`, `source_tier`, `text_hash` e quaisquer outros campos nulos mantêm-se nulos. `source_tier` só é contexto de proveniência; não é evidência de conteúdo. A unidade não lê `config/sources.yaml` nem usa as categorias predominantes do registo de fontes para preencher uma classificação de documento (Q15).
   - Repetições textuais não alteram a regra de entrada: documentos duplicados que o NORMALIZE marcou `ignored` ficam excluídos; não se deduplica nem se agrupa nesta etapa.

2. **Saídas por documento e domínios**
   - Existem propostas para `category`, `subcategory`, `audience`, `impact_type`, `legal_stage` e `relevance_flag`; nunca se escreve directamente nos campos de `Event`.
   - `proposed_category`: nulo ou exactamente um código. Domínio: as 14 categorias de EDITORIAL_POLICY §4.1 e o código técnico `fora_de_ambito`. Não se cria categoria nova.
   - `proposed_subcategory`: nulo ou exactamente um código configurado, subordinado à categoria proposta. Os exemplos de EDITORIAL_POLICY §4.1 não constituem uma lista fechada nem são automaticamente códigos válidos.
   - `proposed_audience`: antes da classificação é SQL `NULL`; após a execução é sempre uma lista JSON de zero ou mais códigos, sem repetição, da lista inicial de EDITORIAL_POLICY §4.2. Lista vazia significa que nenhuma audiência foi sustentada; não equivale à audiência `populacao_geral`. Não se infere uma audiência a partir da categoria.
   - `proposed_impact_type`: nulo ou exactamente um dos 11 códigos de EDITORIAL_POLICY §4.3.
   - `proposed_legal_stage`: nulo ou exactamente um dos sete códigos de DATA_MODEL §3.3. É apenas uma proposta textual, nunca uma confirmação jurídica.
   - `relevance_flag`: obrigatório e exactamente `relevant`, `irrelevant` ou `uncertain`. É uma proposta documental, não o estado de relevância de um `Event`. Até Q12 ser decidida, CLASSIFY pode concluir `irrelevant` apenas por uma regra explícita que demonstre exclusão do âmbito; em todos os restantes casos grava `uncertain`, nunca `relevant`. A novidade face ao que já foi tratado não é decidida aqui.
   - Nos campos singulares (`category`, `subcategory`, `impact_type`, `legal_stage`), nulo significa que não há correspondência única sustentada pelas regras; não é um valor por defeito. `proposed_audience` só é SQL `NULL` antes da classificação; após execução, lista vazia significa que nenhuma audiência foi sustentada. `relevance_flag` é obrigatório após execução. Nenhum campo de classificação admite um valor literal `uncertain`; essa categoria de incerteza existe apenas em `relevance_flag`.
   - Cada saída tem proveniência no próprio documento. CLASSIFY V1 só admite `classified_by = "rules"`. Não pode gravar `human`, `llm:*` nem alegar revisão humana. A configuração que forneceu regras e o `run` que as aplicou têm de ser auditáveis (DEC-044, proposta).
   - As propostas são entradas de trabalho para CLUSTER. CLUSTER consolida propostas ao nível do assunto/evento, incluindo a audiência; VERIFY confirma claims, evidência e estágio suportado; SCORE calcula prioridade e proposta editorial. CLASSIFY não verifica, não cria nem consolida `Event`, não cria `event_document`, não calcula score nem decide estado editorial.

3. **Taxonomia e configuração**
   - A fonte de verdade dos domínios continua a ser EDITORIAL_POLICY §4 e DATA_MODEL §3.1–3.3: categorias, audiências, `impact_type` e `legal_stage` aí definidos não são duplicados nem redefinidos por YAML. `relevance_flag` mantém os três valores acima.
   - `config/taxonomy.yaml` será configuração das regras de correspondência; não será fonte de códigos alternativos. Esta unidade não cria o ficheiro. O schema fechado, versão declarada, validação de códigos, regras e fingerprint da configuração estão sujeitos às propostas DEC-043/044.
   - Qualquer código desconhecido, subcategoria sem categoria-pai válida, código repetido, regra com formato inválido ou configuração ausente/inválida é erro de configuração global: código de saída `1`, stderr explícito, nenhum `run` e nenhuma escrita de classificação.
   - Não há lista de palavras-chave de produção neste contrato. Uma regra só pode propor um valor quando uma correspondência literal, declarada e válida existir nos campos de texto autorizados. Não se inventa vocabulário com base em fixtures, nomes de fonte ou conhecimento externo.

4. **Correspondências, conflitos e ausência de evidência** *(semântica proposta em DEC-043; aprovação humana pendente)*
   - Cada lista de regras de `taxonomy.yaml` é obrigatória; pode estar vazia. Cada regra tem um identificador estável único, código e `match_any` não vazio. Uma subcategoria inclui ainda o código de categoria-pai; a regra de exclusão tem o código fixo `fora_de_ambito`, que não é um código de categoria dentro do âmbito. As listas são `category_rules`, `subcategory_rules`, `audience_rules`, `impact_type_rules`, `legal_stage_rules` e `exclusion_rules`; chaves desconhecidas, IDs repetidos e estrutura inválida falham validação. Os vocabulários fechados são verificados contra EDITORIAL_POLICY/DATA_MODEL; subcategorias são declaradas pelas próprias regras, sempre ligadas a uma categoria válida. O schema final é proposta em DEC-043 e requer aprovação antes da implementação.
   - Configuração define, por código, um conjunto de frases literais para procurar separadamente no `title` e no `text` não nulo; uma correspondência não atravessa a fronteira entre campos. A normalização para comparação, limites de palavra e schema executável exacto têm de ser aceites em DEC-043 antes da implementação. As correspondências válidas no mesmo código agregam-se; ordem das regras e frequência não desempata códigos diferentes.
   - Para os campos singulares (`category`, `subcategory`, `impact_type`), uma única proposta distinta sustentada produz esse código; nenhuma produz nulo; duas ou mais propostas distintas produzem nulo, sem desempate por frequência, tier ou ordem das regras.
   - Uma subcategoria só pode ser considerada depois de existir uma única categoria proposta; deve pertencer-lhe. Categoria ausente/ambígua ou subcategoria ambígua produz `proposed_subcategory = NULL`.
   - Para audiência, são propostas apenas as audiências cujas próprias regras correspondam; várias audiências distintas são permitidas, não são inferidas hierarquicamente e são guardadas sem duplicados numa ordem determinística. Nenhuma correspondência produz lista vazia, não nulo nem população em geral.
   - Para `legal_stage`, uma única correspondência produz esse estágio. Em conflito entre estágios ordenáveis aplica-se a regra conservadora de DEC-020: escolher o menos avançado sustentado; `not_applicable` só é escolhido se houver correspondência explícita e nenhuma correspondência a estágio ordenável. Sem correspondência, nulo. Nenhuma proposta torna o estágio oficialmente confirmado.
   - Uma regra explícita de exclusão só pode produzir `proposed_category = fora_de_ambito` e `relevance_flag = irrelevant` se não houver correspondência conflitante com uma categoria dentro do âmbito. Conflito de inclusão/exclusão produz relevância `uncertain` e não marca o documento como irrelevante.
   - Ausência de correspondência, correspondências em conflito ou ausência de contexto necessário produzem nulos nos campos singulares afectados; não se escolhe a regra “mais forte” sem prioridade formal. Ambiguidades devem ficar identificáveis em `run.stats`; não se resolvem por maioria, fonte, tier ou julgamento implícito.
   - A política editorial exige novidade face ao histórico (EDITORIAL_POLICY §6 e §10). Como CLASSIFY não compara com `Event` nem com o histórico, não pode afirmar novidade nem produzir `relevant` até decisão de Q12. CLUSTER recebe os documentos classificados como `uncertain`; a decisão de como converter essa proposta em relevância de evento permanece aberta.

5. **Persistência lógica, atomicidade e auditoria**
   - Os campos propostos ficam em `source_document`, relacionados 1:1 com o documento já existente; `raw_item_id`, `created_in_run` (run de NORMALIZE), título, texto e restantes dados de origem não são alterados.
   - Colunas lógicas necessárias: `proposed_category TEXT NULL`, `proposed_subcategory TEXT NULL`, `proposed_audience TEXT NULL` antes de classificar e JSON array obrigatório após, `proposed_impact_type TEXT NULL`, `proposed_legal_stage TEXT NULL`, `relevance_flag TEXT NULL` antes da classificação e obrigatório após, `classified_by TEXT NULL` antes e obrigatório após, `classified_in_run INTEGER NULL` antes e FK para `run` após, `classification_config_hash TEXT NULL` antes e obrigatório após, `classifier_version TEXT NULL` antes e obrigatório após. A migração correspondente é futura (sequência `0003` ou versão posterior); nenhuma migração é criada nesta definição.
   - Linha `normalized`: classificação ainda não executada, campos de proposta e auditoria de classificação nulos.
   - Linha classificada normalmente: `status = classified`, `classified_by = rules`, `classified_in_run`, hash de configuração e versão do classificador presentes; os valores propostos podem ser nulos/sem correspondência. Assim, “parcialmente classificada” significa execução concluída com um ou mais campos sem proposta, não falha nem estado intermédio.
   - Linha explicitamente fora do âmbito: `status = ignored`, `proposed_category = fora_de_ambito`, `proposed_audience = []`, `relevance_flag = irrelevant`, proveniência de regras e auditoria presentes. Um duplicado do NORMALIZE continua `ignored` sem proveniência de CLASSIFY (`classified_by IS NULL` e `duplicate_of IS NOT NULL`); não se confunde com uma exclusão de CLASSIFY.
   - A gravação de cada documento é all-or-nothing numa transacção própria: propostas, provenance, alteração de status e `updated_at` são gravados juntos; `created_at` e `created_in_run` mantêm-se. A escrita só pode actualizar uma linha ainda `normalized`. Se outra execução a tiver classificado desde a leitura dos pendentes, a escrita condicional não altera a linha e este run regista `skipped`; não sobrescreve resultados nem falha por esse motivo (DEC-045, proposta). Uma falha de regra/validação do documento não deixa actualização parcial e permite continuar os restantes. Erro de storage faz rollback do documento em curso, interrompe o comando com código `1` e deixa o `run` por concluir; documentos já confirmados mantêm-se, como em DEC-041.

6. **Pendente, idempotência e reclassificação**
   - Documento pendente é, exactamente, `source_document.status = normalized`. Documentos classificados, ignorados e agrupados não são pendentes.
   - Cada execução cria novo `run`, inclusive com zero pendentes. Repeti-la sem novos documentos não altera documentos anteriores; devolve zero pendentes e sucesso.
   - Alterar regras/configuração não reclassifica automaticamente documentos. Os já classificados preservam propostas e fingerprint da configuração anterior; só documentos ainda `normalized` usam a configuração actual.
   - Não existe reclassificação explícita em V1. Nenhuma opção CLI pode reabrir status ou sobrescrever proposta. A futura operação de reclassificação e o tratamento de eventos já agrupados exigem decisão própria (Q14).
   - O hash da configuração e a relação com o run ficam documentados na linha do documento e no `run.stats`; o formato final do hash e o versionamento do algoritmo ficam dependentes de DEC-044. Não se apresenta `classified_by = rules` como versão de regra.

7. **CLI, execução e isolamento**
   - Comando: `tde [--db PATH] [--config DIR] classify`. `--db` e `--config` são opções globais existentes; `--config` localiza apenas `taxonomy.yaml`. Sem opções próprias. `--source`, `--since`, `--dry-run`, `--no-llm`, `--event` e parâmetros de fornecedor são proibidos.
   - Pré-condições antes do `run`: base de dados existente; esquema conhecido/conforme com migrações aplicadas (sem migração implícita); configuração de taxonomia presente e integralmente válida. Qualquer falha → código `1`, stderr, sem `run` e sem alterações.
   - Após pré-condições, criar `run.command = "classify"` no padrão DEC-031, com `finished_at` e `status` nulos durante o trabalho; fechar com `finished_at`, `status` e JSON `stats`; `outcome` e `report_path` nulos.
   - `stats` contém hash/versão do classificador e lista ordenada por `source_document_id` com `result` (`classified`, `ignored`, `skipped` ou `failed`), estado de cada campo, códigos candidatos em caso de ambiguidade, IDs ordenados das regras correspondentes por campo e motivo de falha quando exista. Os IDs das regras que sustentam cada proposta são a proveniência específica da proposta; o `classified_in_run` liga o documento ao registo que os contém. Não se copia texto do documento para `stats`. Totais: `pending` (snapshot inicial), `classified`, `ignored`, `skipped`, `uncertain`, `failed`. `uncertain` conta documentos classificados com `relevance_flag = uncertain`.
   - Estados/códigos como DEC-031/041: `success` / 0 sem falhas (inclui zero pendentes, todos irrelevantes e documentos `skipped` por concorrência); `partial` / 2 se pelo menos um documento foi gravado e pelo menos um falhou; `failed` / 1 se houve falhas e nenhum documento foi gravado. Falha global de pré-condição ou storage: código 1. Sem falhas de documento, `ignored` e `skipped` não são falhas.
   - Toda a consulta e escrita SQL passa por `storage`; CLASSIFY/orquestração não importa `sqlite3` nem contém SQL. Não altera `Event`, `event_document`, `claim`, `source_evidence`, `score` ou `editorial_decision`.
   - Sem rede, sem leitura de `sources.yaml`, sem IA/LLM, fornecedor externo ou dependência de fontes reais. Não implementa CLUSTER, VERIFY, SCORE ou REPORT.

8. **Testes de aceitação da implementação**
   - Documento RSS sintético `normalized`, com texto e correspondências únicas, persiste as seis propostas e a proveniência esperadas; os valores sem suporte permanecem nulos.
   - Zero documentos elegíveis cria `run` `success`, código 0, contagens zero e nenhuma alteração a documentos.
   - `text = NULL`, `language = NULL`, `document_kind = NULL` e restantes campos nulos não fazem o comando falhar nem permitem inferir texto, língua, tipo, audiência ou categoria; só regras explícitas sobre `title` podem corresponder.
   - Documento `ignored` duplicado (`duplicate_of` preenchido) e documento já classificado são excluídos e não alterados; documentos em `clustered` também não entram.
   - Nenhuma correspondência deixa as propostas singulares nulas, `proposed_audience = []` e `relevance_flag = uncertain`; não cria códigos ou factos de preenchimento.
   - Uma e várias correspondências de categoria, subcategoria, audiência, `impact_type` e `legal_stage` verificam o domínio, cardinalidade, pai da subcategoria, proveniência por IDs das regras, ordem determinística e política de conflito/empate aprovada.
   - Conflitos inclusão/exclusão e empate entre códigos singulares nunca escolhem arbitrariamente um resultado; produzem nulos nos campos afectados, relevância incerta e informação de ambiguidade em `stats`.
   - Regras explícitas de exclusão só produzem `fora_de_ambito`/`irrelevant` nos casos sem conflito; irrelevantes ficam `ignored`, sem serem confundidos com duplicados.
   - A regra de relevância não afirma novidade histórica: até decisão Q12, nenhum documento recebe `relevant`; a implementação não consulta eventos.
   - Duas execuções sequenciais com a mesma configuração: a segunda encontra zero pendentes, cria run de sucesso e não altera linhas. Duas execuções concorrentes não sobrescrevem uma à outra: uma única transição de `normalized` é confirmada e a outra execução regista `skipped`. Alterar configuração não reclassifica automaticamente as linhas `classified`/`ignored`; uma linha ainda `normalized` usa a configuração validada pelo run que a persistir e guarda essa provenance.
   - Base ausente, migração pendente/desconhecida/checksum alterado, taxonomia ausente/inválida, código desconhecido, regra inválida e hash/versionamento inválido falham antes do run e sem escrita.
   - Falha injectada ao persistir um documento faz rollback integral dessa linha; falha de storage termina com código 1 e run inacabado; documentos de transacções anteriores mantêm-se.
   - Testes verificam que nenhuma `Event` é criada/alterada e não há rede, leitura de `sources.yaml`, chamada de IA, fonte real nem SQL fora de `storage`; migrations/config reais não são criadas nesta definição.

9. **Dependências futuras e questões explícitas**
   - DEC-042 propõe guardar `proposed_audience` por documento, em vez de usar prematuramente `Event.audience`; DEC-043 propõe o contrato das regras literais; DEC-044 propõe a provenance por hash/run. São propostas, não decisões aceites.
   - Q12: semântica de `relevance_flag` e fronteira com novidade histórica/CLUSTER.
   - Q13: aceitação do schema e semântica da configuração de regras e definição/revisão das regras lexicais concretas de produção.
   - Q14: reclassificação explícita e impacto de mudanças de regras em documentos já agrupados.
   - Q15: utilização ou não de `source_registry.categories` como sugestão/default por documento.
   - D1, D3, Q8, Q9, Q10 e Q11 permanecem OPEN. Também não se fecham D12/D13, D7, Q2/Q3/Q5/Q6/Q7. Esta definição não insere fontes nem antecipa gates de fase.
   - Q16: aceitação do controlo de concorrência por transição condicional de `normalized`, com registo `skipped`, em vez de serialização global dos comandos.

**Compatibilidade das etapas:** CLASSIFY produz apenas as propostas documentais descritas acima. CLUSTER compara documentos com eventos e consolida num `Event` único os atributos adequados, incluindo audiência (DEC-019/020); VERIFY cria claims/evidência e calcula a verificação e o estágio suportado; SCORE calcula dimensões e proposta editorial sem incorporar verificação. Nenhuma dessas responsabilidades é antecipada pelo CLASSIFY.

### Estado após M2.11 — D1 e unidade seguinte

- **D1 permanece OPEN e não bloqueia tecnicamente CLASSIFY.** D1 continua a bloquear fontes reais, a validação end-to-end dependente dessas fontes e os gates de saída da Fase 0/1. `config/sources.yaml` mantém-se vazio (`[]`); fixtures sintéticas são suficientes para testar CLASSIFY.
- **D3 permanece OPEN** e bloqueia apenas integração assistida por IA/fornecedor; CLASSIFY rules-only não chama IA.
- O relatório mínimo continua a ser trabalho separado sem contrato operacional completo. Não fica incluído no M2.12.
- Q8–Q11 continuam abertas; Q12–Q16 são novas questões desta definição. Nenhuma é fechada por inferência.

## Fase 0 — Arquitectura e documentação *(actual)*

- [x] Documentação técnica inicial em `docs/`.
- [x] Revisão e aprovação da arquitectura.
- [x] M1 — decisões fundamentais fechadas e registadas em [DECISION_LOG.md](DECISION_LOG.md).
- [ ] Decisões pendentes restantes resolvidas ou explicitamente adiadas (ver abaixo).

**Critério de saída:** documentação aprovada; lista de fontes T1 prioritárias acordada (D1).

## Fase 1 — Fundação e recolha (manual)

- Projecto Python gerido com `uv` (`pyproject.toml`, `uv.lock`), pacote `tensdireito_content_engine`, CLI `tde`, `ruff`, `pytest`.
- Camada `storage` com SQLite e migrações numeradas para `source_registry`, `source_endpoint`, `raw_item`, `source_document` e `run`: a migração inicial (M2.6) cobre `run`, `source_registry`, `source_endpoint` e `raw_item`; `source_document` entra numa migração seguinte, com a persistência da etapa NORMALIZE (DEC-026).
- Registo de fontes + `tde sources validate` (M2.5) + `tde sources sync`, sincronização explícita YAML → SQLite dos campos projectados (M2.7).
- Collectors `rss`, `html_page`, `manual` — apenas para endpoints validados. A orquestração de `tde collect`, o ciclo de vida de `run`, a persistência de `raw_item` e o contrato `Collector` são o M2.8 (DEC-031). O collector `rss` (RSS 2.0) e o transporte HTTPS restrito são o M2.9 (DEC-032, DEC-033); `html_page`, `manual` e o transporte de `fetch` ficam para unidades posteriores.
- NORMALIZE com deduplicação exacta. A normalização mecânica e a deduplicação exacta sem persistência são o M2.3 e o M2.4 (DEC-021, DEC-022); a persistência em `source_document`, a migração `0002` e `tde normalize` são o M2.11 (DEC-037 a DEC-041).
- Validação manual de 5–10 fontes (prioridade T1), registando endpoints reais só após confirmação, segundo o protocolo de [SOURCES.md](SOURCES.md#8-protocolo-de-validação-de-fontes) §8 (DEC-034). Unidade separada do M2.9: é trabalho humano, documentado e revisto por pull request; o modelo não infere URLs, feeds nem endpoints.
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

- Preparação manual disponível: `tde ingest` executa `sources sync → collect → normalize` numa base de dados já inicializada.
- DEC-046 foi suspensa pela DEC-048B e reactivada pela DEC-050: o workflow corre três vezes por dia, com resumo do run, etiquetas por área e fecho de rascunhos antigos (DEC-058). D8 (persistência durável) continua aberta. Os códigos `0`, `1` e `2` mantêm o contrato definido em DEC-046.
- Evolução futura: workflow persistente para `tde run`, depois de resolvida D8.
- Persistência conforme a decisão D8.
- Notificação com o relatório da execução.

**Critério de saída:** execuções agendadas estáveis durante 2 semanas sem intervenção; geração e revisão continuam manuais.

## Fase 6 — Evolução (a avaliar)

- Migração para PostgreSQL.
- Formatos `newsletter` e `social_post`.
- Envio automatizado para WhatsApp e integração de publicação (ex.: CMS do TensDireito.com), incluindo eventual uso do estado `PUBLISHED` — requer decisões de integração e operação; D10 define apenas o destino e a pré-visualização.
- Recolha automatizada de redes sociais — requer decisão (termos, custo, RGPD).
- Calibração de pesos por categoria, audiência, histórico de desempenho e tipo de notícia.
- Similaridade semântica (embeddings) para clustering.
- Interface de revisão web com autenticação.

### Decisão D10 — Destino de publicação WhatsApp

**Estado:** fechada por DEC-048 para o destino e o formato inicial.

O alvo V1 é a geração de mensagens para **canais e grupos de transmissão do WhatsApp**. `tde publish --target whatsapp --input <JSON>` valida a elegibilidade e imprime uma pré-visualização; não envia a mensagem nem altera o estado editorial. A integração de envio fica para evolução futura.

Formato: título apelativo iniciado por emoji, em `*negrito*`; 2–3 pontos-chave sobre o direito/notícia; CTA em destaque; e hiperligação HTTPS com `_Saiba mais:_` em itálico. A elegibilidade requer (DEC-063: sem limiar de score) `VERIFIED_EDITORIAL` ou `VERIFIED_OFFICIAL`, `APPROVED` por revisão humana e item não duplicado. Entradas inválidas ou inelegíveis não produzem pré-visualização publicável.

## Decisões pendentes

| # | Decisão | Fase | Estado / notas |
|---|---------|------|----------------|
| D1 | Fontes T1 prioritárias e confirmação de endpoints reais de cada uma | 1 | **Pendente (OPEN).** Lista candidata em [SOURCES.md](SOURCES.md). Só será fechada quando as fontes prioritárias e os respectivos endpoints forem validados manualmente; nenhum URL, feed, RSS ou API é assumido até lá. Protocolo de validação em [SOURCES.md](SOURCES.md#8-protocolo-de-validação-de-fontes) §8 (DEC-034). O M2.9 não a resolve nem a pressupõe. |
| D2 | Selecção de fontes T2/T3 (imprensa) | 1–2 | **Pendente.** Decisão editorial. |
| D3 | Fornecedor(es) de IA inicial(is) e orçamento mensal | 2 | **Pendente.** Interface agnóstica já definida. |
| D4 | Âmbito temático (taxonomia) | 2 | **Fechada no M1** — taxonomia V1 extensível (DEC-006). |
| D5 | Verificação na ausência de fonte oficial | 3 | **Fechada no M1** — máximo `VERIFIED_EDITORIAL`; override nunca produz `VERIFIED_OFFICIAL` (DEC-004). |
| D6 | Guia de estilo por formato | 4 | **Fechada no M1** — [STYLE_GUIDE.md](STYLE_GUIDE.md) (DEC-008); nota de responsabilidade proporcional ao risco (DEC-018). |
| D7 | Quem revê e aprova | 4 | **Parcialmente fechada** — formato do registo de revisão definido (DEC-014); pessoas concretas e eventual autenticação a decidir. |
| D8 | Persistência durável e estado partilhado em modo agendado (ex.: storage externo, PostgreSQL gerido) | **Antes da Fase 5** | **Em Avaliação / Pendente de Aprovação; não concluída.** A proposta DEC-047 recomenda PostgreSQL gerido + S3/R2 para relatórios, preservando a idempotência e o contrato rigoroso de exit codes do `tde daily` (`0` sucesso, `1` falha fatal, `2` parcial; código inesperado falha o job). Aguarda aprovação, confirmação de fornecedor/credenciais/custos e implementação/testes da camada `storage`. O M2.6 e o workflow diário em runner efémero não a resolvem. |
| D9 | Frequência e agendamento das execuções | 5 | **Suspensa (DEC-048; DEC-046 mantida como histórico).** O workflow é manual até D8 estar implementada; os códigos de saída `0`, `1` e `2` continuam a ter tratamento explícito. |
| D10 | Destino de publicação e integração com o TensDireito.com | 6 | **Fechada para destino e formato V1 (DEC-048):** WhatsApp, canais e grupos de transmissão; pré-visualização elegível, sem envio automático. Integração de envio/API e CMS continuam futuras. |
| D11 | Norma ortográfica do conteúdo publicado | 4 | **Fechada no M1 (CLOSED)** — AO1990, variante europeia, para todo o conteúdo público; documentação interna fora do âmbito; citações, legislação e nomes oficiais preservados (DEC-017). |
| D12 | Regra de `canonical_url`: que parâmetros são "de tracking" e se se normalizam esquema, domínio, barra final ou fragmento | 1 | **Pendente (OPEN).** DATA_MODEL.md exige `canonical_url` "sem parâmetros de tracking" sem os enumerar. Não se inventa nem assume nenhuma lista de parâmetros. Até decisão, o M2.3 não calcula `canonical_url` e preserva o URL tal como obtido (DEC-021). O projecto não tem nenhuma lista documentada de parâmetros de tracking; no M2.11, `source_document.canonical_url` fica nulo ("por calcular") até D12 ser decidida, segundo a orientação conservadora registada em DEC-037. |
| D13 | Formatos aceites em `published_at_raw` e tratamento de data sem hora ou data/hora sem fuso | 1 | **Pendente (OPEN).** Nenhum fuso (incluindo `Europe/Lisbon`) é assumido silenciosamente. Até decisão, só ISO 8601 com fuso explícito é convertido para UTC; os restantes casos ficam nulos, com o original preservado (DEC-021). Com o M2.9, `published_at_raw` de itens RSS virá do `pubDate` (formato RFC 822 em RSS 2.0), que DEC-021 não converte: até D13, esses itens terão `published_at` nulo na normalização. |
