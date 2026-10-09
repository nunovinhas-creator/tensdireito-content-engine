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
| P17 | Destino WhatsApp com gate editorial | A formatação para canais e grupos de transmissão só gera pré-visualizações de itens aprovados, validados, relevantes e não duplicados; não envia mensagens. |

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
| `publish` | Formatação e verificação de elegibilidade para destinos definidos; na V1, pré-visualização de mensagens WhatsApp sem envio automático. |
| `report` | Relatório de cada execução (incluindo "nada a publicar"). |
| `llm` | Abstracção `LLMProvider`, registo de chamadas, prompts versionados. |
| `storage` | Camada de repositório sobre SQLite (V1); todo o SQL vive aqui. |
| `cli` | Ponto de entrada único (`tde`); um subcomando por etapa. |

### Destino de publicação (D10)

O destino definido para a V1 é a geração de mensagens para **canais e grupos de transmissão do WhatsApp** (DEC-048). `tde publish --target whatsapp --input <JSON>` produz uma pré-visualização local; não envia mensagens, não usa a API do WhatsApp e não atribui `PUBLISHED`. A publicação efectiva continua manual/externa, em conformidade com o circuito `APPROVED → EXPORT`.

O manifesto de entrada fornece o título, emoji, 2–3 pontos-chave, CTA, hiperligação HTTPS, score, estados editorial e de verificação, e indicador de duplicação. A mensagem usa título em `*negrito*`, pontos-chave em lista, CTA e `_Saiba mais:_` em itálico junto à hiperligação. A elegibilidade exige simultaneamente:

- `editorial_score ≥ 65` (`SELECT_THRESHOLD`);
- `verification_status ∈ {VERIFIED_EDITORIAL, VERIFIED_OFFICIAL}`;
- `editorial_status = APPROVED` (aprovação humana);
- item não duplicado.

Itens inválidos ou que falhem qualquer gate não produzem mensagem e dão erro visível no CLI.

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
| ADR-006 | Humano no circuito; sem publicação automática na V1. Concretizado por DEC-012 e DEC-014; destino WhatsApp e gate de pré-visualização definidos por DEC-048. | Aceite, complementado |
| ADR-007 | CLI primeiro, automação depois; a automação não contém lógica própria. | Aceite |
| ADR-008 | Configuração (fontes, taxonomia, pesos, prompts) como ficheiros versionados revistos por pull request. | Aceite |

## 7. Proposta de persistência durável (D8)

> **Estado: Em Avaliação / Pendente de Aprovação.** A DEC-047 no [DECISION_LOG.md](DECISION_LOG.md) regista a recomendação para discussão; não é uma decisão aceite. D8 permanece OPEN até a proposta ser aprovada e os requisitos operacionais, fornecedor, credenciais e custos serem confirmados.

### Recomendação

Usar uma instância PostgreSQL gerida como fonte de verdade durável para os dados operacionais e editoriais, e armazenamento de objectos compatível com S3 (por exemplo, Cloudflare R2) para os relatórios diários. Esta abordagem serve tanto o runner efémero como o acesso partilhado pela revisão editorial, e está alinhada com a evolução PostgreSQL já prevista em ADR-002/DEC-013.

O workflow deve obter credenciais de curta duração por OIDC quando o fornecedor o suportar; caso contrário, usar secrets dedicados, com privilégios mínimos, TLS e rotação. A configuração editorial (`config/sources.yaml`) continua versionada no Git e sincronizada de forma unidireccional para a base de dados. Não guardar conteúdo de base de dados em commits.

### Fluxo e fronteiras

1. O runner liga-se à base PostgreSQL remota, verifica/aplica apenas migrações suportadas pela aplicação e executa `tde daily` contra esse estado partilhado. A ligação tem de falhar explicitamente quando a configuração ou o serviço estão indisponíveis; não se cria nem usa silenciosamente uma base SQLite vazia como fallback.
2. O relatório determinístico é escrito no armazenamento de objectos com uma chave estável por data (`daily/AAAA-MM-DD.txt`), permitindo que uma repetição do mesmo dia substitua o mesmo destino. Relatórios produzidos tanto em sucesso total como parcial são preservados; uma falha de publicação do relatório é uma falha de infraestrutura visível, não um sucesso.
3. Os objectos não substituem a base de dados como fonte de verdade. Artefactos GitHub Actions podem ser usados para diagnóstico efémero, mas não como persistência: expiram e não oferecem o estado partilhado exigido.
4. A camada `storage` isola driver, transacções e migrações. Como preparação, os repositórios e a lógica do pipeline usam agora o protocolo `storage.Connection`, em vez de expor `sqlite3.Connection`. Isto define apenas a superfície comum de execução/resultado: o adaptador actual, as migrações e o dialecto SQL continuam SQLite, pelo que ainda não existe intercambialidade com PostgreSQL. A implementação D8 terá de fornecer um adaptador e migrações PostgreSQL, mantendo SQL e decisões de fornecedor dentro de `storage`; validar todas as migrações e invariantes contra PostgreSQL antes de mudar o workflow de produção.

### Alternativas avaliadas

| Opção | Avaliação para D8 |
|---|---|
| PostgreSQL gerido + object storage para relatórios | **Recomendação.** Estado durável e partilhado, transacções e concorrência adequadas, acesso pela revisão editorial e alinhamento com ADR-002. Exige trabalho real no driver, migrações, credenciais e testes de integração; não é uma troca de URL. |
| Turso/libSQL | Alternativa plausível se a prioridade for conservar semântica SQLite. Continua a exigir um adaptador (o código actual depende de `sqlite3.Connection` e `PRAGMA`), testes de transacções/concorrência e confirmação de compatibilidade das migrações e do modelo de ligação escolhido. Evita algum trabalho de dialecto, mas cria uma escolha de plataforma que não é a evolução PostgreSQL já registada. |
| SQLite em S3/R2, com download/upload por execução | Não recomendado como fonte partilhada. O runner trabalha sobre uma cópia local; execuções concorrentes podem sobrescrever alterações, e o upload do ficheiro não oferece transacções partilhadas com a revisão editorial. Serializar o workflow reduz apenas a concorrência entre jobs, não resolve o acesso de outros clientes. |
| Commits ou artefactos GitHub Actions | Não recomendado como persistência canónica. Commits de dados causam churn e misturam estado mutável com código/configuração; artefactos têm retenção e acesso orientados a execução, não a uma base de dados partilhada. |

### Contratos do `tde daily`

- Preservar rigorosamente os códigos do CLI: `0` indica sucesso; `1` indica erro geral/fatal e tem de falhar o job; `2` indica falhas parciais de fontes e tem de manter o aviso visível no resumo sem descartar o relatório parcial. Qualquer código não previsto tem de falhar o job. Não traduzir uma falha parcial para sucesso silencioso nem esconder erros de ligação, migração ou publicação do relatório; falhas de infraestrutura devem ser observáveis como erro fatal (`1`).
- Manter as pré-condições e a ordem do pipeline existente. A configuração continua validada e sincronizada antes da recolha; falhas numa fonte não impedem o processamento das restantes.
- Preservar a idempotência existente: identidade de recolha por endpoint/URL/hash, criação única dos documentos normalizados, transacções atómicas das operações e substituição determinística do relatório do mesmo dia. Repetir a execução não deve duplicar dados; a chave estável do relatório por data deve actualizar o mesmo objecto, sem criar versões que pareçam execuções diferentes.
- Configurar um grupo de concorrência do workflow para reduzir sobreposição no mesmo ambiente, sem cancelar um job em curso. O GitHub Actions mantém no máximo uma execução pendente por grupo e pode substituir uma pendente por outra mais recente; por isso, esta configuração não é uma fila garantida. A base remota continua responsável pela integridade transaccional; o controlo de concorrência não substitui restrições nem idempotência.
- Testar o mesmo comportamento com falhas parciais, repetição no mesmo dia, indisponibilidade da base, erro de migração e falha de upload. O workflow só deve passar quando o estado e o relatório tiverem sido persistidos conforme o resultado do CLI.

### Revisão por GitHub Issues

O workflow é manual (`workflow_dispatch`) até existir persistência durável e partilhada; em seguida executa `tde daily` e `tde drafts sync-issues`, e preserva o relatório como artefacto por 14 dias. Para cada rascunho pendente e `unverified`, este comando procura a referência estável da fonte nas issues do repositório e cria uma issue apenas quando ainda não existe:

```text
COLLECT → NORMALIZE → SCORE → rascunho pending/unverified
                                  │
                           drafts sync-issues
                                  │
             issue [Rascunho WhatsApp] <Título>
             label draft-whatsapp
             mensagem + score + fonte + instruções
                                  │
             revisão humana → copiar → publicar → fechar issue
```

O URL da fonte é guardado como referência oculta no corpo da issue; a consulta inclui issues abertas e fechadas para a repetição de uma execução não reabrir o mesmo rascunho já tratado. O `GITHUB_TOKEN` recebe apenas `issues: write` além de `contents: read`. A issue regista a revisão/publicação operacional, mas o fecho não aprova nem altera a base SQLite local. Como o runner é efémero, não se liga o evento de fecho a `tde drafts approve` nem a `--mark-published`: isso não produziria um histórico durável e partilhado. A persistência PostgreSQL + object storage continua pendente em D8.

## 8. Fora do âmbito (V1)

- Publicação automática em qualquer canal (o sistema termina em `APPROVED → EXPORT`).
- Interface web/dashboard e autenticação.
- Recolha a partir de APIs de redes sociais.
- Pesquisa web aberta durante a verificação.
- Execução distribuída, filas de mensagens, microserviços.
- Execução agendada em produção com estado durável antes da decisão de persistência D8; o agendamento GitHub Actions actual é operacional/efémero e não constitui publicação automática.
- Pesquisa semântica com base de dados vectorial.

## 9. Documentos relacionados

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
