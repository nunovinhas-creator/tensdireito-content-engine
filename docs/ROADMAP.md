# Roadmap

> Estado actual: **Fase 0 — Architecture / Documentation phase.** Milestone M1 (fecho das decisões arquitecturais e editoriais) concluído com o PR do M1, depois de revisto. M2 em curso: M2.1 (fundação executável), M2.2 (modelos de domínio) e M2.3 (normalização e identidade) concluídos e integrados (M2.3 no PR #5); M2.4 (deduplicação exacta por `text_hash`) implementado, em revisão. Os critérios de saída da Fase 0 continuam dependentes de D1.

Cada fase termina com critérios de saída verificáveis. Uma fase só começa quando os critérios da anterior estão cumpridos e as decisões pendentes relevantes estão tomadas.

## Milestones

| Milestone | Âmbito | Estado |
|-----------|--------|--------|
| Prompt 1 | Documentação inicial da arquitectura e especificação técnica. | Concluído |
| **M1** | Decisões arquitecturais e editoriais fundamentais: modelo de verificação, taxonomia V1, modelo de fontes, guia de estilo, política editorial, revisão humana, separação score/verificação, estados editoriais, persistência, tooling, decision log. Apenas documentação. | **Concluído com o PR do M1, depois de revisto** |
| M2 | Implementação por unidades: M2.1 fundação executável; M2.2 modelos de domínio; M2.3 normalização e identidade (DEC-021); M2.4 deduplicação exacta por `text_hash` (DEC-022) — usa o `text_hash` do M2.3, faz apenas deduplicação exacta, sem clustering nem deduplicação aproximada. | **Em curso** — M2.1, M2.2 e M2.3 concluídos e integrados; M2.4 implementado, em revisão |

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
