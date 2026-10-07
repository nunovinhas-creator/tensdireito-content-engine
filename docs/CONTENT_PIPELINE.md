# Pipeline de Conteúdo

> Estado: **especificação**. Descreve as etapas, entradas, saídas e regras de passagem. Cada etapa é um comando CLI independente (ver [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#3-interface-de-linha-de-comandos)).

## Visão geral

| # | Etapa | Entrada | Saída | IA | Nível atingido |
|---|-------|---------|-------|----|----------------|
| 1 | COLLECT | fontes activas | `raw_item` | Não | 1. Descoberta |
| 2 | NORMALIZE | `raw_item` novos | `document` | Não | 2. Normalizada |
| 3 | CLASSIFY | `document` normalizados | temas, tipo, relevância | Opcional | 2. Normalizada |
| 4 | CLUSTER | `document` relevantes | `event` (candidate) | Opcional | 3. Candidato |
| 5 | VERIFY | `event` candidatos | `claim`, `evidence`, verification_status | Opcional (assistida) | 4. Verificado |
| 6 | SCORE | `event` | `score`, decisão | Opcional (componentes) | — |
| 7 | GENERATE | `event` seleccionado e verificado | `content_piece` (draft) | Sim (com fallback por template) | 5. Conteúdo |
| 8 | REVIEW | `content_piece` | aprovado/rejeitado | Não | 6. Pronto |
| 9 | EXPORT | `content_piece` aprovado | ficheiros | Não | — |
| — | REPORT | execução | relatório | Não | — |

`tde run` executa 1→6 e o REPORT. As etapas 7–9 são despoletadas manualmente na v1.

---

## Etapa 1 — COLLECT

**Objectivo:** obter informação bruta das fontes. Não interpreta.

- Lê `config/sources.yaml`; ignora fontes com `active: false`.
- Usa o `Collector` correspondente a `source_type`.
- Guarda cada item como `raw_item`; ignora se `(source_id, url, content_hash)` já existe.
- Respeita `rate_limit`, `robots.txt` e `user_agent` (ver [SECURITY.md](SECURITY.md)).
- Para fontes T1 do tipo `html_page`, quando o item aponta para um documento oficial (ex.: página de diploma), guarda também o conteúdo da página de destino — será usado como evidência.
- Pistas manuais (`tde add-manual`) entram aqui com `source_type = manual` e tier definido pelo utilizador (por defeito T4).

**Falhas:** erro numa fonte → registado em `source.last_error` e `run.stats`; restantes continuam.

## Etapa 2 — NORMALIZE

- Extrai texto principal do HTML; remove navegação, publicidade, boilerplate.
- Normaliza `published_at` para UTC; se não for possível, deixa nulo (nunca inventa data).
- Calcula `canonical_url` (remove `utm_*`, fragmentos, etc.).
- Calcula `text_hash`; se já existir documento com o mesmo hash → `duplicate_of` e `status = ignored`.
- Detecta língua; documentos não-`pt` ficam `ignored` (salvo fontes marcadas como multilíngues).
- Descarta itens fora da janela temporal configurada (`max_age_days`, por defeito 14).

## Etapa 3 — CLASSIFY

**Objectivo:** decidir se o documento é relevante para o âmbito editorial e de que tipo.

1. **Regras** (sempre): palavras-chave por tema em `taxonomy.yaml`, temas por defeito da fonte, exclusões (ex.: desporto, crime sem relação com direitos).
2. **IA** (opcional): classificação estruturada com o prompt `classify@vN`, devolvendo `topics`, `change_type`, `relevance_flag` e justificação curta.
3. Em caso de conflito regras vs. IA → `relevance_flag = uncertain` (segue para clustering, com penalização na pontuação).

Saída: documentos `irrelevant` ficam `ignored`; os restantes seguem.

## Etapa 4 — CLUSTER

**Objectivo:** agrupar documentos que relatam o mesmo acontecimento num único `event` (princípio P4).

Algoritmo v1 (simples e explicável):
1. Candidatos a agrupamento: documentos relevantes da janela temporal, com pelo menos um tema em comum.
2. Similaridade lexical do título + primeiros parágrafos (ex.: TF-IDF/cosseno ou Jaccard sobre n-gramas) acima de limiar configurável.
3. Sinais fortes que forçam agrupamento: mesma referência legal (nº de diploma), mesmo URL oficial citado.
4. Opcional (IA): para pares no intervalo de incerteza, perguntar ao modelo "relatam o mesmo acontecimento?" com resposta estruturada sim/não/incerto + justificação.
5. Documento que não agrupa com nenhum evento existente → novo `event` (`candidate`), documento com papel `trigger`.
6. Documentos novos podem juntar-se a eventos de execuções anteriores (ainda não `done`/`discarded`) — o evento é actualizado, não duplicado.

Fusão manual de eventos (`merge`) registada em `editorial_decision`.

## Etapa 5 — VERIFY

**Objectivo:** separar o que é afirmado do que está confirmado (princípios P1, P2, P7).

1. **Extracção de claims.** A partir dos documentos do evento, extrair afirmações atómicas e verificáveis. Marcar `critical = true` para claims sobre direitos, valores, condições, prazos, datas de entrada em vigor ou legislação.
2. **Procura de evidência oficial.**
   - Documentos T1 já agrupados no evento.
   - Documentos T1 recolhidos na janela temporal com sinais fortes (referência legal, nome da prestação, entidade).
   - Links para fontes oficiais citados nos documentos T2/T3 (recolhidos nesta etapa, se a fonte de destino estiver no registo como T1).
   - Na v1 **não** há pesquisa web aberta; a evidência vem de fontes registadas.
3. **Associação claim ↔ evidência.** Para cada claim, identificar excerto literal (`quote`) que a suporta ou contradiz. A IA pode propor; a associação só conta se o `quote` existir literalmente no `document.text` (`validated = true`).
4. **Estado da claim:**
   - `confirmed_official` — ≥1 evidência `supports` validada de fonte T1.
   - `supported` — evidência validada apenas de T2/T3.
   - `contradicted` — evidência T1 validada `contradicts`.
   - `unsupported` — sem evidência validada.
5. **Estado do evento** — calculado deterministicamente (ver [DATA_MODEL.md](DATA_MODEL.md#34-eventverification_status)).
6. **Notas de verificação** — lista legível do que falta confirmar (ex.: "Valor anunciado pelo Governo; ainda sem publicação em Diário da República").

Regras fixas:
- Fontes T4 nunca contam como evidência para claims críticas.
- Um anúncio (`change_type = announcement`) sem diploma não pode ter a claim "a alteração está em vigor" confirmada; o conteúdo terá de o apresentar como anúncio.
- Override humano (`override_verification`) é permitido, exige motivo e fica auditado.

## Etapa 6 — SCORE

Calcula a pontuação de cada evento `candidate`/`watchlist` e decide `selected` / `watchlist` / `rejected`. Detalhe em [SCORING.md](SCORING.md).

Gates obrigatórios antes de `selected`:
- `verification_status ∈ {verified, partially_verified, not_applicable}`;
- nenhuma claim crítica `contradicted`;
- pontuação ≥ limiar de selecção.

Eventos relevantes mas não verificados podem ficar em `watchlist` e ser reavaliados nas execuções seguintes (ex.: à espera de publicação oficial).

## Etapa 7 — GENERATE

**Objectivo:** produzir formatos a partir de um evento seleccionado (princípio P10).

- Entrada: `VerifiedEventBundle` (evento + claims + evidências + fontes).
- Um gerador por formato. Formatos v1: `whatsapp`, `article`, `seo_meta`. Futuros: `newsletter`, `social_post`.
- O texto só pode conter factos presentes nas claims com estado `confirmed_official` ou `supported`; claims `supported` (sem T1) têm de ser apresentadas com linguagem de cautela ("segundo [fonte]...").
- `partially_verified` → o conteúdo tem de indicar explicitamente o que ainda não está confirmado.
- Cada conteúdo guarda `claim_refs` e `source_refs`; o artigo inclui secção de fontes.
- Validações automáticas pós-geração (ver [AI_RULES.md](AI_RULES.md#6-validações-automáticas-pós-geração)); falhas → conteúdo fica `draft` com `checks` a indicar o problema.

Especificação inicial dos formatos:

| Formato | Objectivo | Limites / estrutura |
|---------|-----------|---------------------|
| `whatsapp` | Alerta curto para canal/grupo | ≤ 700 caracteres; o quê, quem é abrangido, prazo/valor, acção a tomar, link para artigo. Sem markdown complexo. |
| `article` | Artigo para TensDireito.com | Título; lead; "O que muda"; "Quem tem direito"; "Prazos e valores"; "Como pedir/o que fazer"; "Fontes"; data de actualização; nota de estado de verificação quando aplicável. |
| `seo_meta` | Metadados SEO do artigo | `title` ≤ 60 car., `meta_description` ≤ 155 car., `slug`, palavras-chave principais, sugestões de FAQ apenas com base nas claims. |

## Etapa 8 — REVIEW

- `tde review list` mostra conteúdos `draft`/`in_review` com estado de verificação, claims, fontes e resultado das validações.
- `approve` → `ready_to_publish`; `reject` exige motivo. Ambos geram `editorial_decision`.
- Edições humanas ao texto incrementam `version` com `generated_by = human`.

## Etapa 9 — EXPORT

Exporta conteúdos `ready_to_publish` para `data/exports/<data>/<event_id>/<formato>.md` + `.json` (com metadados, claims e fontes). A publicação nos canais é feita fora do sistema na v1.

## REPORT — relatório da execução

Gerado no fim de `tde run` (Markdown em `data/reports/` + resumo na consola). Contém:

1. Resumo: fontes recolhidas/falhadas, itens novos, documentos relevantes, eventos novos/actualizados.
2. **Eventos seleccionados** — título, pontuação, estado de verificação, fontes principais.
3. **Watchlist** — eventos relevantes à espera de confirmação, com o que falta.
4. **Rejeitados** — top N com motivo principal (para afinação).
5. Custos de IA (tokens por tarefa).
6. **Conclusão explícita** — uma de:
   - "N acontecimentos seleccionados para produção editorial."
   - "**Nada a publicar nesta execução.** Nenhum acontecimento atingiu o limiar de relevância e verificação." (princípio P5)

"Nada a publicar" é um resultado de sucesso (código de saída `0`), não um erro.
