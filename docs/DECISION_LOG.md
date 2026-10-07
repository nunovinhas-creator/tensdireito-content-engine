# Decision Log

> Registo das decisões arquitecturais e editoriais do TensDireito Content Engine. As decisões do M1 ficam efectivas com o merge do PR do M1.

## 1. Formato

Cada decisão é registada com:

| Campo | Conteúdo |
|-------|----------|
| **ID** | `DEC-NNN`, sequencial, nunca reutilizado. |
| **Decisão** | O que foi decidido, numa formulação verificável. |
| **Razão** | Porque foi decidido. |
| **Alternativas consideradas** | Opções avaliadas e porque não foram escolhidas. |
| **Estado** | `Proposta` · `Aceite` · `Substituída por DEC-NNN` · `Revogada`. |
| **Data** | AAAA-MM-DD. |

Regras:
- Decisões são acrescentadas por pull request; nunca se apagam. Uma decisão alterada é marcada `Substituída` e a nova referencia a anterior.
- Os documentos de especificação reflectem o estado das decisões `Aceite`; em caso de conflito, prevalece a decisão mais recente aqui registada, e o documento tem de ser corrigido.
- Decisões ainda por tomar estão em [ROADMAP.md](ROADMAP.md#decisões-pendentes).

Modelo:

```markdown
### DEC-NNN — Título curto
- **Decisão:** …
- **Razão:** …
- **Alternativas consideradas:** …
- **Estado:** Proposta
- **Data:** AAAA-MM-DD
```

## 2. Decisões anteriores (Prompt 1)

Os ADR-001 a ADR-008 da especificação inicial estão resumidos em [ARCHITECTURE.md](ARCHITECTURE.md#6-decisões-arquitecturais-resumo) e mantêm-se aceites, com as alterações e complementos indicados nas decisões abaixo (ADR-004 alterado por DEC-003; ADR-002, ADR-003 e ADR-006 complementados por DEC-013, DEC-010, DEC-012 e DEC-014).

## 3. Decisões do M1

### DEC-001 — Decision log como registo canónico
- **Decisão:** As decisões arquitecturais e editoriais são registadas neste documento, no formato da secção 1.
- **Razão:** Tornar explícito o que está decidido, porquê, e o que foi rejeitado; evitar contradições silenciosas entre documentos.
- **Alternativas consideradas:** ADR apenas dentro de `ARCHITECTURE.md` (mistura decisões editoriais com arquitectura, sem histórico de estado); um ficheiro por ADR (excessivo para a dimensão actual do projecto).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-002 — Regra central: descobrir ≠ verificar ≠ aprovar ≠ publicar
- **Decisão:** "Descobrir não é verificar. Verificar não é aprovar. Aprovar não é publicar." Cada passo tem entidades e estados próprios e nenhum é inferido do anterior.
- **Razão:** O principal risco do produto é apresentar como direito confirmado algo que ainda não o é.
- **Alternativas consideradas:** Um único estado "pronto" que agregasse verificação e aprovação (impede auditoria e esconde o motivo de bloqueio).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-003 — Dois níveis de verificação: `VERIFIED_OFFICIAL` e `VERIFIED_EDITORIAL`
- **Decisão:** Claims e eventos têm `verification_status ∈ {UNVERIFIED, VERIFIED_EDITORIAL, VERIFIED_OFFICIAL, CONTRADICTED}`. `VERIFIED_OFFICIAL` exige evidência T1 validada e adequada ao estágio da claim e é obrigatório para afirmar como facto legislação, direitos, prestações, valores, limites, elegibilidade, prazos, obrigações, entrada em vigor, alterações legais e regras administrativas relevantes. `VERIFIED_EDITORIAL` (fontes credíveis e consistentes, eventualmente revistas editorialmente) nunca é apresentado como confirmação de alteração legal. Para alterações legislativas privilegia-se a versão consolidada oficial quando aplicável. Os estados `verified`, `partially_verified` e `not_applicable` e os estados de claim `supported`/`confirmed_official`/`unsupported` deixam de existir.
- **Razão:** O modelo inicial permitia `verified` com 2×T2 + override humano e seleccionar eventos `partially_verified`, o que tornava possível apresentar como confirmado algo sem confirmação oficial. `not_applicable` era ambíguo.
- **Alternativas consideradas:** Manter os cinco estados iniciais (ambíguos); um único nível "verificado" (não distingue confirmação oficial de editorial); score de confiança contínuo (não dá uma regra inequívoca de bloqueio).
- **Estado:** Aceite (altera ADR-004)
- **Data:** 2026-10-07

### DEC-004 — Ausência de fonte oficial e limites do override humano
- **Decisão:** Sem evidência oficial adequada, o máximo é `VERIFIED_EDITORIAL`. `OVERRIDE_VERIFICATION` só pode baixar o estado ou fixar `VERIFIED_EDITORIAL`, com nota obrigatória; nunca produz `VERIFIED_OFFICIAL`. Fontes T2/T3 nunca produzem `VERIFIED_OFFICIAL`; T4 nunca é evidência. Uma única fonte T3 não chega para `VERIFIED_EDITORIAL`.
- **Razão:** Resolver a decisão pendente D5 sem abrir uma porta para confirmações jurídicas sem fonte oficial.
- **Alternativas consideradas:** 2×T2 + override = verificado (proposta inicial; mistura confiança editorial com confirmação jurídica); proibir totalmente conteúdo sem fonte oficial (impediria informar sobre anúncios relevantes com a devida ressalva).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-005 — `legal_stage` e `impact_type` substituem `change_type`
- **Decisão:** O campo `change_type` é substituído por dois campos ortogonais: `impact_type` (o que muda para o cidadão) e `legal_stage` (`proposal`, `announcement`, `approved`, `published`, `in_force`, `ended`, `not_applicable`). Cada claim é formulada com o seu estágio; o `legal_stage` de um evento só avança com evidência oficial.
- **Razão:** `change_type` misturava a natureza da alteração com o seu estágio (`announcement` vs. `legislation`), o que impedia aplicar de forma determinista as regras "proposta ≠ medida aprovada" e "anúncio ≠ lei".
- **Alternativas consideradas:** Manter `change_type` com mais valores (explosão combinatória); inferir o estágio do texto na geração (não auditável).
- **Estado:** Aceite (clarificada por DEC-020 — cálculo e significado do `legal_stage` do evento)
- **Data:** 2026-10-07

### DEC-006 — Taxonomia editorial V1
- **Decisão:** 14 categorias (Segurança Social e prestações; Pensões e reformas; Emprego e desemprego; Salários e rendimento; Fiscalidade para particulares; Habitação e arrendamento; Apoios às famílias; Educação e estudantes; Saúde e apoios relacionados; Energia e água; Consumo e direitos do consumidor; Deficiência e inclusão; Idosos e cuidadores; Justiça e direitos dos cidadãos). Cada evento tem `category` (1), `subcategory` (0..1), `secondary_categories` (0..N), `audience` (1..N) e `impact_type` (1). A taxonomia é extensível e as categorias não têm o mesmo peso editorial. Campos conceptuais, não implementados.
- **Razão:** Resolver D4 e dar base comum à classificação, ao score e ao estilo.
- **Alternativas consideradas:** Manter a lista inicial de temas (misturava níveis, ex.: `desemprego` e `emprego_formacao`, sem audiência nem impacto); taxonomia hierárquica profunda (prematura sem dados reais).
- **Estado:** Aceite (clarificada por DEC-019 — `audience` 1..N aplica-se ao evento em progressão editorial)
- **Data:** 2026-10-07

### DEC-007 — Modelo de fontes em quatro conceitos; source discovery ≠ source verification
- **Decisão:** Distinguem-se `source_registry` (quem, tier), `source_endpoint` (onde/como), `source_document` (o documento obtido) e `source_evidence` (excerto literal ligado a uma claim). Fontes e endpoints só são usados após validação manual registada; URLs, feeds e APIs nunca são assumidos. Pistas manuais têm tier determinado pelo domínio validado, senão T4. A hierarquia continua a privilegiar fontes oficiais.
- **Razão:** O modelo inicial juntava entidade e ponto de acesso numa tabela e permitia ao utilizador declarar o tier de uma pista manual.
- **Alternativas consideradas:** Uma tabela única `source` (proposta inicial); tier por documento (permite "promover" imprensa a oficial).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-008 — Guia de estilo V1 e ausência de limite rígido no WhatsApp
- **Decisão:** Criado [STYLE_GUIDE.md](STYLE_GUIDE.md) (português de Portugal, claro, directo, acessível, útil, rigoroso, sem burocratês, alarmismo nem clickbait, proporcional à evidência; regras para títulos, subtítulos, leads, WhatsApp, artigos, SEO e CTA). Não existe limite rígido de caracteres para WhatsApp; extensões SEO são orientações que geram aviso, nunca bloqueio.
- **Razão:** Resolver D6; o limite de 700 caracteres da especificação inicial não tinha fundamento e podia levar a cortar incerteza ou condições essenciais.
- **Alternativas consideradas:** Manter limites rígidos por formato.
- **Estado:** Aceite (complementada por DEC-017 — norma ortográfica — e DEC-018 — nota de responsabilidade)
- **Data:** 2026-10-07

### DEC-009 — Política editorial e transformações proibidas
- **Decisão:** Criada [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md). O sistema nunca transforma proposta em medida aprovada, anúncio em lei, intenção em direito adquirido, estimativa em valor definitivo, notícia em confirmação jurídica, previsão em facto, nem informação antiga em novidade. Definidos critérios de relevância, utilidade, rejeição e watchlist.
- **Razão:** Tornar estas regras explícitas, verificáveis por validações automáticas e pela revisão humana.
- **Alternativas consideradas:** Deixar as regras implícitas nos prompts (não auditável, dependente do fornecedor).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-010 — O Event é actualizado, não duplicado
- **Decisão:** Desenvolvimentos posteriores do mesmo assunto actualizam o `Event` existente, em qualquer estado (excepto fundido); actualizações materiais reabrem o evento e geram novas versões de conteúdo. Medidas distintas ou ciclos autónomos do mesmo indicador são eventos novos, ligados por `related_events`.
- **Razão:** O clustering inicial só juntava documentos a eventos ainda não concluídos, o que criava duplicados quando uma medida evoluía (ex.: anúncio → diploma).
- **Alternativas consideradas:** Novo evento por cada estágio (fragmenta o histórico e duplica conteúdo).
- **Estado:** Aceite (complementa ADR-003)
- **Data:** 2026-10-07

### DEC-011 — `EDITORIAL_SCORE` separado de `VERIFICATION_STATUS`
- **Decisão:** O score serve para ordenar e priorizar e não contém componentes de verificação: removida a dimensão `confidence` e as penalizações `single_t3_source` e `t4_only`; pesos redistribuídos (impact 30, reach 20, actionability 20, urgency 15, novelty 10, interest 5). O score nunca torna publicável algo não verificado; um evento com score elevado pode continuar bloqueado pela verificação. Calibração futura por categoria, audiência, histórico e tipo de notícia, ainda não implementada.
- **Razão:** Na especificação inicial a confiança contava 20 pontos, misturando prioridade com confirmação.
- **Alternativas consideradas:** Manter `confidence` com peso reduzido (continua a misturar dimensões).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-012 — Estados editoriais do Event; V1 termina em `APPROVED → EXPORT`
- **Decisão:** `event.editorial_status ∈ {CANDIDATE, REJECT, WATCHLIST, EDITORIAL_REVIEW, READY_FOR_APPROVAL, APPROVED, PUBLISHED, ARCHIVED}`, com `CANDIDATE` como estado técnico de entrada. Na V1 o circuito termina em `APPROVED → EXPORT`; `PUBLISHED` está reservado e nunca é atribuído; não existe publicação automática.
- **Razão:** Os estados iniciais (`candidate/scored/selected/in_production/done`) não distinguiam aprovação de exportação nem tinham espaço para publicação futura.
- **Alternativas consideradas:** Derivar o estado do evento apenas dos estados dos conteúdos (perde-se a watchlist e a decisão editorial ao nível do assunto).
- **Estado:** Aceite (complementa ADR-006)
- **Data:** 2026-10-07

### DEC-013 — SQLite na V1; persistência durável decidida antes de agendamento
- **Decisão:** SQLite mantém-se na V1, com todo o SQL isolado na camada `storage` e sem funcionalidades exclusivas de SQLite, para permitir migração para PostgreSQL. Antes de activar execução agendada via GitHub Actions tem de ser decidida a persistência durável e o estado partilhado (D8); SQLite local num runner efémero não é solução suficiente para produção.
- **Razão:** Simplicidade na V1 sem criar uma falsa sensação de prontidão para automação.
- **Alternativas consideradas:** PostgreSQL desde o início (infraestrutura prematura); SQLite como artefacto do workflow (frágil, sem concorrência nem partilha com a revisão).
- **Estado:** Aceite (complementa ADR-002)
- **Data:** 2026-10-07

### DEC-014 — Revisão humana obrigatória na V1
- **Decisão:** Conteúdos têm `review_status ∈ {DRAFT, HUMAN_REVIEW_REQUIRED, APPROVED, REJECTED, NEEDS_REVISION}`, sendo os quatro últimos os estados de revisão. Cada decisão regista quem reviu, quando, a decisão e uma nota opcional. A IA não substitui a aprovação humana: nenhum `actor` pode ser um modelo. Sem autenticação na V1 (identificação declarativa).
- **Razão:** Concretizar ADR-006 e resolver o formato de D7.
- **Alternativas consideradas:** Aprovação automática acima de um score (contraria DEC-002 e DEC-011); autenticação já na V1 (prematura para operação local por poucas pessoas).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-015 — Tooling: Python, uv, `tensdireito_content_engine`, `tde`
- **Decisão:** Python 3.12+; `uv` para gestão de projecto e dependências (`pyproject.toml`, `uv.lock`); pacote `tensdireito_content_engine`; CLI `tde`.
- **Razão:** Fechar os nomes provisórios (`tensdireito_engine`) e a escolha pip/uv em aberto.
- **Alternativas consideradas:** pip + requirements (sem lockfile nativo); Poetry (mais pesado para o necessário); nome de pacote curto `tensdireito_engine` (não coincide com o nome do repositório).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-016 — Monólito modular
- **Decisão:** O sistema continua a ser um único pacote Python modular, com etapas que comunicam pela base de dados. Sem microserviços, filas ou orquestradores.
- **Razão:** Volume e equipa pequenos; a separação por módulos e o estado persistido dão o desacoplamento necessário.
- **Alternativas consideradas:** Microserviços por etapa (custo operacional sem benefício nesta escala).
- **Estado:** Aceite (reafirma P11 / ADR-001)
- **Data:** 2026-10-07

### DEC-017 — Norma ortográfica do conteúdo publicado: AO1990, variante europeia
- **Decisão:** Todo o conteúdo destinado ao público segue o Acordo Ortográfico de 1990, na variante portuguesa/europeia, em linguagem natural de português de Portugal. **Âmbito:** WhatsApp, artigos, títulos, subtítulos, leads, SEO, CTAs, notas de responsabilidade e todo o conteúdo gerado ou proposto por IA. **Fora do âmbito:** a documentação técnica interna, que pode manter a grafia actual. **Excepções no conteúdo publicado:** citações literais preservam a grafia original; excertos de legislação apresentados como citação reproduzem exactamente o texto oficial; nomes oficiais de diplomas, entidades, documentos ou obras mantêm a designação oficial. Fecha D11.
- **Razão:** O AO1990 é a norma em vigor para a escrita pública em Portugal; separar a documentação interna evita uma conversão sem valor; as excepções protegem a fidelidade às fontes.
- **Alternativas consideradas:** Grafia anterior ao AO1990 no conteúdo público (afasta-se da norma que o público espera); converter também toda a documentação interna (custo sem benefício para o leitor); corrigir a grafia de citações e textos oficiais (comprometeria a fidelidade às fontes).
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-018 — Nota de responsabilidade proporcional ao risco
- **Decisão:** A nota de responsabilidade não é obrigatória em todos os conteúdos nem acrescentada automaticamente. Usa-se quando o conteúdo pode induzir uma decisão jurídica, uma decisão financeira relevante ou uma decisão administrativa importante, ou envolve interpretação normativa particularmente sensível. É curta e clara, não sugere que o TensDireito substitui aconselhamento jurídico profissional, e a decisão de a incluir cabe à pessoa que revê (a IA pode apenas propor). Textos de referência em [STYLE_GUIDE.md](STYLE_GUIDE.md#13-nota-de-responsabilidade).
- **Razão:** Uma nota em todos os conteúdos perde significado e polui textos de baixo risco; o risco jurídico concentra-se em conteúdos que levam a decisões.
- **Alternativas consideradas:** Nota padrão obrigatória em todos os conteúdos (proposta inicial do M1); nenhuma nota (insuficiente para conteúdos de risco); exigência automática por validação (falsos positivos; substitui juízo editorial).
- **Estado:** Aceite
- **Data:** 2026-10-07

## 4. Decisões do M2

### DEC-019 — `audience` obrigatória para progressão editorial, não para o candidato
- **Decisão:** A cardinalidade `audience` 1..N de DEC-006 aplica-se ao evento **elegível para progressão editorial**. Um evento pode ter `audience` vazia apenas em `CANDIDATE` (objecto técnico de entrada, ainda incompleto), `REJECT` e `ARCHIVED`. Em `WATCHLIST`, `EDITORIAL_REVIEW`, `READY_FOR_APPROVAL`, `APPROVED` e `PUBLISHED` exige-se ≥1 audiência. Um `CANDIDATE` sem audiência identificável é rejeitado com `status_reason = no_audience`, que continua a ser um motivo de rejeição válido. Nenhuma decisão humana (`MOVE_TO_WATCHLIST`, `PROMOTE_TO_EDITORIAL_REVIEW`, aprovação) faz avançar um evento sem audiência.
- **Razão:** O evento nasce no CLUSTER a partir de propostas de classificação, que podem não identificar audiência; o motivo `no_audience` (EDITORIAL_POLICY.md §8) pressupõe que esse evento existe para poder ser rejeitado (e mantido para deduplicação). Ter audiência é critério de relevância (§6), e a `WATCHLIST` só recebe acontecimentos relevantes (§9); por isso a exigência começa em `WATCHLIST`. Assim DEC-006, EDITORIAL_POLICY §4 e §8 e DATA_MODEL ficam coerentes sem remover nenhum conceito.
- **Alternativas consideradas:** Exigir ≥1 audiência na criação (torna `no_audience` impossível e obriga a inventar uma audiência no CLUSTER); remover `no_audience` (perde-se o registo do motivo de rejeição e a deduplicação contra eventos rejeitados); permitir audiência vazia em `WATCHLIST` (contraria o critério de relevância).
- **Documentos subordinados:** [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md) §4 e §8, [DATA_MODEL.md](DATA_MODEL.md) §2.2 e §3.5, [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) etapas 4 e 6. Implementado como invariante de `Event` no domínio.
- **Estado:** Aceite (clarifica DEC-006)
- **Data:** 2026-10-07

### DEC-020 — `legal_stage` do evento: regra de cálculo e significado
- **Decisão:** O evento tem um único campo `legal_stage`, com regra de cálculo determinística e significado condicionado à verificação:
  1. **Ordem de avanço** (a da tabela de DATA_MODEL.md §3.3 e de DEC-005): `proposal` < `announcement` < `approved` < `published` < `in_force` < `ended`. `not_applicable` fica fora da ordem e só é usado quando nenhuma claim/documento tem estágio aplicável.
  2. **Na criação (CLUSTER):** o estágio menos avançado entre os `proposed_legal_stage` dos documentos agrupados.
  3. **Em cada VERIFY** (recalculado, não acumulado), sobre as claims críticas (ou todas, se não houver críticas): se existir ≥1 claim `VERIFIED_OFFICIAL`, o estágio mais avançado entre essas claims; caso contrário, o estágio menos avançado entre as claims (ou, sem claims, entre os documentos).
  4. **Significado:** o `legal_stage` do evento só é um estágio **oficialmente confirmado** quando `event.verification_status = VERIFIED_OFFICIAL`. Em qualquer outro estado é um estágio de trabalho (proposto, ou apenas parcialmente confirmado) e nunca é apresentado como facto jurídico; a redacção usa sempre o `legal_stage` e o `verification_status` de cada claim.
- **Razão:** DATA_MODEL.md descrevia o campo como "mais avançado verificado", enquanto CONTENT_PIPELINE.md previa, sem claims oficiais, "o menos avançado proposto" — dois significados para o mesmo campo, e nenhum valor definido na criação do evento. A regra acima é determinista, conservadora (sem evidência oficial, escolhe o estágio menos avançado), e impede que uma inferência editorial, um anúncio ou a imprensa sejam lidos como confirmação jurídica, preservando `VERIFIED_OFFICIAL ≠ VERIFIED_EDITORIAL`.
- **Alternativas consideradas:** Dois campos (`proposed_legal_stage` e `verified_legal_stage`) no evento (mais complexidade sem consumidor; a distinção já é dada pelo `verification_status` e pelas claims); `legal_stage` nulo até haver evidência oficial (contraria a cardinalidade "exactamente 1" e impede a pontuação de candidatos); manter o valor anterior quando não há claims oficiais (não determinista face à ordem de execução).
- **Documentos subordinados:** [DATA_MODEL.md](DATA_MODEL.md) §2.2 e §3.3, [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) etapas 4 e 5.5, [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md) §4. O significado (ponto 4) está exposto no domínio como `Event.legal_stage_officially_confirmed`; o cálculo (pontos 1–3) pertence à futura etapa VERIFY.
- **Estado:** Aceite (clarifica DEC-005)
- **Data:** 2026-10-07

### DEC-021 — Normalização mecânica e identidade de conteúdo
- **Decisão:** A etapa NORMALIZE separa três representações: `RawItem` (captura bruta, preservada intacta) → `NormalizedItem` (intermédio sem persistência) → fingerprint. O `NormalizedItem` contém só o que se obtém por transformação mecânica:
  1. **Texto** (`text`): Unicode NFC; `\r\n`/`\r` → `\n`; espaço horizontal consecutivo (incluindo tabulação e NBSP) → um espaço; sem espaços no início/fim das linhas; três ou mais quebras → uma linha em branco; sem espaço exterior. Não muda maiúsculas/minúsculas, pontuação, acentos nem marcação; não usa NFKC.
  2. **Título** (`title`): NFC e todo o espaço consecutivo (incluindo quebras) → um espaço, sem espaço exterior.
  3. **`published_at`**: só ISO 8601 com fuso explícito é convertido para UTC; data sem hora, data/hora sem fuso ou outro formato → nulo (D13).
  4. **URL**: preservado tal como obtido no `RawItem`; `canonical_url` não é calculado até D12.
  5. **Fingerprint**: SHA-256 (hex) do `text` normalizado em UTF-8 — é o `text_hash` de DATA_MODEL.md (deduplicação exacta). `RawItem.content_hash` é o SHA-256 do conteúdo bruto, sem normalização.
  O fingerprint identifica a representação normalizada, não o acontecimento: não é `event_id` nem decide pertença a um `Event` (CLUSTER). A normalização não atribui categoria, audiência, `impact_type`, `legal_stage`, verificação, tier, `document_kind` nem língua, e não cria `claim`, `source_evidence` nem `event`.
- **Razão:** DATA_MODEL.md define `text_hash` como "hash do texto normalizado", mas não as regras de normalização; regras mecânicas e conservadoras tornam a deduplicação exacta determinista sem alterar o significado. NFC junta formas canonicamente equivalentes de caracteres portugueses ("ã" composto e decomposto). A evidência é validada literalmente contra o texto normalizado (DATA_MODEL.md §2.5), por isso o texto normalizado não pode ser reescrito.
- **Alternativas consideradas:** `casefold`/remoção de acentos no hash (funde textos diferentes, ex.: "pensão"/"pensao"); NFKC (altera "m²", "½"); incluir título ou URL no fingerprint (contraria a definição de `text_hash` e mistura identidade de conteúdo com metadados); normalização agressiva de URL e assunção do fuso local (sem regra documentada — D12, D13).
- **Documentos subordinados:** [DATA_MODEL.md](DATA_MODEL.md) §2.1, [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) etapa 2, [ROADMAP.md](ROADMAP.md) D12 e D13. Implementado em `domain/raw_item.py` e `normalize/`.
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-022 — Deduplicação exacta por `text_hash` e regra técnica do representante
- **Decisão:** A deduplicação exacta (M2.4) agrupa `NormalizedItem` pelo fingerprint de DEC-021 (`text_hash`): dois itens são duplicados exactos se e só se têm o mesmo `text_hash`. Em cada grupo, o **representante é o primeiro item na ordem da sequência de entrada**; cada um dos restantes é registado como duplicado desse representante (`duplicate_of`). A regra é exclusivamente técnica e não tem significado editorial: o representante não é "o melhor", "o mais oficial" nem "o original", e a escolha não transfere tier, verificação nem estado para outros itens. A operação não altera, funde nem descarta itens: todos aparecem no resultado, como representante ou como duplicado. Não há deduplicação aproximada, similaridade nem agrupamento em `Event` (CLUSTER).
- **Razão:** DATA_MODEL.md §2.1 prevê `text_hash` e `duplicate_of` e CONTENT_PIPELINE.md (etapa 2) "duplicados exactos → `duplicate_of`", mas nenhum documento diz qual item é preservado. A primeira ocorrência é determinista para a mesma entrada e não exige informação inexistente; quando houver persistência, corresponde a manter o item já registado e a marcar os seguintes como duplicados.
- **Alternativas consideradas:** Preferir por tier, tipo de documento ou fonte (critério editorial não decidido; tier e `document_kind` ainda não são calculados); preferir por `published_at` ou `fetched_at` (atribui significado à data, `published_at` pode ser nulo por D13 e exige desempate adicional); ordenar por URL ou hash do conteúdo bruto (arbitrário e sem vantagem sobre a ordem de entrada).
- **Documentos subordinados:** [ROADMAP.md](ROADMAP.md) M2.4, [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) etapa 2. Implementado em `normalize/dedup.py`. Não altera DEC-021 nem depende de D12/D13.
- **Estado:** Aceite
- **Data:** 2026-10-07

## 5. Estado das decisões pendentes

A lista de referência está em [ROADMAP.md](ROADMAP.md#decisões-pendentes). Resumo após o M1:

| # | Estado |
|---|--------|
| D1 — Fontes T1 prioritárias e endpoints | **OPEN.** Fecha quando as fontes prioritárias e os respectivos endpoints forem validados manualmente. Nenhum URL, feed, RSS ou API é assumido. |
| D2 — Fontes T2/T3 | OPEN |
| D3 — Fornecedor de IA e orçamento | OPEN |
| D4 — Taxonomia | CLOSED (DEC-006) |
| D5 — Verificação sem fonte oficial | CLOSED (DEC-004) |
| D6 — Guia de estilo | CLOSED (DEC-008, DEC-018) |
| D7 — Quem revê e aprova | Parcial: formato do registo fechado (DEC-014); pessoas e autenticação OPEN |
| D8 — Persistência durável e estado partilhado | OPEN — bloqueante para qualquer execução agendada (DEC-013) |
| D9 — Frequência das execuções agendadas | OPEN |
| D10 — Destino de publicação | OPEN |
| D11 — Norma ortográfica do conteúdo publicado | **CLOSED (DEC-017)** |
| D12 — Regra de `canonical_url` | OPEN (ver DEC-021) |
| D13 — Formatos e fuso de `published_at_raw` | OPEN (ver DEC-021) |
