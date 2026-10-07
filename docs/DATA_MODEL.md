# Modelo de Dados

> Estado: **especificação conceptual (M1)**. Esquema-alvo para SQLite (V1), escrito de forma portável para PostgreSQL. Tipos indicados de forma lógica; datas em UTC, formato ISO 8601. Desde o M2.2 existem modelos de domínio (sem persistência) em `src/tensdireito_content_engine/domain/` para `event`, `source_registry`, `source_endpoint`, `source_document`, `source_evidence` e para as enumerações das secções 2–3; os campos de etapas ainda não implementadas (recolha, normalização, classificação) e as restantes entidades ficam para as unidades correspondentes. Desde o M2.3 existe `raw_item` (sem `id` nem `created_in_run`, que pertencem à persistência; `content_hash` calculado) e, em `src/tensdireito_content_engine/normalize/`, um intermédio `NormalizedItem` com os campos de `source_document` obtidos por transformação mecânica (`title`, `text`, `published_at`) e o `text_hash` (fingerprint) — ver DEC-021. Desde o M2.4 a deduplicação exacta por `text_hash` identifica, sem persistência, o representante e os duplicados (`duplicate_of`) — ver DEC-022. Desde o M2.5 (concluído e integrado, PR #8) `config/sources.yaml` é lido e validado para `source_registry` e `source_endpoint` (sem persistência; `fetch` ainda não é convertido) — ver [ROADMAP.md](ROADMAP.md#m25--registo-de-fontes-e-validação-de-fontes). Desde o M2.6 existe a camada `storage` (SQLite local) e `tde init`, que aplica a migração inicial `0001_init.sql` com `schema_migration`, `run`, `source_registry`, `source_endpoint` e `raw_item`, sem escrever dados de negócio; `source_document` fica para uma migração posterior — ver [ROADMAP.md](ROADMAP.md#m26--storage-sqlite-e-migração-inicial), DEC-026 e DEC-027.

**Convenção de nomes de estados.** Nos documentos, os estados conceptuais escrevem-se em maiúsculas (ex.: `VERIFIED_OFFICIAL`, `EDITORIAL_REVIEW`). Na implementação, o código armazenado será a mesma designação em minúsculas (ex.: `verified_official`). Não existem outros nomes para estes estados. Em `config/sources.yaml`, os estados (`registry_status`, `endpoint_status`) escrevem-se na forma documental em maiúsculas e são convertidos na leitura (DEC-024; [SOURCES.md](SOURCES.md#4-registo-configsourcesyaml) §4).

## 1. Visão geral

```
source_registry ──< source_endpoint ──< raw_item ──1:1── source_document >──< event_document >── event
                                                               │                                  │
                                                               │            ┌─────────────────────┼──────────────────────┐
                                                               │            │                     │                      │
                                                               └──< source_evidence >── claim   score             content_piece
                                                                                                                         │
                                       editorial_decision (todas as decisões humanas, incluindo revisão humana) ─────────┘

run ──< (registos com relação a run guardam created_in_run)        llm_call (auditoria de IA)
```

Três dimensões independentes de um `event` — nunca se substituem umas às outras (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md)):

| Dimensão | Campo | Responde a | Quem decide |
|----------|-------|-----------|-------------|
| Verificação | `event.verification_status` | "Está suficientemente confirmado? Com que nível?" | Regras deterministas sobre evidência (etapa VERIFY). |
| Prioridade | `score.editorial_score` | "Quão importante/útil é, comparado com os outros?" | Etapa SCORE. |
| Decisão editorial | `event.editorial_status` | "Em que ponto do circuito editorial está?" | SCORE propõe; transições a partir de `READY_FOR_APPROVAL` são sempre humanas. |

Correspondência com os níveis de maturidade (ver [ARCHITECTURE.md](ARCHITECTURE.md#4-níveis-de-maturidade-da-informação)):

| Nível | Onde vive |
|-------|-----------|
| 1. Descoberta | `raw_item` |
| 2. Normalizada | `source_document` |
| 3. Candidato editorial | `event` com `editorial_status ∈ {CANDIDATE, WATCHLIST}` |
| 4. Acontecimento verificado | `event` com `verification_status ∈ {VERIFIED_EDITORIAL, VERIFIED_OFFICIAL}` |
| 5. Conteúdo editorial | `content_piece` com `review_status ∈ {DRAFT, HUMAN_REVIEW_REQUIRED, NEEDS_REVISION}` |
| 6. Aprovado (pronto para exportação) | `content_piece` com `review_status = APPROVED`; `event.editorial_status = APPROVED` |

A publicação nos canais **não** é um nível gerido pelo sistema na V1 (ver secção 3.6).

## 2. Entidades

### 2.1 Modelo de fontes — quatro conceitos distintos

| Conceito | Entidade | Pergunta a que responde | Exemplo de natureza (sem URLs) |
|----------|----------|-------------------------|--------------------------------|
| **source_registry** | `source_registry` | *Quem* publica? Que confiança merece? | "Diário da República", "Segurança Social", um jornal nacional. |
| **source_endpoint** | `source_endpoint` | *Onde e como* se obtém informação dessa fonte? | Uma página de listagem, um feed, entrada manual. |
| **source_document** | `raw_item` + `source_document` | *O quê* concretamente foi obtido? | Uma notícia, um diploma, uma página de prestação. |
| **source_evidence** | `source_evidence` | *Que excerto literal* sustenta ou contradiz uma claim? | A frase do diploma que fixa um valor. |

Detalhe e regras em [SOURCES.md](SOURCES.md).

#### `source_registry`
Espelho do registo versionado `config/sources.yaml` (o YAML é a fonte de verdade). A sincronização é unidireccional YAML → SQLite; os campos operacionais de `source_endpoint` (`last_success_at`, `last_error`) só existem na base de dados (DEC-027). Mais precisamente, `source_registry` e `source_endpoint` são o espelho operacional dos **campos do registo projectados pelo domínio/storage**, por `tde sources sync` (M2.7, concluído e integrado; DEC-028): `fetch` fica fora da projecção no M2.7 e a coluna fica nula. Identidade pelo `id` do YAML; uma entrada retirada do YAML só é removida se nenhum `raw_item` a referenciar, e um endpoint referenciado não muda de `source_id` nem de `endpoint_type` (DEC-029). Estas tabelas não têm `created_in_run` (DEC-028). Nesta fase, `validated_at`/`validated_by` constituem o estado de validação operacional; `VALIDATE_SOURCE` em `editorial_decision` fica para unidade futura (DEC-030).

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | text PK | Identificador estável, ex.: `seg_social`. |
| `name` | text | |
| `entity_type` | text | `public_body` \| `official_journal` \| `government` \| `parliament` \| `specialised` \| `press` \| `social` \| `other`. |
| `tier` | text | `T1` \| `T2` \| `T3` \| `T4` (ver [SOURCES.md](SOURCES.md)). |
| `categories` | json | Categorias editoriais predominantes (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#4-taxonomia-editorial-v1)). |
| `domains` | json | Domínios web pertencentes à fonte. Preenchido **apenas** após validação manual. Vazio enquanto candidata. |
| `registry_status` | text | `CANDIDATE` \| `VALIDATED` \| `INACTIVE`. |
| `validated_at` / `validated_by` | datetime / text | |
| `notes` | text | |

#### `source_endpoint`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | text PK | |
| `source_id` | FK → source_registry | Uma fonte pode ter 0..N endpoints. |
| `endpoint_type` | text | `rss` \| `html_page` \| `manual` (outros tipos exigem decisão registada). |
| `url` | text, nulo | Nulo até validação. Nunca preenchido por suposição. |
| `fetch` | json | Frequência indicativa, `rate_limit_seconds`, `max_items`, selectores. |
| `endpoint_status` | text | `CANDIDATE` \| `VALIDATED` \| `ACTIVE` \| `INACTIVE`. Só `ACTIVE` é recolhido. |
| `validated_at` / `validated_by` | datetime / text | |
| `last_success_at` / `last_error` | datetime / text | Operacionais (DEC-027). Implementado no M2.8 (a integrar; DEC-031): actualizados por `tde collect` — sucesso → `last_success_at` actualizado e `last_error` nulo; falha → `last_error` actualizado e `last_success_at` preservado; sem alterar `updated_at` (DEC-028). |

#### `raw_item` — Nível 1 (captura bruta de um source_document)
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `source_endpoint_id` | FK → source_endpoint, nulo | Nulo para pistas manuais sem fonte registada. |
| `url` | text | URL tal como obtido. |
| `external_id` | text | GUID do feed, se existir. |
| `title` | text | |
| `raw_content` | text | HTML/XML/texto bruto (ou caminho para ficheiro, se grande). |
| `fetched_at` | datetime | |
| `published_at_raw` | text | Data tal como aparece na fonte. |
| `content_hash` | text | SHA-256 do conteúdo bruto. |
| `manual_note` | text | Apenas para entradas manuais. |
| `created_in_run` | FK → run | |

Unicidade: `(source_endpoint_id, url, content_hash)`.

#### `source_document` — Nível 2 (versão normalizada)
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `raw_item_id` | FK → raw_item, único | |
| `source_id` | FK → source_registry, nulo | Resolvido pelo endpoint, ou pelo domínio validado (ver [SOURCES.md](SOURCES.md#34-pistas-manuais)). |
| `canonical_url` | text | Sem parâmetros de tracking. |
| `title` | text | |
| `text` | text | Texto limpo. |
| `language` | text | Esperado `pt`. |
| `published_at` | datetime | Normalizada; nulo se desconhecida (nunca inventada). |
| `source_tier` | text | Copiado da fonte no momento da normalização; `T4` se a fonte não estiver validada. |
| `document_kind` | text | `legal_text` \| `consolidated_legal_text` \| `official_page` \| `official_communication` \| `news` \| `analysis` \| `social_post` \| `other`. |
| `text_hash` | text | Hash do texto normalizado (deduplicação exacta). |
| `duplicate_of` | FK → source_document, nulo | |
| `proposed_category` / `proposed_subcategory` | text | Proposta de classificação (regras ou IA). |
| `proposed_impact_type` / `proposed_legal_stage` | text | Proposta de classificação. |
| `relevance_flag` | text | `relevant` \| `irrelevant` \| `uncertain`. |
| `classified_by` | text | `rules` \| `llm:<prompt_id>`. |
| `status` | text | `normalized` \| `classified` \| `clustered` \| `ignored`. |

### 2.2 `event` — a unidade editorial (Níveis 3 e 4)

Um `event` representa **um assunto editorial** (ex.: "alteração do valor de uma prestação em 2027"), não uma notícia. Desenvolvimentos posteriores do mesmo assunto **actualizam** o mesmo `event` (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#10-event-actualizar-ou-criar)).

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `title` | text | Título neutro e descritivo (interno). |
| `summary` | text | Resumo interno, só com base nos documentos agrupados. |
| `category` | text | Categoria principal (uma). |
| `subcategory` | text, nulo | Subcategoria dentro da categoria principal. |
| `secondary_categories` | json | Outras categorias, para assuntos transversais (opcional). |
| `audience` | json | Lista de audiências-alvo. ≥1 obrigatório a partir de `WATCHLIST`; vazia só em `CANDIDATE`, `REJECT` e `ARCHIVED` (DEC-019). |
| `impact_type` | text | Ver 3.2. |
| `legal_stage` | text | Estágio da medida, calculado pela regra de 3.3 (DEC-020). Só é estágio oficialmente confirmado quando `verification_status = VERIFIED_OFFICIAL`. |
| `editorial_status` | text | Ver 3.5. |
| `status_reason` | text | Motivo do estado actual (ex.: `awaiting_official_confirmation`, `below_threshold`, `expired`). |
| `verification_status` | text | Ver 3.4. Calculado, nunca editado directamente. |
| `verification_notes` | text | O que falta confirmar, em linguagem legível. |
| `official_reference` | text | Referência do diploma/acto oficial, quando aplicável e verificada. |
| `effective_date` | date | Entrada em vigor, só se verificada. |
| `deadline` | date | Prazo relevante para o cidadão, só se verificado. |
| `first_seen_at` / `last_seen_at` | datetime | |
| `last_material_change_at` | datetime | Última alteração material (nova claim crítica, mudança de `legal_stage`, de valor ou de verificação). |
| `merged_into` | FK → event, nulo | Preenchido quando o evento foi fundido noutro. |
| `related_events` | json | Eventos relacionados mas distintos (ex.: o mesmo indicador noutro ano). |

### 2.3 `event_document`
| Campo | Tipo | Notas |
|-------|------|-------|
| `event_id` | FK | |
| `source_document_id` | FK | |
| `role` | text | `trigger` (originou o evento) \| `update` (trouxe desenvolvimento posterior) \| `supporting` \| `official_evidence`. |
| `similarity` | real | Pontuação de agrupamento. |
| `added_by` | text | `rules` \| `llm:<prompt_id>` \| `human`. |
| `added_at` | datetime | |

PK: `(event_id, source_document_id)`.

### 2.4 `claim` — afirmações verificáveis
Cada afirmação factual relevante de um evento, formulada **com o seu estágio**: "O Governo anunciou que o valor X passará a Y" e "O valor X é Y desde Z" são claims diferentes, com exigências de evidência diferentes.

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `event_id` | FK | |
| `text` | text | Afirmação atómica. |
| `claim_type` | text | `legal_reference` \| `legal_change` \| `right` \| `benefit` \| `amount` \| `limit` \| `eligibility` \| `deadline` \| `effective_date` \| `obligation` \| `administrative_rule` \| `procedure` \| `context` \| `other`. |
| `legal_stage` | text | Estágio a que a claim se refere (ver 3.3). |
| `critical` | bool | `true` para todos os tipos excepto `procedure` não obrigatório, `context` e `other` (ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify)). |
| `verification_status` | text | `UNVERIFIED` \| `VERIFIED_EDITORIAL` \| `VERIFIED_OFFICIAL` \| `CONTRADICTED`. |
| `extracted_by` | text | `llm:<prompt_id>` \| `rules` \| `human`. |
| `superseded_by` | FK → claim, nulo | Quando um desenvolvimento posterior substitui a claim. |

### 2.5 `source_evidence` — ligação claim → excerto de fonte
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `claim_id` | FK | |
| `source_document_id` | FK | Documento que contém o excerto. |
| `quote` | text | Excerto literal (obrigatório). |
| `quote_offset` | integer | Posição do excerto em `source_document.text`. |
| `stance` | text | `supports` \| `contradicts` \| `context`. |
| `source_tier` | text | Copiado do documento. |
| `document_kind` | text | Copiado do documento (determina o que a evidência pode confirmar). |
| `matched_by` | text | `rules` \| `llm:<prompt_id>` \| `human`. |
| `validated` | bool | `true` se o excerto foi encontrado literalmente no texto. Só evidência validada conta. |

### 2.6 `score`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `event_id` | FK | |
| `run_id` | FK | Uma pontuação por evento por execução (histórico mantido). |
| `components` | json | Valor de cada dimensão (ver [SCORING.md](SCORING.md)). |
| `penalties` | json | |
| `editorial_score` | real | 0–100. **Não** contém nenhuma componente de verificação. |
| `verification_status_at_scoring` | text | Cópia, apenas para auditoria da decisão. |
| `proposed_status` | text | `REJECT` \| `WATCHLIST` \| `EDITORIAL_REVIEW`. |
| `reasons` | json | Motivos da proposta (ex.: `awaiting_official_confirmation`, `capacity`). |
| `scoring_config_version` | text | Hash/versão de `scoring.yaml`. |

### 2.7 `content_piece` — Níveis 5 e 6
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `event_id` | FK | |
| `format` | text | `whatsapp` \| `article` \| `seo_meta` \| (futuro) `newsletter`, `social_post`. |
| `version` | integer | Incrementa a cada regeneração ou edição. |
| `title` | text | |
| `body` | text | Markdown/texto. |
| `metadata` | json | Ex.: slug, meta description, palavras-chave (SEO). |
| `claim_refs` | json | IDs das claims usadas no texto. |
| `source_refs` | json | Fontes citadas (derivadas das evidências). |
| `verification_snapshot` | json | Estado de verificação das claims referidas no momento da submissão a revisão. |
| `review_status` | text | Ver 3.6. |
| `generated_by` | text | `llm:<prompt_id>` \| `template` \| `human`. |
| `checks` | json | Resultado das validações automáticas (ver [AI_RULES.md](AI_RULES.md#6-validações-automáticas-pós-geração)). |
| `exported_at` | datetime, nulo | Preenchido pela exportação. Exportar **não** é publicar. |
| `superseded_by` | FK → content_piece, nulo | |

### 2.8 `editorial_decision` — registo auditável de decisões humanas (inclui revisão humana)
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `target_type` | text | `event` \| `content_piece` \| `claim` \| `source_registry` \| `source_endpoint`. |
| `target_id` | text | |
| `decision` | text | Ver 3.7. |
| `actor` | text | **Quem** decidiu. Identificação declarativa de uma pessoa (sem autenticação na V1). Nunca `llm:*`. |
| `decided_at` | datetime | **Quando**. |
| `note` | text | Nota. Opcional nas decisões de revisão; obrigatória nas decisões indicadas em 3.7. |
| `previous_state` / `new_state` | text | Estado antes e depois. |

### 2.9 `run`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `command` | text | |
| `started_at` / `finished_at` | datetime | |
| `status` | text | `success` \| `partial` \| `failed` (sucesso técnico da execução). |
| `stats` | json | Contagens por etapa, erros por fonte, tokens de IA. |
| `outcome` | text | `items_for_editorial_review` \| `nothing_to_publish` \| `n/a`. |
| `report_path` | text | |

Uso implementado no M2.8 (a integrar; DEC-031; contrato em [ROADMAP.md](ROADMAP.md#m28--recolha-local-ciclo-de-vida-de-run-persistência-de-raw_item-e-contrato-collector)): `tde collect` cria um `run` com `command = "collect"` e `started_at`; **durante a execução, `finished_at` e `status` são nulos** (não existe estado `running`); no fim grava `finished_at`, `status` (`success`, `partial` ou `failed`) e `stats` (contagens por endpoint e totais). `outcome` e `report_path` ficam nulos no M2.8. Um `run` com `finished_at` nulo representa uma execução interrompida ou não concluída. `run` não tem modelo de domínio; é tratado na camada `storage`. Os `raw_item` criados por `tde collect` guardam o `run` em `created_in_run`.

### 2.10 `llm_call`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `run_id` | FK | |
| `task` | text | |
| `prompt_id` | text | Ex.: `extract_claims@v3`. |
| `provider` / `model` | text | |
| `input_hash` | text | |
| `output` | text | |
| `input_tokens` / `output_tokens` | integer | |
| `latency_ms` | integer | |
| `error` | text | |

## 3. Enumerações e estados

### 3.1 Classificação editorial
`category`, `subcategory` e `audience` usam os códigos definidos em [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#4-taxonomia-editorial-v1) (a implementar em `config/taxonomy.yaml`). A taxonomia é extensível; acrescentar códigos é uma alteração de configuração revista por pull request e registada no [DECISION_LOG.md](DECISION_LOG.md) quando cria ou remove categorias.

### 3.2 `impact_type` — o que significa para o cidadão
`new_right`, `right_change`, `amount_change`, `new_obligation`, `obligation_change`, `deadline`, `procedure_change`, `payment_schedule`, `measure_ending`, `informational`, `other`. Definições em [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#43-impact_type).

### 3.3 `legal_stage` — em que fase está a medida
| Código | Significado | Pode ser apresentado como facto em vigor? |
|--------|-------------|-------------------------------------------|
| `not_applicable` | A claim não depende de um acto normativo (ex.: calendário publicado, procedimento). | n/a |
| `proposal` | Proposta, projecto, iniciativa legislativa ou consulta pública. | Não |
| `announcement` | Anúncio ou intenção política. | Não |
| `approved` | Aprovado pelo órgão competente, ainda não publicado. | Não |
| `published` | Publicado oficialmente, ainda não em vigor. | Não — indicar a data de entrada em vigor |
| `in_force` | Em vigor. | Sim, se `VERIFIED_OFFICIAL` |
| `ended` | Revogado, caducado ou terminado. | Sim (como terminado), se `VERIFIED_OFFICIAL` |

O `legal_stage` de um evento só avança com evidência que o sustente; nunca é inferido do tom de uma notícia.

**`legal_stage` do evento (DEC-020).** Ordem de avanço: `proposal` < `announcement` < `approved` < `published` < `in_force` < `ended`; `not_applicable` fica fora da ordem e só se usa quando nada tem estágio aplicável.
- Na criação (CLUSTER): o estágio menos avançado entre os `proposed_legal_stage` dos documentos agrupados.
- Em cada VERIFY (recalculado): o estágio mais avançado entre as claims críticas `VERIFIED_OFFICIAL` (ou entre todas as claims, se não houver críticas); sem nenhuma, o estágio menos avançado entre as claims (sem claims, entre os documentos).
- Só é **oficialmente confirmado** quando `event.verification_status = VERIFIED_OFFICIAL`; nos restantes casos é um estágio de trabalho e nunca é apresentado como facto jurídico. A redacção usa o estágio e a verificação de cada claim.

`impact_type` + `legal_stage` substituem o antigo campo único `change_type` (ver [DECISION_LOG.md](DECISION_LOG.md), DEC-005).

### 3.4 `verification_status` (claim e event)

| Valor | Na claim | No event (calculado a partir das claims) |
|-------|----------|------------------------------------------|
| `UNVERIFIED` | Sem evidência validada suficiente. | Alguma claim crítica `UNVERIFIED`, ou nenhuma claim com evidência validada. |
| `VERIFIED_EDITORIAL` | Sustentada por fontes credíveis e consistentes, sem evidência oficial suficiente para o seu estágio. | Nenhuma claim crítica `UNVERIFIED`/`CONTRADICTED`, mas pelo menos uma não é `VERIFIED_OFFICIAL`. |
| `VERIFIED_OFFICIAL` | Evidência oficial validada, adequada ao estágio da claim. | Todas as claims críticas `VERIFIED_OFFICIAL`. |
| `CONTRADICTED` | Evidência oficial validada contradiz a claim. | Pelo menos uma claim crítica `CONTRADICTED`. |

Regras completas em [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify). Os valores `verified`, `partially_verified` e `not_applicable` da especificação inicial deixam de existir (DEC-003).

### 3.5 `event.editorial_status`

```
CANDIDATE ──(SCORE)──┬──▶ REJECT
                     ├──▶ WATCHLIST ──(reavaliação)──▶ EDITORIAL_REVIEW / REJECT
                     └──▶ EDITORIAL_REVIEW ──(conteúdo passa validações)──▶ READY_FOR_APPROVAL
                                   ▲                                              │
                                   └──────────── NEEDS_REVISION ◀─────────────────┤ (humano)
                                                                                  ▼
                                                                              APPROVED ──▶ EXPORT (ficheiros)
                                                                                  │
                                                       PUBLISHED (reservado; não usado na V1)
                                                                                  │
                                                                                  ▼
                                                                              ARCHIVED
```

| Estado | Significado | Entrada |
|--------|-------------|---------|
| `CANDIDATE` | Estado técnico de entrada; ainda sem proposta editorial. | CLUSTER (novo evento ou reabertura). |
| `REJECT` | Não avança. Motivo obrigatório em `status_reason`. | SCORE, regras de rejeição, ou decisão humana. |
| `WATCHLIST` | Relevante, mas ainda não pronto (aguarda confirmação oficial, data, capacidade). Reavaliado em cada execução. | SCORE ou decisão humana. |
| `EDITORIAL_REVIEW` | Seleccionado para trabalho editorial: geração e edição de conteúdo. | SCORE (com gate de verificação) ou promoção humana. |
| `READY_FOR_APPROVAL` | Existe ≥1 `content_piece` em `HUMAN_REVIEW_REQUIRED`. | Validações automáticas passadas. |
| `APPROVED` | Um humano aprovou ≥1 `content_piece`. Exportável. | Decisão humana (sempre). |
| `PUBLISHED` | Publicado num canal. **Reservado para fase futura**; a V1 nunca o atribui. | — |
| `ARCHIVED` | Ciclo fechado: concluído, fundido noutro evento (`merged_into`) ou arquivado por decisão humana. | Decisão humana ou fusão. |

Regras:
- Nenhum evento chega a `EDITORIAL_REVIEW` com `verification_status ∈ {UNVERIFIED, CONTRADICTED}`.
- `audience` vazia só é permitida em `CANDIDATE`, `REJECT` e `ARCHIVED`; nenhum evento passa a `WATCHLIST` ou a um estado posterior sem ≥1 audiência. Um candidato sem audiência identificável é rejeitado com `no_audience` (DEC-019).
- `READY_FOR_APPROVAL → APPROVED` é **sempre** uma decisão humana.
- Um desenvolvimento material num evento em `REJECT`, `WATCHLIST`, `APPROVED` ou `ARCHIVED` reabre-o (`CANDIDATE`), mantendo o histórico. Eventos `ARCHIVED` por fusão não reabrem: reabre o evento de destino.
- Uma alteração ao `verification_status` de um evento em `EDITORIAL_REVIEW`, `READY_FOR_APPROVAL` ou `APPROVED` desencadeia reavaliação: se descer, o evento volta a `WATCHLIST` (ou `REJECT`, se `CONTRADICTED`) e as aprovações pendentes de exportação ficam invalidadas.

### 3.6 `content_piece.review_status`

```
DRAFT ──(validações automáticas passam)──▶ HUMAN_REVIEW_REQUIRED ──(humano)──┬──▶ APPROVED ──▶ (exported_at preenchido)
  ▲                                                                           ├──▶ REJECTED
  └──────────────────────── nova versão ◀──────────────────────────────────────┴──▶ NEEDS_REVISION
```

| Estado | Significado |
|--------|-------------|
| `DRAFT` | Gerado ou editado; validações automáticas por correr ou falhadas. Estado técnico, anterior à revisão. |
| `HUMAN_REVIEW_REQUIRED` | Passou as validações automáticas bloqueantes; aguarda decisão humana. |
| `APPROVED` | Aprovado por uma pessoa identificada. Pode ser exportado. |
| `REJECTED` | Rejeitado por uma pessoa; não será exportado. |
| `NEEDS_REVISION` | A pessoa pediu alterações; a correcção gera nova versão em `DRAFT`. |

- A peça aprovada é imutável: qualquer alteração gera nova versão (`superseded_by`) que volta a exigir revisão.
- Se uma claim referida mudar de estado de verificação após a aprovação e antes da exportação, a aprovação deixa de valer e a peça volta a `HUMAN_REVIEW_REQUIRED`.

### 3.7 `editorial_decision.decision`

| Decisão | Alvo | Nota |
|---------|------|------|
| `APPROVED` | content_piece | Opcional. |
| `REJECTED` | content_piece | Opcional (recomendada). |
| `NEEDS_REVISION` | content_piece | Opcional (recomendada — indica o que mudar). |
| `PROMOTE_TO_EDITORIAL_REVIEW` | event | **Obrigatória.** Só permitida para eventos `VERIFIED_EDITORIAL` ou `VERIFIED_OFFICIAL`. |
| `MOVE_TO_WATCHLIST` | event | Opcional. |
| `REJECT` | event | **Obrigatória.** |
| `ARCHIVE` / `REOPEN` | event | Opcional. |
| `MERGE` | event | Opcional; regista o evento de destino. |
| `OVERRIDE_VERIFICATION` | claim | **Obrigatória.** Só pode **baixar** o estado ou fixar `VERIFIED_EDITORIAL`; nunca produz `VERIFIED_OFFICIAL` (que exige evidência T1 ligada). |
| `ADD_EVIDENCE` | claim | Opcional. Evidência acrescentada manualmente (`matched_by = human`), sujeita às mesmas regras de validação. |
| `VALIDATE_SOURCE` / `DEACTIVATE_SOURCE` | source_registry / source_endpoint | **Obrigatória.** |

## 4. Notas de implementação

- Colunas `json` em SQLite como `TEXT` com JSON válido; em PostgreSQL como `JSONB`.
- Todas as tabelas com `created_at`, `updated_at`, `created_in_run` (quando aplicável: só onde a relação com `run` está definida neste modelo; `source_registry` e `source_endpoint` não a têm — DEC-028).
- Migrações numeradas (`storage/migrations/0001_init.sql`, ...), aplicadas por `tde init`; só para a frente, nunca editadas depois de aplicadas, registadas em `schema_migration` (DEC-026; contrato em [ROADMAP.md](ROADMAP.md#m26--storage-sqlite-e-migração-inicial)).
- Todo o SQL vive na camada `storage`; sem funcionalidades exclusivas de SQLite (ver [DECISION_LOG.md](DECISION_LOG.md), DEC-013).
- Nunca apagar `raw_item`/`source_document` usados como evidência; a política de retenção aplica-se apenas a itens nunca associados a eventos (ver [SECURITY.md](SECURITY.md)).
- Os campos desta especificação são conceptuais; desde o M2.6 a `0001_init.sql` materializa os de `run`, `source_registry`, `source_endpoint` e `raw_item`. O esquema final pode ajustar nomes técnicos, mantendo os conceitos e os estados aqui definidos.
