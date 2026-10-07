# Arquitectura

> Estado: **Architecture / Documentation phase** — este documento descreve a arquitectura-alvo da primeira implementação. Nada aqui está ainda implementado.

## 1. Propósito

O TensDireito Content Engine é um *Editorial Intelligence Engine*: descobre informação sobre apoios sociais, direitos sociais, Segurança Social, emprego, habitação, fiscalidade e matérias afins; verifica-a contra fontes oficiais; agrupa-a em acontecimentos; pontua a sua relevância editorial; e transforma os acontecimentos verificados em conteúdo publicável para o TensDireito.com e outros canais.

O sistema **não é** um agregador de notícias nem um gerador automático de artigos. É uma ferramenta de apoio à decisão editorial, com rastreabilidade obrigatória entre cada afirmação e as respectivas fontes.

## 2. Princípios arquitecturais

| # | Princípio | Consequência na arquitectura |
|---|-----------|------------------------------|
| P1 | Descoberta ≠ confirmação | Etapas e estados separados para "descoberto" e "verificado"; nenhum atalho entre eles. |
| P2 | Alterações a direitos, valores, condições, prazos ou legislação exigem fonte oficial sempre que possível | A etapa de verificação procura evidência de nível T1 (ver [SOURCES.md](SOURCES.md)); sem ela o acontecimento fica limitado a `unverified`/`partially_verified`. |
| P3 | Estados explícitos ao longo do ciclo de vida | Seis níveis de maturidade da informação (secção 4), cada um com entidade/estado próprio no modelo de dados. |
| P4 | Deduplicação por acontecimento | Etapa de *clustering* que agrega vários itens num único `Event`. |
| P5 | "Nada a publicar" é um resultado válido | Cada execução produz um relatório que pode concluir explicitamente que nenhum acontecimento atinge o limiar. |
| P6 | IA assiste, não inventa nem verifica sozinha | A IA opera sobre evidência fornecida; a confirmação depende de documentos, não de respostas do modelo. Ver [AI_RULES.md](AI_RULES.md). |
| P7 | Rastreabilidade afirmação → fonte | Entidades `Claim` e `Evidence` ligam cada afirmação relevante a excertos de fontes concretas. |
| P8 | Hierarquia de fontes | Cada fonte tem um nível (T1–T4) que condiciona o que pode confirmar. |
| P9 | Redes sociais só como sinal | Fontes T4 podem gerar candidatos e sinais de tendência; nunca confirmam isoladamente. |
| P10 | Múltiplos formatos a partir do mesmo acontecimento | O `Event` verificado é a unidade editorial; os formatos (`ContentPiece`) são derivados dele. |
| P11 | Começar simples, evitar monólito desnecessário | Um único pacote Python modular, com etapas desacopladas que comunicam através da base de dados. Sem microserviços, filas ou orquestradores nesta fase. |
| P12 | Python + base de dados simples | SQLite na v1; acesso a dados isolado numa camada de repositório para permitir migração para PostgreSQL. |
| P13 | Execução manual antes de automática | Cada etapa é um comando CLI. A automação (GitHub Actions / cron) apenas invoca os mesmos comandos. |
| P14 | Independência de fornecedor de IA | Interface `LLMProvider` abstracta; fornecedor e modelo definidos por configuração. |

## 3. Visão conceptual

```
                 ┌───────────────────────────────────────────────────────────┐
                 │                   Registo de Fontes (YAML)                │
                 │        T1 oficiais · T2 especializadas · T3 imprensa      │
                 │                    · T4 redes / não confirmado            │
                 └───────────────┬───────────────────────────────────────────┘
                                 │
 ┌──────────────┐   ┌────────────▼───┐   ┌──────────────┐   ┌──────────────┐
 │ 1. COLLECT   │──▶│ 2. NORMALIZE   │──▶│ 3. CLASSIFY  │──▶│ 4. CLUSTER   │
 │ descoberta   │   │ texto, datas,  │   │ tema, tipo,  │   │ agrupa itens │
 │ (RawItem)    │   │ dedupe exacto  │   │ relevância   │   │ em Events    │
 └──────────────┘   │ (Document)     │   │ inicial      │   │ (candidate)  │
                    └────────────────┘   └──────────────┘   └──────┬───────┘
                                                                   │
 ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────▼───────┐
 │ 8. PUBLISH   │◀──│ 7. REVIEW      │◀──│ 6. GENERATE  │◀──│ 5. VERIFY    │
 │ (fora do     │   │ revisão humana │   │ formatos a   │   │ claims +     │
 │ âmbito v1:   │   │ ready_to_      │   │ partir do    │   │ evidência T1 │
 │ exportação)  │   │ publish        │   │ Event        │   │ + SCORE      │
 └──────────────┘   └────────────────┘   └──────────────┘   └──────────────┘
                                                                   │
                                              ┌────────────────────▼───────┐
                                              │ Relatório da execução:     │
                                              │ seleccionados / descartados│
                                              │ / "nada a publicar"        │
                                              └────────────────────────────┘
```

Detalhe de cada etapa em [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md).

## 4. Níveis de maturidade da informação

O sistema distingue seis níveis. Cada nível corresponde a uma entidade ou a um estado explícito no [modelo de dados](DATA_MODEL.md):

| Nível | Designação | Entidade / estado | Significado |
|-------|-----------|-------------------|-------------|
| 1 | Informação descoberta | `RawItem` | Algo foi encontrado numa fonte. Guardado tal como foi obtido. Nenhuma garantia de veracidade. |
| 2 | Informação normalizada | `Document` | Texto limpo, metadados extraídos (datas, URL canónico, língua), duplicados exactos removidos, classificação temática. |
| 3 | Candidato editorial | `Event.status = candidate` | Um ou mais documentos agrupados num acontecimento potencialmente relevante. Ainda não verificado. |
| 4 | Acontecimento verificado | `Event.status = verified` (ou `partially_verified`) | As afirmações críticas (`Claim`) têm evidência suficiente segundo as regras de verificação. |
| 5 | Conteúdo editorial | `ContentPiece.status = draft` / `in_review` | Texto produzido para um formato concreto, com referências às claims e fontes. |
| 6 | Pronto para publicação | `ContentPiece.status = ready_to_publish` | Aprovado por um humano. Pode ser exportado/publicado. |

Regras de transição:

- Só se passa de 3 para 4 através da etapa VERIFY; nenhuma outra etapa pode marcar um acontecimento como verificado.
- Só se passa de 5 para 6 por acção humana explícita (na v1).
- Um acontecimento pode ser descartado (`discarded`) em qualquer ponto, com motivo registado.

## 5. Componentes

Um único pacote Python (`tensdireito_engine`, nome provisório), com módulos por responsabilidade. Os módulos não se chamam directamente entre etapas: **cada etapa lê da base de dados, faz o seu trabalho e escreve na base de dados**. Isto permite correr etapas isoladamente, repetir etapas e substituir implementações.

| Módulo | Responsabilidade |
|--------|------------------|
| `sources` | Carregar e validar o registo de fontes (YAML). |
| `collectors` | Implementações de recolha por tipo de fonte (RSS, página HTML, entrada manual). Interface comum `Collector`. |
| `normalize` | Extracção de texto, limpeza, datas, URL canónico, hash de conteúdo, deduplicação exacta. |
| `classify` | Classificação temática e de tipo de alteração (regras + IA opcional). |
| `cluster` | Agrupamento de documentos em `Event`. |
| `verify` | Extracção de claims, procura e associação de evidência, cálculo do estado de verificação. |
| `scoring` | Cálculo da pontuação editorial e decisão de selecção. |
| `generate` | Produção de formatos (`ContentPiece`) a partir de um `Event` verificado. |
| `review` | Comandos para revisão humana, aprovação e rejeição. |
| `report` | Relatório de cada execução (incluindo "nada a publicar"). |
| `llm` | Abstracção `LLMProvider`, registo de chamadas, gestão de prompts versionados. |
| `storage` | Camada de repositório sobre SQLite (v1); esquema e migrações. |
| `cli` | Ponto de entrada único; um subcomando por etapa. |

Especificação técnica em [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).

## 6. Decisões arquitecturais (ADR resumidos)

**ADR-001 — Pipeline por etapas com estado persistido.**
Cada etapa é idempotente e comunica pela base de dados. *Alternativa rejeitada:* pipeline em memória num único processo — impede re-execução parcial, auditoria e revisão humana entre etapas.

**ADR-002 — SQLite na v1, PostgreSQL depois.**
Ficheiro único, zero infraestrutura, suficiente para o volume esperado (centenas a poucos milhares de itens/dia). Todo o SQL fica na camada `storage`; evitar funcionalidades específicas de SQLite. *Gatilho para migrar:* execução concorrente, múltiplos utilizadores ou necessidade de pesquisa full-text avançada.

**ADR-003 — O `Event` é a unidade editorial.**
Todas as decisões (pontuação, verificação, publicação) operam sobre acontecimentos, não sobre notícias individuais. Isto resolve a duplicação e permite gerar múltiplos formatos.

**ADR-004 — Verificação baseada em evidência documental, não em julgamento do modelo.**
O estado `verified` deriva de regras deterministas sobre a existência de evidência T1/T2 ligada às claims críticas. A IA pode *propor* associações entre claim e excerto; a regra decide.

**ADR-005 — IA atrás de uma interface.**
Nenhum módulo importa SDKs de fornecedores directamente, excepto as implementações de `LLMProvider`. A IA é opcional em todas as etapas: o pipeline tem de conseguir correr (com qualidade reduzida) sem IA.

**ADR-006 — Humano no circuito para publicação.**
Na v1, nenhum conteúdo passa a `ready_to_publish` sem aprovação humana. A publicação propriamente dita (envio para WordPress, WhatsApp, etc.) está fora do âmbito da v1 — o sistema produz ficheiros exportáveis.

**ADR-007 — CLI primeiro, automação depois.**
A automação (GitHub Actions) apenas encadeia comandos CLI já existentes; não contém lógica própria.

**ADR-008 — Configuração como ficheiros versionados.**
Fontes, pesos de pontuação, taxonomia e prompts vivem em ficheiros no repositório, revistos via pull request.

## 7. Fora do âmbito (v1)

- Publicação automática em qualquer canal.
- Interface web/dashboard.
- Recolha a partir de APIs de redes sociais (requer decisão sobre termos de utilização e custo).
- Execução distribuída, filas de mensagens, microserviços.
- Pesquisa semântica com base de dados vectorial (pode ser avaliada mais tarde para clustering).

## 8. Documentos relacionados

- [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) — stack, estrutura de código, CLI, configuração.
- [DATA_MODEL.md](DATA_MODEL.md) — entidades, estados e esquema.
- [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) — etapas em detalhe.
- [SOURCES.md](SOURCES.md) — hierarquia e registo de fontes.
- [SCORING.md](SCORING.md) — pontuação e limiares.
- [AI_RULES.md](AI_RULES.md) — regras de utilização de IA.
- [SECURITY.md](SECURITY.md) — segurança, privacidade e conformidade.
- [ROADMAP.md](ROADMAP.md) — fases de implementação.
