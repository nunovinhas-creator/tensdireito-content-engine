# Roadmap

> Estado actual: **Fase 0 — Architecture / Documentation phase.** Milestone M1 (fecho das decisões arquitecturais e editoriais) concluído com o PR do M1, depois de revisto. M2 em curso: M2.1 (fundação executável), M2.2 (modelos de domínio), M2.3 (normalização e identidade) e M2.4 (deduplicação exacta por `text_hash`) concluídos e integrados (M2.3 no PR #5, M2.4 no PR #6); M2.5 (registo de fontes e validação de fontes) implementado, em revisão. Os critérios de saída da Fase 0 continuam dependentes de D1.

Cada fase termina com critérios de saída verificáveis. Uma fase só começa quando os critérios da anterior estão cumpridos e as decisões pendentes relevantes estão tomadas.

## Milestones

| Milestone | Âmbito | Estado |
|-----------|--------|--------|
| Prompt 1 | Documentação inicial da arquitectura e especificação técnica. | Concluído |
| **M1** | Decisões arquitecturais e editoriais fundamentais: modelo de verificação, taxonomia V1, modelo de fontes, guia de estilo, política editorial, revisão humana, separação score/verificação, estados editoriais, persistência, tooling, decision log. Apenas documentação. | **Concluído com o PR do M1, depois de revisto** |
| M2 | Implementação por unidades: M2.1 fundação executável; M2.2 modelos de domínio; M2.3 normalização e identidade (DEC-021); M2.4 deduplicação exacta por `text_hash` (DEC-022) — usa o `text_hash` do M2.3, faz apenas deduplicação exacta, sem clustering nem deduplicação aproximada; M2.5 registo de fontes e validação de fontes (ver [M2.5](#m25--registo-de-fontes-e-validação-de-fontes)). | **Em curso** — M2.1 a M2.4 concluídos e integrados (M2.4 no PR #6); M2.5 implementado, em revisão |

### M2.5 — registo de fontes e validação de fontes

**Estado:** implementado, em revisão.

**Objectivo:** preparar a camada de fontes para os futuros collectors, sem os implementar: ler o registo versionado `config/sources.yaml` ([SOURCES.md](SOURCES.md#4-registo-configsourcesyaml) §4) para os modelos de domínio `SourceRegistry` e `SourceEndpoint` do M2.2 e validá-lo com `tde sources validate` ([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#3-interface-de-linha-de-comandos) §3).

**Entregáveis previstos:**
- Leitura de `config/sources.yaml`, no formato de SOURCES.md §4, para `SourceRegistry` e `SourceEndpoint`, respeitando os enums e invariantes do M2.2 sem os enfraquecer (ex.: fonte `CANDIDATE` sem `domains`; `VALIDATED`/`ACTIVE` com `validated_at` e `validated_by`). `validated_at` só é aceite com fuso explícito; nenhum fuso é assumido.
- Comando `tde sources validate`, local, determinista e sem escrita, que aplica as regras de SOURCES.md §4: esquema, IDs únicos, tiers válidos e campos obrigatórios; recusa endpoints `ACTIVE` sem `url` e sem `validated_at`. Regras que a documentação não define não são inventadas.
- Testes offline com registos fictícios (fixtures), sem fontes nem URLs reais.
- O parser YAML, se introduzido, segue a política de dependências de [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#1-stack) §1 (justificado no PR de implementação).

**Implementação:** `src/tensdireito_content_engine/sources/` (`registry.py`: conversão e regras; `yaml_loader.py`: leitura YAML segura) e `tde [--config DIR] sources validate` em `cli.py`. O comando escreve `sources: OK` e as contagens (código de saída `0`) ou `sources: ERRO` e todos os erros encontrados, pela ordem do ficheiro, em stderr (código de saída `1`). Representação das enumerações: estados em maiúsculas como na documentação (`CANDIDATE` → `candidate`); `entity_type`, `endpoint_type` e `tier` tal como o valor interno. Campos fora do formato de SOURCES.md §4 são recusados, com `validated_by` aceite por ser exigido pelo domínio para `VALIDATED`/`ACTIVE`. `validated_at` em ISO 8601 com fuso explícito é convertido para UTC; sem fuso é recusado. `fetch` é verificado como mapeamento, mas não tem correspondência nos modelos do M2.2 e não é convertido. `config/sources.yaml` foi criado vazio (`[]`), à espera de D1. Dependência introduzida: `pyyaml` (TECHNICAL_SPEC.md §7).

**Dependência de D1:** as regras de validação já estão definidas e não dependem de D1. O **conteúdo** do registo depende de D1 e fica fora do M2.5: o M2.5 não acrescenta fontes concretas, URLs, feeds, endpoints nem `domains`, e não marca nenhuma fonte ou endpoint como `VALIDATED`/`ACTIVE`. A validação manual de uma fonte (URL, termos de utilização, `robots.txt`) e a decisão `VALIDATE_SOURCE` em `editorial_decision` (que exige persistência) não são feitas por `tde sources validate`.

**Exclusões:** collectors; RSS; HTML; HTTP; scraping; qualquer acesso à rede (incluindo verificar se um URL responde); descoberta automática de fontes; SQLite, migrações e ORM; deduplicação; clustering; `SourceDocument`; `SourceEvidence`; claims; verificação; scoring; IA; scheduler; WhatsApp; publicação. Não altera D12 (não calcula `canonical_url`) nem D13 (não interpreta `published_at_raw`); ambas continuam OPEN.

## Fase 0 — Arquitectura e documentação *(actual)*

- [x] Documentação técnica inicial em `docs/`.
- [x] Revisão e aprovação da arquitectura.
- [x] M1 — decisões fundamentais fechadas e registadas em [DECISION_LOG.md](DECISION_LOG.md).
- [ ] Decisões pendentes restantes resolvidas ou explicitamente adiadas (ver abaixo).

**Critério de saída:** documentação aprovada; lista de fontes T1 prioritárias acordada (D1).

## Fase 1 — Fundação e recolha (manual)

- Projecto Python gerido com `uv` (`pyproject.toml`, `uv.lock`), pacote `tensdireito_content_engine`, CLI `tde`, `ruff`, `pytest`.
- Camada `storage` com SQLite e migração inicial (`source_registry`, `source_endpoint`, `raw_item`, `source_document`, `run`).
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
| D8 | Persistência durável e estado partilhado em modo agendado (ex.: storage externo, PostgreSQL gerido) | **Antes da Fase 5** | **Pendente e bloqueante** para qualquer execução agendada (DEC-013). |
| D9 | Frequência das execuções agendadas | 5 | **Pendente.** |
| D10 | Destino de publicação e integração com o TensDireito.com | 6 | **Pendente.** Na V1 apenas exportação de ficheiros. |
| D11 | Norma ortográfica do conteúdo publicado | 4 | **Fechada no M1 (CLOSED)** — AO1990, variante europeia, para todo o conteúdo público; documentação interna fora do âmbito; citações, legislação e nomes oficiais preservados (DEC-017). |
| D12 | Regra de `canonical_url`: que parâmetros são "de tracking" e se se normalizam esquema, domínio, barra final ou fragmento | 1 | **Pendente (OPEN).** DATA_MODEL.md exige `canonical_url` "sem parâmetros de tracking" sem os enumerar. Não se inventa nem assume nenhuma lista de parâmetros. Até decisão, o M2.3 não calcula `canonical_url` e preserva o URL tal como obtido (DEC-021). |
| D13 | Formatos aceites em `published_at_raw` e tratamento de data sem hora ou data/hora sem fuso | 1 | **Pendente (OPEN).** Nenhum fuso (incluindo `Europe/Lisbon`) é assumido silenciosamente. Até decisão, só ISO 8601 com fuso explícito é convertido para UTC; os restantes casos ficam nulos, com o original preservado (DEC-021). |
