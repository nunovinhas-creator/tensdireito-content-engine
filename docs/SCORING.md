# Pontuação Editorial

> Estado: **especificação**. Pesos e limiares são valores iniciais a calibrar com dados reais na Fase 2. Todos os valores vivem em `config/scoring.yaml`.

## 1. Objectivo

Ordenar acontecimentos (`event`) por valor editorial para o leitor do TensDireito.com e decidir, para cada um: `selected`, `watchlist` ou `rejected`. A pontuação tem de ser **explicável**: cada decisão mostra os componentes que a determinaram.

A pontuação **não** substitui a verificação. A verificação é um *gate*; a pontuação ordena o que passa o gate.

## 2. Dimensões

Cada dimensão é avaliada numa escala 0–5. A coluna "Origem" indica se o valor vem de regras deterministas, de IA (opcional, com fallback por regras) ou de ambos.

| Dimensão | Código | Peso inicial | Pergunta | Origem |
|----------|--------|--------------|----------|--------|
| Impacto nos direitos | `impact` | 25 | Altera direitos, valores, condições ou obrigações dos cidadãos? | `change_type` + IA |
| Abrangência | `reach` | 15 | Quantas pessoas são potencialmente abrangidas? (nicho → generalizada) | IA + temas |
| Urgência / prazo | `urgency` | 15 | Existe prazo próximo ou data de entrada em vigor iminente? | `deadline`/`effective_date` verificados |
| Accionabilidade | `actionability` | 15 | O leitor pode/deve fazer algo (pedir, entregar, actualizar)? | IA + `change_type` |
| Confiança | `confidence` | 20 | Qual o nível de verificação? | `verification_status` (regras) |
| Novidade | `novelty` | 5 | É novo face ao que já foi publicado/seleccionado? | regras (histórico de eventos) |
| Interesse público | `interest` | 5 | Quantas fontes independentes / sinais de tendência? | nº de fontes independentes, sinais T4 |

**Total = Σ (valor/5 × peso) − penalizações**, limitado a 0–100.

### 2.1 Grelhas de referência

**`impact`**
| Valor | Critério |
|-------|----------|
| 5 | Nova prestação/direito, ou alteração de valor/condições de prestação existente, em vigor ou com data. |
| 4 | Novo prazo ou alteração de procedimento obrigatório. |
| 3 | Calendário de pagamentos; anúncio formal com diploma em preparação. |
| 2 | Anúncio político sem diploma; proposta em discussão parlamentar. |
| 1 | Informação contextual/estatística. |
| 0 | Sem relação com direitos dos cidadãos. |

**`urgency`**
| Valor | Critério |
|-------|----------|
| 5 | Prazo ou entrada em vigor em ≤ 7 dias. |
| 4 | ≤ 30 dias. |
| 3 | ≤ 90 dias. |
| 1 | Sem data ou > 90 dias. |
| 0 | Prazo já terminado. |

Só datas de claims `confirmed_official` ou `supported` contam; datas não verificadas → valor 1.

**`confidence`**
| `verification_status` | Valor |
|-----------------------|-------|
| `verified` | 5 |
| `not_applicable` (evento informativo com fonte T1/T2) | 4 |
| `partially_verified` | 3 |
| `unverified` | 1 |
| `contradicted` | 0 (e bloqueio) |

**`reach`** — 5: generalidade dos contribuintes/pensionistas/trabalhadores; 3: grupo amplo (ex.: famílias com filhos, desempregados); 1: grupo muito restrito.

## 3. Penalizações

| Código | Pontos | Condição |
|--------|--------|----------|
| `uncertain_relevance` | −10 | Documento disparador com `relevance_flag = uncertain`. |
| `single_t3_source` | −10 | Evento sustentado apenas por uma fonte T3. |
| `t4_only` | −25 | Evento sustentado apenas por fontes T4. |
| `already_covered` | −30 | Evento semelhante já `done` nos últimos N dias sem alteração material. |
| `stale` | −15 | Documento mais recente com mais de `max_age_days`. |

## 4. Decisão

```
se verification_status == contradicted               → rejected (motivo: contradição oficial)
senão se total >= SELECT_THRESHOLD (inicial 65)
     e verification_status ∈ {verified, partially_verified, not_applicable}
                                                     → selected
senão se total >= WATCH_THRESHOLD (inicial 45)        → watchlist
senão                                                → rejected
```

Restrições adicionais:
- **Máximo por execução** (`max_selected_per_run`, inicial 5): se houver mais candidatos acima do limiar, os restantes ficam em `watchlist` com motivo `capacity`.
- **Watchlist expira** após `watchlist_ttl_days` (inicial 14) sem novos dados → `rejected` (motivo `expired`).
- **Nada a publicar:** se nenhum evento for `selected`, a execução termina com `outcome = nothing_to_publish`. Os limiares **nunca** são baixados automaticamente para garantir resultados.

## 5. Explicabilidade

Cada `score` guarda `components`, `penalties`, `total`, `decision` e a versão da configuração. O relatório mostra, por evento:

```
[72] Alteração ao valor do abono de família (verified)
     impact 5 · reach 3 · urgency 4 · actionability 3 · confidence 5 · novelty 5 · interest 3
     penalizações: —
     decisão: selected
```

## 6. Calibração

- Fase 2: correr o pipeline sobre 2–4 semanas de dados reais e comparar a decisão automática com a decisão editorial humana.
- Ajustes a pesos/limiares por pull request em `scoring.yaml`, com nota da razão.
- Métricas de acompanhamento: precisão dos `selected` (% aprovados na revisão), eventos relevantes perdidos (detectados manualmente), proporção de execuções "nada a publicar".
