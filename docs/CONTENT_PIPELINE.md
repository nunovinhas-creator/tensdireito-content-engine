# Pipeline de Conteúdo

> Estado: **especificação (M1)**. Descreve as etapas, entradas, saídas e regras de passagem. Cada etapa é um comando CLI independente (ver [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#3-interface-de-linha-de-comandos)). O que já está implementado ou definido por milestone é indicado em cada etapa; o resto continua por implementar.

Regra central (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#2-regra-central)): **descobrir não é verificar; verificar não é aprovar; aprovar não é publicar.**

## Visão geral

| # | Etapa | Entrada | Saída | IA | Efeito no estado |
|---|-------|---------|-------|----|------------------|
| 1 | COLLECT | endpoints `ACTIVE` | `raw_item` | Não | Nível 1 — descoberta |
| 2 | NORMALIZE | `raw_item` novos | `source_document` | Não | Nível 2 — normalizada |
| 3 | CLASSIFY | `source_document` normalizados | categoria, impacto, estágio, relevância (propostas) | Opcional | — |
| 4 | CLUSTER | documentos relevantes | `event` novo ou actualizado | Opcional | `CANDIDATE` |
| 5 | VERIFY | eventos activos | `claim`, `source_evidence`, `verification_status` | Opcional (assistida) | Nível 4 se `VERIFIED_*` |
| 6 | SCORE | eventos `CANDIDATE`/`WATCHLIST` | `score`, proposta editorial | Opcional (componentes) | `REJECT` / `WATCHLIST` / `EDITORIAL_REVIEW` |
| 7 | GENERATE | eventos `EDITORIAL_REVIEW` | `content_piece` (`DRAFT`) | Sim (com fallback por template) | Nível 5 |
| 8 | CHECK | `content_piece` `DRAFT` | `checks` | Não | `HUMAN_REVIEW_REQUIRED`; evento `READY_FOR_APPROVAL` |
| 9 | REVIEW | `content_piece` `HUMAN_REVIEW_REQUIRED` | decisão humana | **Não** | `APPROVED` / `REJECTED` / `NEEDS_REVISION` |
| 10 | EXPORT | `content_piece` `APPROVED` | ficheiros | Não | `exported_at` (não é publicação) |
| — | REPORT | execução | relatório | Não | — |

`tde run` executa 1→6 e o REPORT. As etapas 7–10 são despoletadas manualmente na V1. **A V1 termina em `APPROVED → EXPORT`; não existe publicação automática.**

---

## Etapa 1 — COLLECT

**Objectivo:** obter informação bruta. Não interpreta nem verifica.

> Implementado (M2.8, integrado no PR #14; DEC-031): infra-estrutura e orquestração de COLLECT — `tde collect [--source ID]` lê os endpoints `ACTIVE` do espelho SQLite (sem sincronização implícita de `config/sources.yaml`), cria e fecha um `run`, chama o `Collector` registado para cada `endpoint_type`, grava `raw_item` com `created_in_run` (atomicidade por endpoint; itens já existentes não são duplicados) e actualiza `last_success_at`/`last_error`. Contrato em [ROADMAP.md](ROADMAP.md#m28--recolha-local-ciclo-de-vida-de-run-persistência-de-raw_item-e-contrato-collector). **Continuam fora:** collectors concretos (`rss`, `html_page`, `manual`), HTTP, `robots.txt`, `User-Agent`, rate limiting, transporte de `fetch`, `--since`, pistas manuais (`tde add-manual`) e a recolha de documentos oficiais associados.

> Implementado (M2.9; DEC-032, DEC-033): primeiro collector concreto, `rss` (RSS 2.0), com o único transporte de rede do sistema (HTTPS restrito, sem redirects, destino público, `robots.txt` verificado). Não segue links dos itens nem recolhe documentos associados; não normaliza nem interpreta datas. Sem endpoints reais até D1. Contrato em [ROADMAP.md](ROADMAP.md#m29--primeiro-collector-concreto-rss-com-transporte-https-restrito).

- Lê o registo de fontes; recolhe apenas endpoints `ACTIVE` (validados — ver [SOURCES.md](SOURCES.md)).
- Usa o `Collector` correspondente a `endpoint_type`.
- Guarda cada item como `raw_item`; ignora se `(source_endpoint_id, url, content_hash)` já existe.
- Respeita `rate_limit`, `robots.txt` e `user_agent` (ver [SECURITY.md](SECURITY.md)).
- Para endpoints T1, quando o item aponta para um documento oficial no mesmo domínio validado, guarda também esse documento — poderá servir de evidência.
- Pistas manuais (`tde add-manual`) entram aqui; o tier é determinado pelo domínio (ver [SOURCES.md](SOURCES.md#34-pistas-manuais)), por defeito T4.

**Falhas:** erro num endpoint → registado em `last_error` e `run.stats`; os restantes continuam.

## Etapa 2 — NORMALIZE

> Implementado (M2.3): apenas a normalização mecânica de título, texto e `published_at` e o `text_hash` (DEC-021). Implementado (M2.4): deduplicação exacta por `text_hash` sobre itens normalizados, que identifica representantes e duplicados (`duplicate_of`) sem os alterar (DEC-022); o registo `status = ignored` pertence à persistência. Extracção de HTML, `canonical_url` (D12), tier, `document_kind`, língua e janela temporal ficam para unidades posteriores.

> Implementado (M2.11; DEC-037 a DEC-041): persistência em `source_document` (migração `0002`) por `tde normalize`, com `run` no padrão de DEC-031 e deduplicação exacta persistida (duplicados `ignored`, com `duplicate_of` para o representante já registado). Texto de itens `rss` a partir de `content:encoded`, senão de `description`, sem HTML (DEC-040); `canonical_url` nulo enquanto D12 estiver OPEN (DEC-037); `language` só por `xml:lang` explícita, senão nulo (DEC-038); `document_kind` só quando houver regra mecânica documentada — no M2.11, nulo (DEC-039); `source_tier` pela regra abaixo. O filtro de língua e a janela temporal, abaixo, continuam por decidir e ficam fora do M2.11 (Q10, Q11). Contrato em [ROADMAP.md](ROADMAP.md#m211--persistência-da-etapa-normalize).

- Extrai texto principal; remove navegação, publicidade, boilerplate.
- Normaliza `published_at` para UTC; se não for possível, deixa nulo (nunca inventa data).
- Calcula `canonical_url`, `text_hash`; duplicados exactos → `duplicate_of`, `status = ignored`.
- Determina `source_tier` (T4 se a fonte não estiver `VALIDATED`) e `document_kind`.
- Documentos não-`pt` ficam `ignored` (salvo fontes marcadas como multilíngues).
- Itens fora da janela temporal (`max_age_days`, por defeito 14) ficam `ignored`, excepto documentos oficiais procurados como evidência.

## Etapa 3 — CLASSIFY

**Objectivo:** propor categoria, subcategoria, audiência, `impact_type`, `legal_stage` e relevância.

1. **Regras** (sempre): palavras-chave por categoria (`config/taxonomy.yaml`), categorias por defeito da fonte, exclusões.
2. **IA** (opcional): classificação estruturada (`classify@vN`) com justificação curta.
3. Conflito regras vs. IA → `relevance_flag = uncertain` (segue, com penalização no score).
4. `legal_stage` proposto nunca é mais avançado do que o texto do próprio documento sustenta; na dúvida, o estágio menos avançado.

Saída: documentos `irrelevant` ficam `ignored`; os restantes seguem. As classificações são **propostas**; os valores do evento são consolidados no CLUSTER e podem ser corrigidos por humanos.

## Etapa 4 — CLUSTER

**Objectivo:** garantir que cada assunto editorial é **um** `event` (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#10-event-actualizar-ou-criar)).

Algoritmo V1 (simples e explicável):
1. Comparar cada documento novo com eventos existentes **em qualquer estado**, excepto os fundidos (`merged_into`), dentro de uma janela de procura configurável — mais longa para eventos com referência oficial.
2. Similaridade lexical do título + primeiros parágrafos (ex.: TF-IDF/cosseno ou Jaccard sobre n-gramas) acima de limiar configurável.
3. Sinais fortes que forçam agrupamento: mesma referência legal, mesmo URL oficial citado, mesma prestação + mesmo período.
4. Opcional (IA): para pares no intervalo de incerteza, `same_event` (sim/não/incerto + justificação). "Incerto" nunca funde automaticamente: cria novo evento e assinala possível duplicado no relatório.
5. Sem correspondência → novo `event` em `CANDIDATE`, documento com papel `trigger`.
6. Com correspondência → o documento junta-se ao evento (`supporting` ou `update`). Se trouxer desenvolvimento **material**, o evento regista `last_material_change_at` e, se estiver em `REJECT`, `WATCHLIST`, `APPROVED` ou `ARCHIVED`, reabre em `CANDIDATE`.
7. Consolida no evento `category`, `subcategory`, `audience`, `impact_type`. A `audience` pode ficar vazia num evento `CANDIDATE` (DEC-019). Um evento novo recebe como `legal_stage` o estágio menos avançado proposto pelos seus documentos; daí em diante o `legal_stage` só é recalculado na etapa VERIFY (DEC-020).

Fusões manuais (`MERGE`) ficam registadas em `editorial_decision`; o evento absorvido passa a `ARCHIVED` com `merged_into`.

## Etapa 5 — VERIFY

**Objectivo:** separar o que é afirmado do que está confirmado, e com que nível.

### 5.1 Extracção de claims
A partir dos documentos do evento, extrair afirmações atómicas, cada uma com `claim_type` e `legal_stage`. A mesma informação em estágios diferentes ("foi anunciado" vs. "está em vigor") dá claims diferentes.

**Claims críticas** (`critical = true`): afirmações sobre legislação, direitos, prestações, valores, limites, elegibilidade, prazos, obrigações, entrada em vigor, alterações legais e regras administrativas relevantes — ou seja, `claim_type ∈ {legal_reference, legal_change, right, benefit, amount, limit, eligibility, deadline, effective_date, obligation, administrative_rule}`, e `procedure` quando condiciona o acesso a um direito ou o cumprimento de uma obrigação.

### 5.2 Procura de evidência
- Documentos T1 já agrupados no evento.
- Documentos T1 recolhidos com sinais fortes (referência legal, nome da prestação, entidade).
- Links para documentos oficiais citados em documentos T2/T3, recolhidos apenas se pertencerem a um domínio de fonte T1 `VALIDATED`.
- Na V1 **não** há pesquisa web aberta: a evidência vem de fontes registadas ou é acrescentada manualmente (`ADD_EVIDENCE`), sujeita às mesmas validações.

### 5.3 Associação claim ↔ evidência
Para cada claim, identificar excertos literais (`quote`) que a suportam ou contradizem. A IA pode propor; a associação só conta se o `quote` existir literalmente no `source_document.text` (`validated = true`).

### 5.4 Estado de verificação da claim (determinista, por esta ordem)

1. **`CONTRADICTED`** — existe evidência T1 validada `contradicts`, adequada ao estágio. (Conflitos entre documentos oficiais de datas diferentes — ex.: diploma entretanto alterado — são resolvidos por revisão humana; até lá, mantém-se `CONTRADICTED`.)
2. **`VERIFIED_OFFICIAL`** — existe evidência T1 validada `supports`, de um documento **adequado ao estágio da claim** (tabela em [SOURCES.md](SOURCES.md#5-evidência-oficial-adequada)). Para alterações legislativas, privilegia-se a versão consolidada oficial quando aplicável.
3. **`VERIFIED_EDITORIAL`** — sem contradição e sem inconsistência entre fontes, e pelo menos uma:
   - evidência validada `supports` de ≥1 fonte T2;
   - evidência validada `supports` de ≥2 fontes T3 independentes;
   - evidência T1 validada que suporta a claim mas não é adequada ao seu estágio (ex.: comunicado de aprovação para uma claim "em vigor");
   - decisão humana `OVERRIDE_VERIFICATION` que fixa `VERIFIED_EDITORIAL`, com nota obrigatória.
4. **`UNVERIFIED`** — todos os outros casos, incluindo: uma única fonte T3; fontes T2/T3 inconsistentes entre si; apenas T4.

Regras fixas:
- Fontes T4 nunca contam como evidência.
- Fontes T2 e T3 nunca produzem `VERIFIED_OFFICIAL`, nem com decisão humana.
- `OVERRIDE_VERIFICATION` só pode baixar o estado ou fixar `VERIFIED_EDITORIAL`. `VERIFIED_OFFICIAL` exige sempre evidência T1 validada e adequada.

### 5.5 Estado de verificação do evento
Calculado a partir das claims críticas (ou de todas, se não houver críticas; sem claims → `UNVERIFIED`):

| Condição | `event.verification_status` |
|----------|-----------------------------|
| Alguma claim crítica `CONTRADICTED` | `CONTRADICTED` |
| Alguma claim crítica `UNVERIFIED` | `UNVERIFIED` |
| Todas as claims críticas `VERIFIED_OFFICIAL` | `VERIFIED_OFFICIAL` |
| Restantes casos (todas verificadas, pelo menos uma só `VERIFIED_EDITORIAL`) | `VERIFIED_EDITORIAL` |

O `legal_stage` do evento é recalculado (DEC-020, ordem em [DATA_MODEL.md](DATA_MODEL.md#33-legal_stage--em-que-fase-está-a-medida)): o estágio mais avançado entre as claims críticas `VERIFIED_OFFICIAL` (ou entre todas, se não houver críticas); sem nenhuma, o estágio menos avançado entre as claims (sem claims, entre os documentos). Só é estágio oficialmente confirmado quando o evento fica `VERIFIED_OFFICIAL`; caso contrário é um estágio de trabalho, nunca apresentado como facto jurídico.

### 5.6 Notas de verificação
Lista legível do que falta confirmar (ex.: "Valor anunciado pelo Governo; diploma ainda não publicado em Diário da República").

## Etapa 6 — SCORE

Calcula o `editorial_score` de cada evento `CANDIDATE`/`WATCHLIST` e propõe o estado editorial. Detalhe em [SCORING.md](SCORING.md).

**O score ordena; não verifica.** O estado editorial resulta de duas condições independentes:

| Gate | Condição para `EDITORIAL_REVIEW` |
|------|----------------------------------|
| Verificação | `verification_status = VERIFIED_OFFICIAL`; ou `VERIFIED_EDITORIAL` **sem claims críticas**. |
| Prioridade | `editorial_score ≥ SELECT_THRESHOLD` e dentro do máximo por execução. |
| Política | Nenhum critério de rejeição de [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#8-critérios-para-rejeitar-reject). |

- `CONTRADICTED` → `REJECT`.
- Sem audiência identificável → `REJECT` (`no_audience`); um evento sem audiência nunca é proposto para `WATCHLIST` nem `EDITORIAL_REVIEW` (DEC-019).
- Score elevado mas verificação insuficiente → `WATCHLIST` (`awaiting_verification` ou `awaiting_official_confirmation`). Um score alto **nunca** desbloqueia a verificação.
- Um evento `VERIFIED_EDITORIAL` com claims críticas só chega a `EDITORIAL_REVIEW` por decisão humana (`PROMOTE_TO_EDITORIAL_REVIEW`, nota obrigatória) e com as restrições de redacção da [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#5-níveis-de-verificação).
- `UNVERIFIED` e `CONTRADICTED` nunca chegam a `EDITORIAL_REVIEW`, nem por decisão humana.

## Etapa 7 — GENERATE

**Objectivo:** produzir formatos a partir de um evento em `EDITORIAL_REVIEW`. Todos os formatos derivam do mesmo evento.

- Entrada: `VerifiedEventBundle` (evento + claims + evidências + fontes + estado de verificação).
- Um gerador por formato. Formatos V1: `whatsapp`, `article`, `seo_meta`. Futuros: `newsletter`, `social_post`.
- Uso de claims no texto:

| Estado da claim | Pode ser usada? | Como |
|-----------------|-----------------|------|
| `VERIFIED_OFFICIAL` | Sim | Como facto, **no seu estágio** (um anúncio confirmado oficialmente continua a ser um anúncio). |
| `VERIFIED_EDITORIAL` | Sim, com restrições | Com atribuição à fonte e indicação explícita de que não há confirmação oficial. Nunca como alteração legal confirmada. |
| `UNVERIFIED` | Não | — |
| `CONTRADICTED` | Não | — |

- Cada conteúdo guarda `claim_refs` e `source_refs`; o artigo inclui secção de fontes e, quando aplicável, "O que ainda não se sabe".
- Regras de escrita, estrutura por formato e orientações de extensão: [STYLE_GUIDE.md](STYLE_GUIDE.md). **Não existe limite rígido de caracteres para WhatsApp.**

## Etapa 8 — CHECK (validações automáticas)

Validações pós-geração (ver [AI_RULES.md](AI_RULES.md#6-validações-automáticas-pós-geração)). Se todas as validações bloqueantes passam, o conteúdo passa a `HUMAN_REVIEW_REQUIRED` e o evento a `READY_FOR_APPROVAL`; caso contrário fica `DRAFT` com o problema em `checks`. Passar nas validações **não** é aprovação.

## Etapa 9 — REVIEW (revisão humana)

**Na V1, a IA não substitui a aprovação humana.**

- `tde review list` mostra conteúdos em `HUMAN_REVIEW_REQUIRED` com estado de verificação de cada claim, `legal_stage`, fontes e resultado das validações.
- Decisões: `APPROVED`, `REJECTED`, `NEEDS_REVISION`. Cada uma regista em `editorial_decision`: quem (`actor`), quando (`decided_at`), decisão e nota opcional.
- `APPROVED` → o evento passa a `APPROVED`. `NEEDS_REVISION` → nova versão em `DRAFT`; o evento volta a `EDITORIAL_REVIEW`. Todos os conteúdos `REJECTED` → o evento volta a `EDITORIAL_REVIEW`, a menos que a pessoa decida `REJECT` ou `MOVE_TO_WATCHLIST`.
- Edições humanas ao texto criam nova versão (`generated_by = human`), que volta às validações automáticas e à revisão.
- O sistema recusa decisões de revisão sem `actor` ou com `actor` do tipo `llm:*`.

## Etapa 10 — EXPORT

Exporta conteúdos `APPROVED` ainda não exportados para `data/exports/<data>/<event_id>/<formato>.md` + `.json` (metadados, claims com estado de verificação, fontes, decisão de revisão). Preenche `exported_at`.

**Exportar não é publicar.** A publicação nos canais é feita fora do sistema na V1; o estado `PUBLISHED` não é atribuído pelo sistema.

## REPORT — relatório da execução

Gerado no fim de `tde run` (Markdown em `data/reports/` + resumo na consola). Contém:

1. Resumo: endpoints recolhidos/falhados, itens novos, documentos relevantes, eventos novos/actualizados (com actualizações materiais assinaladas).
2. **Eventos em `EDITORIAL_REVIEW`** — título, score, estado de verificação, `legal_stage`, fontes principais.
3. **Watchlist** — motivo e o que falta (ex.: "aguarda publicação oficial").
4. **Rejeitados** — top N com motivo principal (para afinação).
5. Possíveis duplicados por confirmar.
6. Custos de IA (tokens por tarefa).
7. **Conclusão explícita** — uma de:
   - "N acontecimentos seleccionados para revisão editorial."
   - "**Nada suficientemente importante para publicar nesta execução.**"

"Nada a publicar" é um resultado de sucesso (código de saída `0`), não um erro.
