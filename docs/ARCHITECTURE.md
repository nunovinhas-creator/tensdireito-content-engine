# Arquitectura

> Estado: **Architecture / Documentation phase — decisões fundamentais fechadas no M1.** Este documento descreve a arquitectura-alvo da primeira implementação. Nada aqui está ainda implementado. As decisões e a sua justificação estão no [DECISION_LOG.md](DECISION_LOG.md).

## 1. Propósito

O TensDireito Content Engine é um *Editorial Intelligence Engine*: descobre informação sobre apoios sociais, direitos sociais, Segurança Social, emprego, habitação, fiscalidade e matérias afins; agrupa-a em acontecimentos; verifica-a contra fontes oficiais; pontua a sua relevância editorial; e apoia a produção de conteúdo, que só avança com aprovação humana.

O sistema **não é** um agregador de notícias nem um gerador automático de artigos. É uma ferramenta de apoio à decisão editorial, com rastreabilidade obrigatória entre cada afirmação e as respectivas fontes.

**Regra central:** descobrir não é verificar; verificar não é aprovar; aprovar não é publicar (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#2-regra-central)).

## 2. Princípios arquitecturais

| # | Princípio | Consequência na arquitectura |
|---|-----------|------------------------------|
| P1 | Descoberta ≠ verificação ≠ aprovação ≠ publicação | Entidades e estados separados para cada passo; nenhum atalho entre eles. |
| P2 | Alterações a direitos, valores, condições, prazos ou legislação exigem `VERIFIED_OFFICIAL` para serem afirmadas como facto | VERIFY procura evidência T1 adequada ao estágio da claim; sem ela, no máximo `VERIFIED_EDITORIAL`, que nunca é apresentado como confirmação legal. |
| P3 | Estados explícitos ao longo do ciclo de vida | Níveis de maturidade (secção 4), estados de verificação, estados editoriais e estados de revisão, cada um com campo próprio. |
| P4 | O `Event` é a unidade editorial | CLUSTER agrega notícias num único `Event` e actualiza-o com desenvolvimentos posteriores, em vez de criar duplicados. |
| P5 | "Nada a publicar" é um resultado válido | Cada execução produz um relatório que pode concluir "nada suficientemente importante para publicar". |
| P6 | IA assiste, não inventa, não verifica, não aprova | A IA opera sobre evidência fornecida; verificação por regras; aprovação humana. Ver [AI_RULES.md](AI_RULES.md). |
| P7 | Rastreabilidade afirmação → fonte | `claim` e `source_evidence` ligam cada afirmação a excertos literais. |
| P8 | Hierarquia de fontes | Cada fonte tem tier (T1–T4); só T1 produz `VERIFIED_OFFICIAL`. Source discovery ≠ source verification. |
| P9 | Redes sociais só como sinal | T4 pode gerar candidatos e sinais de interesse; nunca é evidência. |
| P10 | Múltiplos formatos a partir do mesmo acontecimento | Os formatos (`content_piece`) derivam do `Event`. |
| P11 | Monólito modular | Um único pacote Python modular; etapas desacopladas que comunicam pela base de dados. Sem microserviços, filas ou orquestradores. |
| P12 | Python + base de dados simples | SQLite na V1; SQL isolado numa camada de repositório para permitir migração para PostgreSQL. |
| P13 | Execução manual antes de automática | Cada etapa é um comando CLI. A automação apenas invoca os mesmos comandos, e só depois de decidida a persistência durável. |
| P14 | Independência de fornecedor de IA | Interface `LLMProvider`; fornecedor e modelo definidos por configuração. |
| P15 | Score ≠ verificação | `editorial_score` ordena; `verification_status` bloqueia. Um não altera o outro. |
| P16 | Humano no circuito | Na V1, só uma pessoa aprova conteúdo; a V1 termina em `APPROVED → EXPORT`. |

## 3. Visão conceptual

```
                 ┌───────────────────────────────────────────────────────────┐
                 │  source_registry (quem, tier) ─< source_endpoint (onde)   │
                 │  T1 oficiais · T2 especializadas · T3 imprensa · T4 sinal │
                 └───────────────┬───────────────────────────────────────────┘
                                 │  só endpoints validados e ACTIVE
 ┌──────────────┐   ┌────────────▼───┐   ┌──────────────┐   ┌──────────────┐
 │ 1. COLLECT   │──▶│ 2. NORMALIZE   │──▶│ 3. CLASSIFY  │──▶│ 4. CLUSTER   │
 │ descoberta   │   │ source_document│   │ categoria,   │   │ cria/actualiza│
 │ (raw_item)   │   │                │   │ impacto,     │   │ Event        │
 └──────────────┘   └────────────────┘   │ estágio      │   │ (CANDIDATE)  │
                                         └──────────────┘   └──────┬───────┘
                                                                   │
                    ┌──────────────────────────────────────────────▼───────┐
                    │ 5. VERIFY — claims + source_evidence                 │
                    │    UNVERIFIED · VERIFIED_EDITORIAL · VERIFIED_OFFICIAL│
                    │    · CONTRADICTED                                    │
                    ├──────────────────────────────────────────────────────┤
                    │ 6. SCORE — editorial_score (independente)            │
                    │    + gate de verificação → REJECT / WATCHLIST /      │
                    │      EDITORIAL_REVIEW                                │
                    └──────────────┬───────────────────────────┬───────────┘
                                   │                           │
                                   ▼                           ▼
 ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   Relatório: selecção /
 │ 10. EXPORT   │◀──│ 9. REVIEW      │◀──│ 7. GENERATE  │   watchlist / rejeitados /
 │ ficheiros    │   │ humano:        │   │ 8. CHECK     │   "nada suficientemente
 │ (não publica)│   │ APPROVED /     │   │ READY_FOR_   │   importante para publicar"
 └──────────────┘   │ REJECTED /     │   │ APPROVAL     │
                    │ NEEDS_REVISION │   └──────────────┘
                    └────────────────┘
```

Detalhe de cada etapa em [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md).

## 4. Níveis de maturidade da informação

| Nível | Designação | Entidade / estado | Significado |
|-------|-----------|-------------------|-------------|
| 1 | Informação descoberta | `raw_item` | Algo foi encontrado numa fonte. Nenhuma garantia de veracidade. |
| 2 | Informação normalizada | `source_document` | Texto limpo, metadados, duplicados exactos removidos, classificação proposta. |
| 3 | Candidato editorial | `event.editorial_status ∈ {CANDIDATE, WATCHLIST}` | Documentos agrupados num assunto potencialmente relevante. |
| 4 | Acontecimento verificado | `event.verification_status ∈ {VERIFIED_EDITORIAL, VERIFIED_OFFICIAL}` | As claims críticas têm evidência suficiente para o nível indicado. Só `VERIFIED_OFFICIAL` permite afirmar alterações legais como facto. |
| 5 | Conteúdo editorial | `content_piece.review_status ∈ {DRAFT, HUMAN_REVIEW_REQUIRED, NEEDS_REVISION}` | Texto num formato concreto, com referências às claims e fontes. |
| 6 | Aprovado | `content_piece.review_status = APPROVED` | Aprovado por uma pessoa identificada. Pode ser exportado. |

Publicação: fora do sistema na V1. O estado editorial `PUBLISHED` está reservado para uma futura integração.

Regras de transição:
- Só a etapa VERIFY altera o estado de verificação; nenhuma outra etapa (nem o score) marca um acontecimento como verificado.
- Nenhum evento `UNVERIFIED` ou `CONTRADICTED` chega a produção editorial.
- Só se passa de 5 para 6 por decisão humana explícita.
- Um acontecimento pode ser rejeitado ou arquivado em qualquer ponto, com motivo registado, e reaberto por desenvolvimento material.

## 5. Componentes

Um único pacote Python, **`tensdireito_content_engine`**, com CLI **`tde`**, organizado em módulos por responsabilidade. Os módulos não se chamam directamente entre etapas: **cada etapa lê da base de dados, faz o seu trabalho e escreve na base de dados**.

| Módulo | Responsabilidade |
|--------|------------------|
| `sources` | Carregar e validar o registo de fontes (`source_registry`, `source_endpoint`). |
| `collectors` | Recolha por tipo de endpoint (`rss`, `html_page`, `manual`). Interface comum `Collector`. |
| `normalize` | Extracção de texto, limpeza, datas, URL canónico, hash, deduplicação exacta, tier e tipo de documento. |
| `classify` | Propostas de categoria, subcategoria, audiência, `impact_type`, `legal_stage`, relevância. |
| `cluster` | Criação e actualização de `Event`; detecção de desenvolvimentos materiais. |
| `verify` | Claims, evidência, cálculo determinista do estado de verificação. |
| `scoring` | `editorial_score` e proposta de estado editorial, com gate de verificação. |
| `generate` | Produção de formatos a partir de um `Event` em `EDITORIAL_REVIEW`. |
| `checks` | Validações automáticas pós-geração. |
| `review` | Revisão humana e restantes decisões editoriais. |
| `export` | Exportação de conteúdo aprovado para ficheiros. |
| `report` | Relatório de cada execução (incluindo "nada a publicar"). |
| `llm` | Abstracção `LLMProvider`, registo de chamadas, prompts versionados. |
| `storage` | Camada de repositório sobre SQLite (V1); todo o SQL vive aqui. |
| `cli` | Ponto de entrada único (`tde`); um subcomando por etapa. |

Especificação técnica em [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).

## 6. Decisões arquitecturais (resumo)

Os ADR da especificação inicial mantêm-se, com as alterações do M1. O registo completo, com razões e alternativas, está no [DECISION_LOG.md](DECISION_LOG.md).

| ID | Decisão | Estado |
|----|---------|--------|
| ADR-001 | Pipeline por etapas com estado persistido; etapas idempotentes que comunicam pela base de dados. | Aceite |
| ADR-002 | SQLite na V1, PostgreSQL depois; SQL isolado em `storage`. Complementado por DEC-013 (persistência durável antes de agendamento). | Aceite, complementado |
| ADR-003 | O `Event` é a unidade editorial. Complementado por DEC-010 (actualizar em vez de duplicar). | Aceite, complementado |
| ADR-004 | Verificação baseada em evidência documental e regras deterministas, não em julgamento do modelo. Os estados passam a `VERIFIED_OFFICIAL`/`VERIFIED_EDITORIAL` (DEC-003). | Aceite, alterado |
| ADR-005 | IA atrás de uma interface; opcional em todas as etapas. | Aceite |
| ADR-006 | Humano no circuito; sem publicação automática na V1. Concretizado por DEC-012 e DEC-014. | Aceite, complementado |
| ADR-007 | CLI primeiro, automação depois; a automação não contém lógica própria. | Aceite |
| ADR-008 | Configuração (fontes, taxonomia, pesos, prompts) como ficheiros versionados revistos por pull request. | Aceite |

## 7. Fora do âmbito (V1)

- Publicação automática em qualquer canal (o sistema termina em `APPROVED → EXPORT`).
- Interface web/dashboard e autenticação.
- Recolha a partir de APIs de redes sociais.
- Pesquisa web aberta durante a verificação.
- Execução distribuída, filas de mensagens, microserviços.
- Execução agendada em produção antes da decisão sobre persistência durável.
- Pesquisa semântica com base de dados vectorial.

## 8. Documentos relacionados

- [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md) — política editorial, taxonomia, verificação, estados, revisão humana.
- [STYLE_GUIDE.md](STYLE_GUIDE.md) — estilo editorial e regras por formato.
- [DECISION_LOG.md](DECISION_LOG.md) — registo de decisões.
- [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) — stack, estrutura de código, CLI, configuração.
- [DATA_MODEL.md](DATA_MODEL.md) — entidades, estados e esquema.
- [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) — etapas em detalhe.
- [SOURCES.md](SOURCES.md) — modelo, hierarquia e registo de fontes.
- [SCORING.md](SCORING.md) — pontuação e limiares.
- [AI_RULES.md](AI_RULES.md) — regras de utilização de IA.
- [SECURITY.md](SECURITY.md) — segurança, privacidade e conformidade.
- [ROADMAP.md](ROADMAP.md) — fases de implementação e decisões pendentes.
