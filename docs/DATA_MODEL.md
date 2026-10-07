# Modelo de Dados

> Estado: **especificação**. Esquema-alvo para SQLite (v1), escrito de forma portável para PostgreSQL. Tipos indicados de forma lógica; datas em UTC, formato ISO 8601.

## 1. Visão geral

```
source ──< raw_item ──1:1── document >──< event_document >── event
                                                              │
                         ┌────────────────────────────────────┼─────────────────────┐
                         │                                    │                     │
                       claim ──< evidence >── document      score            content_piece
                                                                                    │
                                                                           editorial_decision

run ──< (todos os registos guardam created_in_run)     llm_call (auditoria de IA)
```

Correspondência com os níveis de maturidade (ver [ARCHITECTURE.md](ARCHITECTURE.md#4-níveis-de-maturidade-da-informação)):

| Nível | Onde vive |
|-------|-----------|
| 1. Descoberta | `raw_item` |
| 2. Normalizada | `document` |
| 3. Candidato editorial | `event` com `status = candidate` |
| 4. Acontecimento verificado | `event` com `verification_status ∈ {verified, partially_verified}` |
| 5. Conteúdo editorial | `content_piece` com `status ∈ {draft, in_review}` |
| 6. Pronto para publicação | `content_piece` com `status = ready_to_publish` |

## 2. Entidades

### 2.1 `source`
Espelho do registo `config/sources.yaml` (o YAML é a fonte de verdade; a tabela é sincronizada no `collect`).

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | text PK | Identificador estável, ex.: `seg_social_noticias`. |
| `name` | text | |
| `tier` | text | `T1` \| `T2` \| `T3` \| `T4` (ver [SOURCES.md](SOURCES.md)). |
| `source_type` | text | `rss` \| `html_page` \| `manual`. |
| `url` | text | |
| `topics` | json | Temas predominantes. |
| `active` | bool | |
| `last_success_at` | datetime | |
| `last_error` | text | |

### 2.2 `raw_item` — Nível 1
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `source_id` | FK → source | |
| `url` | text | URL tal como obtido. |
| `external_id` | text | GUID do RSS, se existir. |
| `title` | text | |
| `raw_content` | text | HTML/XML/texto bruto (ou caminho para ficheiro, se grande). |
| `fetched_at` | datetime | |
| `published_at_raw` | text | Data tal como aparece na fonte. |
| `content_hash` | text | SHA-256 do conteúdo bruto. |
| `manual_note` | text | Apenas para `source_type = manual`. |
| `created_in_run` | FK → run | |

Unicidade: `(source_id, url, content_hash)`.

### 2.3 `document` — Nível 2
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `raw_item_id` | FK → raw_item, único | |
| `canonical_url` | text | Sem parâmetros de tracking. |
| `title` | text | |
| `text` | text | Texto limpo. |
| `language` | text | Esperado `pt`. |
| `published_at` | datetime | Normalizada; nulo se desconhecida. |
| `source_tier` | text | Copiado da fonte no momento da normalização. |
| `text_hash` | text | Hash do texto normalizado (deduplicação exacta). |
| `duplicate_of` | FK → document, nulo | Preenchido se for duplicado exacto. |
| `topics` | json | Lista de códigos de `taxonomy.yaml`. |
| `change_type` | text | Ver 3.2. |
| `relevance_flag` | text | `relevant` \| `irrelevant` \| `uncertain`. |
| `classified_by` | text | `rules` \| `llm:<prompt_id>`. |
| `status` | text | `normalized` \| `classified` \| `clustered` \| `ignored`. |

### 2.4 `event` — Níveis 3 e 4
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `title` | text | Título neutro e descritivo (interno). |
| `summary` | text | Resumo interno, só com base nos documentos agrupados. |
| `topics` | json | |
| `change_type` | text | |
| `first_seen_at` | datetime | Data do documento mais antigo. |
| `last_seen_at` | datetime | |
| `status` | text | Ver 3.3. |
| `verification_status` | text | Ver 3.4. |
| `verification_notes` | text | O que falta confirmar. |
| `official_reference` | text | Ex.: referência de diploma no Diário da República, quando aplicável. |
| `effective_date` | date | Data de entrada em vigor, se conhecida e verificada. |
| `deadline` | date | Prazo relevante para o cidadão, se conhecido e verificado. |
| `discard_reason` | text | |
| `merged_into` | FK → event, nulo | Quando dois eventos se revelam o mesmo. |

### 2.5 `event_document`
| Campo | Tipo | Notas |
|-------|------|-------|
| `event_id` | FK | |
| `document_id` | FK | |
| `role` | text | `trigger` (originou o evento) \| `supporting` \| `official_evidence`. |
| `similarity` | real | Pontuação de agrupamento. |
| `added_by` | text | `rules` \| `llm:<prompt_id>` \| `human`. |

PK: `(event_id, document_id)`.

### 2.6 `claim` — afirmações verificáveis
Cada afirmação factual relevante de um evento (valor, prazo, condição, data, entidade abrangida, diploma).

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `event_id` | FK | |
| `text` | text | Afirmação atómica, ex.: "O valor do IAS em 2027 é X €". |
| `claim_type` | text | `amount` \| `date` \| `deadline` \| `eligibility` \| `legal_reference` \| `procedure` \| `other`. |
| `critical` | bool | `true` se altera direitos, valores, condições, prazos ou legislação. |
| `status` | text | `unsupported` \| `supported` \| `confirmed_official` \| `contradicted`. |
| `extracted_by` | text | `llm:<prompt_id>` \| `human`. |

### 2.7 `evidence` — ligação afirmação → fonte
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `claim_id` | FK | |
| `document_id` | FK | Documento que contém a evidência. |
| `quote` | text | Excerto literal do documento (obrigatório). |
| `quote_offset` | integer | Posição do excerto no `document.text` (para validação). |
| `stance` | text | `supports` \| `contradicts` \| `context`. |
| `source_tier` | text | Copiado do documento. |
| `matched_by` | text | `rules` \| `llm:<prompt_id>` \| `human`. |
| `validated` | bool | `true` se o excerto foi encontrado literalmente no texto (validação automática). |

### 2.8 `score`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `event_id` | FK | |
| `run_id` | FK | Uma pontuação por evento por execução (histórico mantido). |
| `components` | json | Valor de cada dimensão (ver [SCORING.md](SCORING.md)). |
| `penalties` | json | |
| `total` | real | 0–100. |
| `decision` | text | `selected` \| `watchlist` \| `rejected`. |
| `scoring_config_version` | text | Hash/versão de `scoring.yaml`. |

### 2.9 `content_piece` — Níveis 5 e 6
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `event_id` | FK | |
| `format` | text | `whatsapp` \| `article` \| `seo_meta` \| (futuro) `newsletter`, `social_post`. |
| `version` | integer | Incrementa a cada regeneração. |
| `title` | text | |
| `body` | text | Markdown/texto. |
| `metadata` | json | Ex.: slug, meta description, palavras-chave (SEO). |
| `claim_refs` | json | IDs das claims usadas no texto. |
| `source_refs` | json | Fontes citadas (derivadas das evidências). |
| `status` | text | Ver 3.5. |
| `generated_by` | text | `llm:<prompt_id>` \| `template` \| `human`. |
| `checks` | json | Resultado das validações automáticas (ver [AI_RULES.md](AI_RULES.md#6-validações-automáticas-pós-geração)). |

### 2.10 `editorial_decision`
Registo auditável de decisões humanas.

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `target_type` | text | `event` \| `content_piece` \| `claim`. |
| `target_id` | integer | |
| `action` | text | `approve` \| `reject` \| `discard` \| `override_verification` \| `merge` \| `edit`. |
| `reason` | text | Obrigatório em `reject`, `discard`, `override_verification`. |
| `actor` | text | Identificação do revisor. |
| `created_at` | datetime | |

### 2.11 `run`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `command` | text | |
| `started_at` / `finished_at` | datetime | |
| `status` | text | `success` \| `partial` \| `failed`. |
| `stats` | json | Contagens por etapa, erros por fonte, tokens de IA. |
| `outcome` | text | `items_selected` \| `nothing_to_publish` \| `n/a`. |
| `report_path` | text | |

### 2.12 `llm_call`
| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | integer PK | |
| `run_id` | FK | |
| `task` | text | |
| `prompt_id` | text | Ex.: `extract_claims@v3`. |
| `provider` / `model` | text | |
| `input_hash` | text | Hash do input (o input completo pode ser guardado opcionalmente). |
| `output` | text | |
| `input_tokens` / `output_tokens` | integer | |
| `latency_ms` | integer | |
| `error` | text | |

## 3. Enumerações

### 3.1 Temas (`taxonomy.yaml`, lista inicial)
`seguranca_social`, `prestacoes_familiares`, `desemprego`, `emprego_formacao`, `pensoes_reforma`, `deficiencia_incapacidade`, `habitacao`, `fiscalidade_irs`, `saude`, `educacao`, `energia_custo_vida`, `consumo`, `direitos_laborais`, `outros`.

### 3.2 Tipo de alteração (`change_type`)
`new_benefit`, `benefit_change` (valor/condições), `deadline` (prazo a decorrer/novo prazo), `legislation` (novo diploma/alteração legal), `procedure` (alteração de procedimento/canal), `payment_calendar`, `announcement` (anúncio político sem diploma), `informational` (sem alteração), `other`.

`announcement` é distinto de `legislation`: um anúncio não constitui alteração de direitos até existir diploma ou regulamentação.

### 3.3 `event.status` (ciclo editorial)
```
candidate ──▶ scored ──▶ selected ──▶ in_production ──▶ done
    │            │           │
    │            ├──▶ watchlist (reavaliado em execuções seguintes)
    │            └──▶ rejected
    └──────────────────────────────▶ discarded (qualquer ponto, com motivo)
                                    merged (fundido noutro evento)
```

### 3.4 `event.verification_status`
| Valor | Regra (determinista, ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify)) |
|-------|-------|
| `unverified` | Nenhuma claim crítica com evidência validada. |
| `partially_verified` | Algumas claims críticas com evidência T1 validada, outras não. |
| `verified` | Todas as claims críticas com evidência T1 validada **ou**, quando não existe fonte oficial aplicável, ≥2 evidências T2 independentes, com override humano registado. |
| `contradicted` | Pelo menos uma claim crítica contradita por evidência T1. |
| `not_applicable` | Evento sem claims críticas (ex.: puramente informativo). |

### 3.5 `content_piece.status`
`draft` → `in_review` → `ready_to_publish` → `exported`; ou `rejected`; `superseded` quando existe versão mais recente.

## 4. Notas de implementação

- Colunas `json` em SQLite como `TEXT` com JSON válido; em PostgreSQL como `JSONB`.
- Todas as tabelas com `created_at`, `updated_at`, `created_in_run` (quando aplicável).
- Migrações numeradas (`storage/migrations/0001_init.sql`, ...), aplicadas por `tde init`.
- Nunca apagar `raw_item`/`document` usados como evidência; aplicar política de retenção apenas a itens nunca associados a eventos (ver [SECURITY.md](SECURITY.md)).
