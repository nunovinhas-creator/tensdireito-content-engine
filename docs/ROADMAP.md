# Roadmap

> Estado actual: **Fase 0 — Architecture / Documentation phase**.

Cada fase termina com critérios de saída verificáveis. Uma fase só começa quando os critérios da anterior estão cumpridos e as decisões pendentes relevantes estão tomadas.

## Fase 0 — Arquitectura e documentação *(actual)*

- [x] Documentação técnica inicial em `docs/`.
- [x] Revisão e aprovação da arquitectura.
- [ ] Decisões pendentes da secção "Decisões pendentes" resolvidas ou explicitamente adiadas.

**Critério de saída:** documentação aprovada; lista de fontes T1 prioritárias acordada.

## Fase 1 — Fundação e recolha (manual)

- Estrutura do pacote Python, `pyproject.toml`, `ruff`, `pytest`.
- Camada `storage` com SQLite e migração inicial (`raw_item`, `document`, `source`, `run`).
- Registo de fontes + `tde sources validate`.
- Collectors `rss`, `html_page`, `manual`.
- NORMALIZE com deduplicação exacta.
- Validação manual de 5–10 fontes (prioridade T1).
- Relatório mínimo da execução.

**Critério de saída:** `tde collect && tde normalize` corre localmente, de forma idempotente, sobre as fontes validadas; testes offline com fixtures.

## Fase 2 — Classificação, agrupamento e pontuação

- `taxonomy.yaml` e CLASSIFY por regras.
- Interface `LLMProvider` + `NullProvider` + primeira implementação de fornecedor (após decisão).
- CLASSIFY assistida por IA.
- CLUSTER (similaridade lexical + sinais fortes).
- SCORE com `scoring.yaml` e relatório completo, incluindo "nada a publicar".
- Calibração com 2–4 semanas de dados reais.

**Critério de saída:** `tde run` produz relatório útil com eventos ordenados; editor confirma que a lista seleccionada é razoável.

## Fase 3 — Verificação e rastreabilidade

- Entidades `claim` e `evidence`.
- Extracção de claims e associação a evidência com validação literal de excertos.
- Cálculo determinista de `verification_status`.
- Gates de verificação na pontuação; watchlist.
- Comandos de override e fusão de eventos.

**Critério de saída:** nenhum evento `selected` sem claims críticas com evidência validada (ou override registado).

## Fase 4 — Produção editorial e revisão

- GENERATE para `whatsapp`, `article`, `seo_meta`.
- Validações automáticas pós-geração.
- REVIEW (`list`, `approve`, `reject`) e EXPORT.

**Critério de saída:** fluxo completo manual, de recolha a conteúdo `ready_to_publish` exportado, com rastreabilidade claim → fonte.

## Fase 5 — Automação

- Workflow GitHub Actions agendado para `tde run`.
- Armazenamento persistente da base de dados fora do runner.
- Notificação com o relatório da execução.

**Critério de saída:** execuções agendadas estáveis durante 2 semanas sem intervenção, com geração de conteúdo ainda despoletada manualmente.

## Fase 6 — Evolução (a avaliar)

- Migração para PostgreSQL.
- Formatos `newsletter` e `social_post`.
- Integração de publicação (ex.: CMS do TensDireito.com) — requer decisão.
- Recolha automatizada de redes sociais — requer decisão (termos, custo, RGPD).
- Similaridade semântica (embeddings) para clustering.
- Interface de revisão web.

## Decisões pendentes

Decisões a tomar antes (ou no início) da fase indicada:

| # | Decisão | Fase | Opções / notas |
|---|---------|------|----------------|
| D1 | Fontes T1 prioritárias para a Fase 1 e confirmação de mecanismo de recolha de cada uma | 1 | Lista candidata em [SOURCES.md](SOURCES.md). |
| D2 | Selecção de fontes T2/T3 (imprensa) | 1–2 | Decisão editorial. |
| D3 | Fornecedor(es) de IA inicial(is) e orçamento mensal | 2 | Interface já é agnóstica; afecta custos e termos de tratamento de dados. |
| D4 | Âmbito temático definitivo (taxonomia) | 2 | Lista inicial em [DATA_MODEL.md](DATA_MODEL.md#31-temas-taxonomyyaml-lista-inicial). |
| D5 | Regra de verificação na ausência de fonte oficial (2×T2 + override é suficiente?) | 3 | Proposta em [SOURCES.md](SOURCES.md#33-ausência-de-fonte-oficial). |
| D6 | Guias de estilo editorial por formato (tom, extensão, nota de responsabilidade) | 4 | Especificação inicial em [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-7--generate). |
| D7 | Quem revê e aprova (uma pessoa? várias?) | 4 | Afecta campo `actor` e eventual autenticação. |
| D8 | Armazenamento da base de dados em modo agendado (artefacto, storage externo, PostgreSQL gerido) | 5 | SQLite num runner efémero não persiste. |
| D9 | Frequência das execuções agendadas | 5 | Ex.: diária vs. várias vezes por dia. |
| D10 | Destino de publicação e formato de integração com o TensDireito.com | 6 | Na v1 apenas exportação de ficheiros. |
