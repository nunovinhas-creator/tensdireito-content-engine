# Política Editorial

> Estado: **política V1 (M1)**. Define o que o TensDireito publica, com que nível de confirmação, e o que nunca faz. Aplica-se a pessoas e ao sistema (regras, IA e templates). Regras de escrita em [STYLE_GUIDE.md](STYLE_GUIDE.md).

## 1. Propósito

O TensDireito ajuda cidadãos a perceber e exercer os seus direitos. A credibilidade é o activo principal: é preferível publicar mais tarde, ou não publicar, do que publicar uma alteração de direitos que ainda não existe.

## 2. Regra central

> **Descobrir não é verificar.**
> **Verificar não é aprovar.**
> **Aprovar não é publicar.**

| Passo | O que significa | O que **não** significa |
|-------|-----------------|-------------------------|
| Descobrir | Encontrou-se informação numa fonte (`raw_item`, `source_document`). | Que é verdade, actual ou relevante. |
| Verificar | As claims têm evidência validada; nível `VERIFIED_EDITORIAL` ou `VERIFIED_OFFICIAL`. | Que merece ser publicado, nem que está bem escrito. |
| Aprovar | Uma pessoa identificada aprovou um conteúdo concreto (`APPROVED`). | Que foi publicado. |
| Publicar | O conteúdo foi colocado num canal. | — Na V1 acontece **fora do sistema**; o sistema só exporta. |

Nenhum destes passos é inferido a partir do anterior, e nenhum score, modelo de IA ou automatismo salta um passo.

## 3. Transformações proibidas

O sistema e a equipa **nunca** transformam:

| Informação de origem | Nunca apresentar como | Forma correcta | Mecanismo de controlo |
|----------------------|-----------------------|----------------|-----------------------|
| Proposta | Medida aprovada | "O Governo propôs…", "Está em discussão…" | `legal_stage = proposal` |
| Anúncio político | Lei | "O Governo anunciou que…; a medida ainda não foi publicada em Diário da República." | `legal_stage = announcement` |
| Intenção | Direito adquirido | "Está prevista…", "Poderá vir a…" | `legal_stage ∈ {proposal, announcement}` + validação de linguagem |
| Estimativa | Valor definitivo | "Valor estimado de…", "segundo as contas de [fonte]…" | claim de tipo `amount` só é afirmada como definitiva com `VERIFIED_OFFICIAL` |
| Notícia jornalística | Confirmação jurídica | "Segundo [órgão de comunicação]…; ainda sem confirmação oficial." | Fontes T3 nunca produzem `VERIFIED_OFFICIAL` |
| Previsão | Facto | "Prevê-se que…", com a fonte da previsão | claim `context`; nunca critical confirmada |
| Informação antiga | Novidade actual | Indicar a data original; "Recorde-se que…" | `published_at`, dimensão `novelty`, penalização `stale` |

Expressões como "nova lei", "novo direito", "novo valor", "já pode pedir", "passa a receber", "está em vigor" só são permitidas quando as claims correspondentes estão `VERIFIED_OFFICIAL` **e** o `legal_stage` o justifica (`in_force`, ou `published` com data de entrada em vigor indicada). Lista operacional em [STYLE_GUIDE.md](STYLE_GUIDE.md#5-formulações-por-estágio-e-nível-de-verificação).

## 4. Taxonomia editorial V1

A taxonomia organiza o trabalho editorial. É **extensível**: novas categorias, subcategorias e audiências podem ser acrescentadas por pull request (com registo em [DECISION_LOG.md](DECISION_LOG.md) quando se criam ou removem categorias). As categorias **não têm o mesmo peso editorial**; a forma de o reflectir na pontuação é calibrada mais tarde (ver [SCORING.md](SCORING.md#7-calibração-futura)).

Cada `event` tem:

| Campo | Cardinalidade | Função |
|-------|---------------|--------|
| `category` | exactamente 1 | Área temática principal. |
| `subcategory` | 0..1 | Assunto específico dentro da categoria. |
| `secondary_categories` | 0..N | Para assuntos transversais (ex.: IRS de pensionistas). |
| `audience` | 1..N | Quem é afectado. Um evento sem audiência identificável não é publicável. |
| `impact_type` | exactamente 1 | O que muda para essas pessoas. |
| `legal_stage` | exactamente 1 | Em que fase está a medida (ver [DATA_MODEL.md](DATA_MODEL.md#33-legal_stage--em-que-fase-está-a-medida)). |

Estes campos são, nesta fase, **conceptuais**; não estão implementados.

### 4.1 Categorias (`category`)

As subcategorias indicadas são exemplos iniciais, não uma lista fechada.

| # | Código | Categoria | Exemplos de subcategoria |
|---|--------|-----------|--------------------------|
| 1 | `seguranca_social` | Segurança Social e prestações | contribuições, carreira contributiva, rendimento social de inserção, subsídio de doença, indexantes de referência |
| 2 | `pensoes_reformas` | Pensões e reformas | pensão de velhice, invalidez, sobrevivência, actualização de pensões, idade de reforma |
| 3 | `emprego_desemprego` | Emprego e desemprego | subsídio de desemprego, direitos laborais, contratos de trabalho, formação profissional, medidas de emprego |
| 4 | `salarios_rendimento` | Salários e rendimento | salário mínimo, retribuição, subsídios de férias e de Natal, rendimento disponível |
| 5 | `fiscalidade_particulares` | Fiscalidade para particulares | IRS, deduções, prazos de entrega, IMI, benefícios fiscais |
| 6 | `habitacao_arrendamento` | Habitação e arrendamento | apoio à renda, arrendamento, crédito à habitação, programas públicos de habitação |
| 7 | `apoios_familias` | Apoios às famílias | abono de família, parentalidade, creches, apoios à infância |
| 8 | `educacao_estudantes` | Educação e estudantes | bolsas de estudo, propinas, acção social escolar, acesso ao ensino superior |
| 9 | `saude_apoios` | Saúde e apoios relacionados | SNS, taxas moderadoras, comparticipação de medicamentos, apoios na doença |
| 10 | `energia_agua` | Energia e água | tarifas sociais, preços regulados, apoios à eficiência energética |
| 11 | `consumo` | Consumo e direitos do consumidor | garantias, contratos de serviços, reclamações, comunicações |
| 12 | `deficiencia_inclusao` | Deficiência e inclusão | prestação social para a inclusão, atestado de incapacidade, benefícios associados |
| 13 | `idosos_cuidadores` | Idosos e cuidadores | complemento solidário para idosos, estatuto do cuidador informal, respostas sociais |
| 14 | `justica_direitos` | Justiça e direitos dos cidadãos | apoio judiciário, documentos e registos, direitos face à Administração |

Código técnico de recurso: `fora_de_ambito` — usado apenas na classificação, para documentos sem categoria aplicável; um evento com esta categoria é rejeitado.

### 4.2 Audiências (`audience`)

Lista inicial, extensível:

`populacao_geral`, `trabalhadores_conta_outrem`, `trabalhadores_independentes`, `desempregados`, `pensionistas`, `futuros_pensionistas`, `familias_com_filhos`, `pais_maes_recentes`, `estudantes`, `jovens`, `inquilinos`, `proprietarios_senhorios`, `compradores_habitacao`, `contribuintes_irs`, `pessoas_com_deficiencia`, `idosos`, `cuidadores_informais`, `beneficiarios_prestacoes`, `consumidores`, `empregadores` (apenas quando a medida afecta direitos dos trabalhadores).

### 4.3 `impact_type`

| Código | Significado |
|--------|-------------|
| `new_right` | Cria um direito, prestação ou apoio que não existia. |
| `right_change` | Altera condições, elegibilidade ou âmbito de um direito existente (alargamento ou restrição). |
| `amount_change` | Altera valores, montantes, limites, taxas ou escalões. |
| `new_obligation` | Cria uma obrigação para o cidadão. |
| `obligation_change` | Altera uma obrigação existente. |
| `deadline` | Existe um prazo a decorrer ou uma acção a tomar até uma data. |
| `procedure_change` | Altera a forma de pedir, o canal ou os documentos necessários. |
| `payment_schedule` | Calendário ou data de pagamento. |
| `measure_ending` | Uma medida ou apoio termina, é revogado ou caduca. |
| `informational` | Sem alteração; explicação ou esclarecimento útil. |
| `other` | Não enquadrável; exige nota do editor. |

## 5. Níveis de verificação

Dois níveis de verificação editorial, distintos e nunca intermutáveis:

### `VERIFIED_OFFICIAL`
Existe evidência oficial suficiente, validada literalmente, para sustentar as afirmações críticas **no estágio em que são feitas**.

É **obrigatório** para apresentar como facto afirmações sobre: legislação; direitos; prestações; valores; limites; elegibilidade; prazos; obrigações; entrada em vigor; alterações legais; regras administrativas relevantes.

Para alterações legislativas, privilegia-se a publicação oficial do diploma e, quando aplicável, a versão consolidada oficial. Regras de evidência em [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify).

### `VERIFIED_EDITORIAL`
A informação é sustentada por fontes credíveis e consistentes, e pode ter sido revista editorialmente, mas **não** existe confirmação oficial suficiente para tratar a alteração jurídica como facto confirmado.

- `VERIFIED_EDITORIAL` **nunca** é apresentado como confirmação de uma alteração legal.
- Conteúdo baseado em `VERIFIED_EDITORIAL` tem de atribuir a informação à fonte e dizer explicitamente o que ainda não está oficialmente confirmado.
- Uma notícia baseada apenas em imprensa nunca se transforma automaticamente em "nova lei", "novo direito", "novo valor" ou equivalente.
- Nenhuma decisão humana transforma `VERIFIED_EDITORIAL` em `VERIFIED_OFFICIAL`: só a ligação de evidência oficial o faz.

`UNVERIFIED` e `CONTRADICTED` não são níveis de verificação; bloqueiam a passagem a produção editorial.

## 6. Critérios de relevância

Um acontecimento é relevante para o TensDireito quando cumpre **todos**:

1. Pertence a uma categoria da taxonomia (não `fora_de_ambito`).
2. Afecta direitos, obrigações, rendimentos, prazos ou acesso a serviços de pessoas em Portugal.
3. Tem uma audiência identificável.
4. É novo ou traz um desenvolvimento material face ao que já foi tratado (ver secção 10).

Aumentam a relevância (reflectido no score, ver [SCORING.md](SCORING.md)): impacto directo em direitos ou valores; abrangência; prazo próximo; possibilidade de o leitor agir; estágio legal avançado.

## 7. Critérios de utilidade para o cidadão

Um conteúdo é útil quando o leitor consegue responder, pelo menos, a uma destas perguntas — e o texto responde-lhes com o que está confirmado:

- **O que muda** (ou o que está em causa)?
- **Isto aplica-se a mim?** (quem é abrangido, condições)
- **Quanto / quando?** (valores, prazos, datas, só se verificados)
- **O que tenho de fazer?** (como pedir, onde, até quando)
- **O que ainda não se sabe?**

Um acontecimento relevante mas sem nenhuma destas respostas confirmadas fica em `WATCHLIST`.

## 8. Critérios para rejeitar (`REJECT`)

Rejeita-se quando se verifica pelo menos um:

| Motivo (`status_reason`) | Condição |
|--------------------------|----------|
| `out_of_scope` | Sem relação com a taxonomia ou com direitos dos cidadãos. |
| `no_audience` | Sem audiência identificável em Portugal. |
| `contradicted` | Claim crítica contradita por evidência oficial. |
| `duplicate` | É o mesmo assunto de um evento existente (deve ser fundido — `MERGE`). |
| `stale_no_change` | Informação antiga sem desenvolvimento material. |
| `below_threshold` | Score abaixo do limiar de watchlist. |
| `expired` | Esteve em `WATCHLIST` além do prazo sem novos dados. |
| `unverifiable` | Origem exclusivamente T4 ou sem possibilidade razoável de confirmação, sem desenvolvimento durante o período de watchlist. |
| `editorial_decision` | Decisão humana, com nota. |

Um evento rejeitado mantém-se na base de dados (para deduplicação e aprendizagem) e pode reabrir se surgir desenvolvimento material.

## 9. Critérios para `WATCHLIST`

Coloca-se em watchlist um acontecimento relevante que ainda não deve avançar:

| Motivo (`status_reason`) | Condição |
|--------------------------|----------|
| `awaiting_verification` | Score elevado mas `UNVERIFIED`. |
| `awaiting_official_confirmation` | `VERIFIED_EDITORIAL` com claims críticas sem confirmação oficial (ex.: anúncio noticiado, à espera de diploma). |
| `awaiting_date` | Medida confirmada sem data de entrada em vigor ou prazo conhecido, quando essa data é essencial à utilidade. |
| `below_select_threshold` | Score entre os limiares de watchlist e de selecção. |
| `capacity` | Acima do limiar mas excede o máximo por execução. |
| `editorial_decision` | Decisão humana. |

Eventos em watchlist são reavaliados em cada execução e expiram após um prazo configurável sem novos dados (ver [SCORING.md](SCORING.md)).

Um evento `VERIFIED_EDITORIAL` pode ser promovido por uma pessoa a `EDITORIAL_REVIEW` (decisão `PROMOTE_TO_EDITORIAL_REVIEW`, com nota obrigatória) quando há utilidade pública em informar sobre o anúncio ou a proposta em si. O conteúdo resultante tem de seguir a secção 3 e a secção 5.

## 10. Event: actualizar ou criar

**O `Event` é a unidade editorial.** Todas as decisões (verificação, score, revisão, exportação) operam sobre eventos, e todos os formatos derivam do mesmo evento.

Um novo documento **actualiza um Event existente** quando trata do **mesmo assunto**, em qualquer das situações:

- mesma medida, prestação ou obrigação, num estágio posterior (proposta → aprovação → publicação → entrada em vigor → regulamentação);
- mesma medida com correcção, esclarecimento ou alteração de valor, prazo ou condições;
- mesmo diploma ou referência oficial;
- confirmação oficial (ou contradição) de algo já noticiado;
- nova notícia sobre o mesmo acontecimento sem informação nova (junta-se como `supporting`, sem alteração material).

Cria-se **um novo Event** quando:

- é uma medida distinta, mesmo que na mesma categoria;
- é um ciclo novo e autónomo do mesmo indicador (ex.: o valor de um indexante para um ano diferente) — os eventos ficam ligados em `related_events`;
- o evento anterior foi fundido ou não é possível estabelecer que se trata do mesmo assunto (na dúvida, a decisão de fusão é humana).

Uma actualização é **material** quando altera: uma claim crítica, o `legal_stage`, o `verification_status`, um valor, um prazo, uma data, a elegibilidade ou a audiência. Uma actualização material:

1. regista `last_material_change_at` e liga o documento com papel `update`;
2. reabre o evento se estiver em `REJECT`, `WATCHLIST`, `APPROVED` ou `ARCHIVED` (volta a `CANDIDATE` para ser re-pontuado);
3. torna desactualizados os conteúdos existentes: nova versão, com a anterior marcada como substituída — nunca apagada.

## 11. Estados editoriais

`CANDIDATE` (entrada técnica) → `REJECT` | `WATCHLIST` | `EDITORIAL_REVIEW` → `READY_FOR_APPROVAL` → `APPROVED` → *exportação* → `ARCHIVED`. `PUBLISHED` está reservado para quando existir integração de publicação (fora da V1).

Definições e transições em [DATA_MODEL.md](DATA_MODEL.md#35-eventeditorial_status).

**Na V1 o circuito termina em `APPROVED → EXPORT`.** O sistema não publica em nenhum canal.

## 12. Revisão humana

**Na V1, a IA não substitui a aprovação humana.** Nenhum conteúdo é aprovado, exportado como aprovado ou considerado pronto sem decisão de uma pessoa.

Estados de revisão de cada conteúdo (`content_piece.review_status`):

| Estado | Significado |
|--------|-------------|
| `HUMAN_REVIEW_REQUIRED` | Passou as validações automáticas; aguarda uma pessoa. |
| `APPROVED` | Aprovado. |
| `REJECTED` | Rejeitado. |
| `NEEDS_REVISION` | Precisa de alterações; volta a rascunho numa nova versão. |

Cada decisão de revisão regista: **quem** reviu (`actor`), **quando** (`decided_at`), **decisão** e **nota opcional**. Na V1 não há autenticação: a identificação do revisor é declarativa (ver [SECURITY.md](SECURITY.md#8-acesso)).

Quem revê confirma, no mínimo:

1. Os factos afirmados correspondem às claims e ao seu nível de verificação.
2. O texto respeita a secção 3 (nenhuma transformação proibida).
3. A incerteza relevante está explícita.
4. As fontes estão indicadas.
5. O texto cumpre o [STYLE_GUIDE.md](STYLE_GUIDE.md).

## 13. "Nada suficientemente importante para publicar"

É um resultado **válido e de sucesso**. Cada execução termina com uma conclusão explícita; quando nenhum evento chega a `EDITORIAL_REVIEW`, o relatório diz:

> "Nada suficientemente importante para publicar nesta execução."

Os limiares nunca são baixados para produzir resultados, e não se publica para "manter o ritmo".

## 14. Correcções

- Um erro em conteúdo exportado gera nova versão corrigida; a anterior fica substituída, nunca apagada.
- Quando uma claim publicada é contradita por evidência oficial posterior, o evento reabre e a correcção tem prioridade editorial.
- A rastreabilidade claim → evidência → fonte permite responder a pedidos de correcção.
