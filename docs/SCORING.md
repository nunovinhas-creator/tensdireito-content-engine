# Pontuação Editorial

> Estado: **especificação em evolução**. O pipeline diário implementa um scorer lexical inicial, determinístico e conservador para priorização de rascunhos WhatsApp; não é verificação factual nem substitui o modelo editorial aqui especificado.

## 1. Objectivo

Ordenar e priorizar acontecimentos (`event`) por valor editorial para o leitor do TensDireito, e propor para cada um: `REJECT`, `WATCHLIST` ou `EDITORIAL_REVIEW`. A pontuação tem de ser **explicável**: cada proposta mostra os componentes que a determinaram.

## 2. Score e verificação são dimensões separadas

| | `EDITORIAL_SCORE` | `VERIFICATION_STATUS` |
|---|-------------------|-----------------------|
| Pergunta | Quão importante e útil seria isto para o leitor, se se confirmar? | Está confirmado? Com que nível? |
| Natureza | Prioridade (0–100), comparativa | Estado (`UNVERIFIED`, `VERIFIED_EDITORIAL`, `VERIFIED_OFFICIAL`, `CONTRADICTED`) |
| Calculado em | SCORE | VERIFY |
| Serve para | Ordenar, priorizar, decidir entre `REJECT`/`WATCHLIST`/selecção | Bloquear ou permitir a passagem a produção editorial; limitar o que pode ser afirmado |

Regras:
- O score **não** inclui nenhuma componente de verificação ou de confiança na fonte. (A dimensão `confidence` e as penalizações `single_t3_source` e `t4_only` da especificação inicial foram removidas — DEC-011.)
- O score **nunca** transforma uma notícia não verificada numa notícia publicável. A verificação é um *gate* independente.
- Uma notícia muito relevante mas sem confirmação suficiente pode ter score elevado **e** continuar bloqueada pela verificação (fica em `WATCHLIST`).
- O score avalia a informação **tal como reportada** (incluindo o estágio legal e as datas reportadas); a verificação decide o que pode ser afirmado.

Exemplo:

```
[84] Aumento anunciado de uma prestação (reportado por imprensa)
     impact 5 · reach 4 · urgency 3 · actionability 3 · novelty 5 · interest 4
     verificação: UNVERIFIED (uma única fonte T3)
     proposta: WATCHLIST — awaiting_verification
```

## 3. Dimensões

Cada dimensão é avaliada numa escala 0–5. A coluna "Origem" indica se o valor vem de regras deterministas, de IA (opcional, com fallback por regras) ou de ambos.

| Dimensão | Código | Peso inicial | Pergunta | Origem |
|----------|--------|--------------|----------|--------|
| Impacto nos direitos | `impact` | 30 | Altera direitos, valores, condições ou obrigações? Em que estágio? | `impact_type` + `legal_stage` reportado + IA |
| Abrangência | `reach` | 20 | Quantas pessoas são potencialmente abrangidas? | `audience` + IA |
| Accionabilidade | `actionability` | 20 | O leitor pode/deve fazer algo (pedir, entregar, actualizar)? | IA + `impact_type` |
| Urgência / prazo | `urgency` | 15 | Existe prazo próximo ou entrada em vigor iminente? | datas reportadas |
| Novidade | `novelty` | 10 | É novo face ao que já foi tratado? | regras (histórico de eventos) |
| Interesse público | `interest` | 5 | Quantas fontes independentes falam disto / sinais de tendência? | nº de fontes independentes, sinais T4 |

**`editorial_score` = Σ (valor/5 × peso) − penalizações**, limitado a 0–100.

`interest` mede atenção pública, não confiança: muitas notícias sobre o mesmo assunto aumentam a prioridade, mas não a verificação.

### 3.1 Grelhas de referência

**`impact`**
| Valor | Critério |
|-------|----------|
| 5 | `new_right`, `right_change`, `amount_change`, `new_obligation`, `measure_ending` com `legal_stage ∈ {published, in_force}`. |
| 4 | `deadline`, `procedure_change` ou `obligation_change` com efeito actual; `new_right`/`amount_change` com `legal_stage = approved`. |
| 3 | `payment_schedule`; medidas `approved` de menor alcance. |
| 2 | `legal_stage ∈ {announcement, proposal}`. |
| 1 | `informational`. |
| 0 | Sem relação com direitos dos cidadãos. |

**`urgency`**
| Valor | Critério |
|-------|----------|
| 5 | Prazo ou entrada em vigor em ≤ 7 dias. |
| 4 | ≤ 30 dias. |
| 3 | ≤ 90 dias. |
| 1 | Sem data ou > 90 dias. |
| 0 | Prazo já terminado. |

**`reach`** — 5: generalidade dos contribuintes/pensionistas/trabalhadores; 3: grupo amplo (ex.: famílias com filhos, desempregados); 1: grupo muito restrito.

## 4. Penalizações

| Código | Pontos | Condição |
|--------|--------|----------|
| `uncertain_relevance` | −10 | Documento disparador com `relevance_flag = uncertain`. |
| `already_covered` | −30 | Assunto semelhante tratado nos últimos N dias sem alteração material (salvaguarda para falhas de agrupamento). |
| `stale` | −15 | Documento mais recente com mais de `max_age_days`. |

Nenhuma penalização depende do tier das fontes: a qualidade das fontes é tratada pela verificação.

## 5. Proposta de estado

```
se critério de rejeição da política editorial               → REJECT  (motivo do critério)
senão se verification_status == CONTRADICTED                → REJECT  (contradicted)
senão se editorial_score < WATCH_THRESHOLD (inicial 45)     → REJECT  (below_threshold)
senão se editorial_score >= SELECT_THRESHOLD (inicial 65):
     se gate de verificação passa                           → EDITORIAL_REVIEW
     senão se verification_status == VERIFIED_EDITORIAL     → WATCHLIST (awaiting_official_confirmation)
     senão                                                  → WATCHLIST (awaiting_verification)
senão                                                       → WATCHLIST (below_select_threshold)
```

Gate de verificação (ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-6--score)): `VERIFIED_OFFICIAL`, ou `VERIFIED_EDITORIAL` sem claims críticas.

Restrições adicionais:
- **Máximo por execução** (`max_editorial_review_per_run`, inicial 5): excedentes ficam em `WATCHLIST` com motivo `capacity`.
- **Watchlist expira** após `watchlist_ttl_days` (inicial 14) sem novos dados → `REJECT` (`expired`).
- **Nada a publicar:** se nenhum evento chegar a `EDITORIAL_REVIEW`, a execução termina com `outcome = nothing_to_publish` e o relatório conclui "Nada suficientemente importante para publicar nesta execução." Os limiares **nunca** são baixados automaticamente para garantir resultados.
- A proposta do SCORE nunca leva um evento além de `EDITORIAL_REVIEW`; `APPROVED` é sempre humano.

## 6. Explicabilidade

Cada `score` guarda `components`, `penalties`, `editorial_score`, `proposed_status`, `reasons`, o estado de verificação no momento e a versão da configuração. O relatório mostra, por evento:

```
[72] Alteração ao valor do abono de família
     impact 5 · reach 3 · urgency 4 · actionability 3 · novelty 5 · interest 3
     penalizações: —
     verificação: VERIFIED_OFFICIAL (legal_stage: published)
     proposta: EDITORIAL_REVIEW
```

## 7. Calibração futura

Não implementado nesta fase. Os pesos e limiares poderão no futuro ser calibrados por:

- **categoria** (as categorias não têm o mesmo peso editorial);
- **audiência**;
- **histórico de desempenho** (ex.: taxa de aprovação na revisão humana, interesse dos leitores);
- **tipo de notícia** (`impact_type`, `legal_stage`).

Processo:
- Correr o pipeline sobre 2–4 semanas de dados reais e comparar a proposta automática com a decisão editorial humana.
- Ajustes por pull request em `scoring.yaml`, com nota da razão; mudanças estruturais (novas dimensões, pesos por categoria) registadas no [DECISION_LOG.md](DECISION_LOG.md).
- Métricas: precisão das propostas `EDITORIAL_REVIEW` (% aprovados na revisão), eventos relevantes perdidos, proporção de execuções "nada a publicar".
- A calibração nunca pode introduzir verificação no score nem relaxar o gate de verificação.

### Implementação lexical inicial do pipeline diário

O scorer actual procura termos normalizados sem distinguir maiúsculas nem diacríticos em impacto, alcance, accionabilidade e urgência. Cada dimensão recebe 0 quando não há correspondência e, caso contrário, `min(5, correspondências distintas + 2)`. Novelty e interest usam provisoriamente o mapa `config/apoios.yaml` (DEC-056): `interest` conta palavras-chave, nomes de apoios e pesquisas no título e texto; `novelty` conta nomes de apoios e pesquisas no título. Ambos casam palavras inteiras (com plural opcional). Quando houver histórico de eventos e agrupamento, voltam à definição da secção 3. Ao score soma-se um bónus pelo nível da fonte (T1 +10, T2 +5; máximo 100; DEC-059). Notícias com títulos semelhantes (similaridade lexical) dão um único rascunho, o de maior score, e não abrem nova issue se outra do mesmo tema foi criada nos últimos 3 dias. Aplicam-se os pesos da tabela da secção 3. **Desde DEC-063, o score não exclui**: só ordena os candidatos de prioridade `alta` e decide qual fica como representante de cada tema. A selecção usa a prioridade de `priority.py` (alta/rever/baixa, com motivo).

Este score é apenas uma ordenação lexical, não determina a veracidade, estado legal, adequação jurídica ou aprovação editorial. Para entrar na fila de rascunhos, o item tem de ter prioridade `alta` e ser representante não duplicado, provir de fonte `VALIDATED` e ter URL HTTPS. O rascunho persiste com `verification_status = unverified`; `tde drafts approve` exige que a pessoa revisora declare explicitamente `verified_editorial` ou `verified_official`. Estas regras não atribuem automaticamente verificação nem publicam o conteúdo. O scorer e os pesos são implementação inicial, não a calibração final prevista nesta especificação.

## Prioridade alta/rever/baixa (DEC-063, fase 1)

O limiar de 65 deixou de ser critério de exclusão. Cada notícia do dia recebe uma prioridade e um motivo, por esta ordem de regras:

1. título com termo forte (nome completo de um apoio ou pesquisa de `config/apoios.yaml`, termos da secção `prioridade.alta` ou predefinições de `priority.py`) → `alta`; se o título também nomear outro país (lista em `priority.py`, extensível em `prioridade.outros_paises`), → `rever`;
2. fonte oficial (T1/T2) → `rever` (as fontes oficiais nunca ficam em `baixa`);
3. título com termo ambíguo (palavras-chave e apelidos entre parênteses de `apoios.yaml`, secção `prioridade.rever`, predefinições) → `rever`;
4. resumo com termo forte → `rever`;
5. nada disto → `baixa`.

A correspondência é por palavra inteira, sem diacríticos, com os plurais portugueses de cada palavra. Só `alta` gera rascunho nesta fase (máximo 20 por run). Nenhuma prioridade apaga candidatos: o relatório diário lista todas as notícias com prioridade e decisão, e o resumo do run mostra o funil, a lista `rever` e uma amostra de `baixa` para auditoria. Os casos de aceitação estão em `tests/test_priority.py`.
