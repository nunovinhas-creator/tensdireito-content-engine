# Regras de Utilização de IA

> Estado: **especificação**. Aplica-se a qualquer modelo de linguagem utilizado pelo sistema, independentemente do fornecedor.

## 1. Princípio

A IA **ajuda** na descoberta, classificação, síntese e produção editorial. A IA **não**:
- inventa factos, valores, datas, prazos, nomes de diplomas ou entidades;
- confirma informação — a confirmação resulta de evidência documental validada (ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify));
- substitui a revisão humana antes da publicação.

## 2. Tarefas permitidas

| Tarefa | Etapa | Saída | Pode ser substituída por regras? |
|--------|-------|-------|----------------------------------|
| `classify` | CLASSIFY | JSON: temas, tipo de alteração, relevância, justificação | Sim (palavras-chave) |
| `same_event` | CLUSTER | JSON: sim/não/incerto + justificação | Sim (só similaridade lexical) |
| `extract_claims` | VERIFY | JSON: lista de claims atómicas + tipo + crítica | Parcialmente (padrões para valores/datas); sem IA, extracção manual |
| `match_evidence` | VERIFY | JSON: claim_id, excerto literal, stance | Sim (pesquisa literal de valores/datas) |
| `assess_dimensions` | SCORE | JSON: `reach`, `actionability`, `impact` com justificação | Sim (heurísticas por `change_type`) |
| `summarize_event` | CLUSTER/VERIFY | Resumo interno | Sim (título do disparador) |
| `generate:<formato>` | GENERATE | Texto + `claim_refs` usados | Sim (templates simples) |

Qualquer outra utilização de IA tem de ser documentada aqui antes de ser implementada.

## 3. Regras de entrada (grounding)

- O modelo recebe **apenas** o material necessário: texto dos documentos, claims e evidências do evento. Não se pede ao modelo conhecimento "de memória" sobre legislação ou valores.
- O prompt indica explicitamente: "Usa exclusivamente a informação fornecida. Se a informação não estiver no material, responde que não consta."
- Conteúdo recolhido de fontes externas é tratado como **dados não confiáveis** — delimitado no prompt e nunca interpretado como instruções (mitigação de *prompt injection*, ver [SECURITY.md](SECURITY.md)).

## 4. Regras de saída

- Tarefas analíticas devolvem **JSON validado contra esquema**; resposta inválida → nova tentativa (máx. 1) → fallback para regras ou marcação `needs_human`.
- Temperatura 0 (ou a mais baixa suportada) para classificação, extracção e associação; valor moderado configurável apenas para geração editorial.
- Excertos (`quote`) têm de ser cópias literais; a validação procura o excerto no texto original e rejeita se não existir.
- Toda a geração editorial devolve a lista de `claim_refs` utilizadas.

## 5. Regras editoriais para geração

- Português europeu; linguagem clara e acessível; frases curtas; sem jargão sem explicação.
- Tom informativo, não sensacionalista; não prometer direitos ("vai receber") quando dependem de condições — usar "pode ter direito se...".
- Distinguir sempre **anúncio** de **lei em vigor**.
- Valores monetários com formato português (ex.: `1 234,56 €`); datas por extenso ou `dd/mm/aaaa`.
- Indicar a fonte oficial sempre que existir.
- Quando `verification_status = partially_verified`, incluir frase explícita sobre o que ainda não está confirmado.
- Não incluir aconselhamento jurídico individual; incluir nota padrão a remeter para os serviços competentes quando aplicável (texto a definir editorialmente).

## 6. Validações automáticas pós-geração

Executadas sobre cada `content_piece`; resultado guardado em `content_piece.checks`:

| Validação | Regra | Falha → |
|-----------|-------|---------|
| Números não suportados | Todo o valor numérico (montantes, percentagens) no texto tem de aparecer numa claim referida. | bloqueia aprovação |
| Datas não suportadas | Toda a data no texto tem de aparecer numa claim referida. | bloqueia aprovação |
| Referências legais | Toda a referência a diploma (ex.: "Decreto-Lei n.º ...") tem de constar das claims/evidências. | bloqueia aprovação |
| Claims referidas | Todas as `claim_refs` existem e não estão `contradicted`/`unsupported`. | bloqueia aprovação |
| Fontes | Artigo contém secção de fontes com ≥1 fonte; se existir evidência T1, é citada. | aviso |
| Limites de formato | Comprimentos de `whatsapp`/`seo_meta`. | aviso |
| Linguagem de cautela | Se há claims só `supported`, o texto contém atribuição ("segundo..."). | aviso |

"Bloqueia aprovação" significa que `tde review approve` recusa, salvo override humano explícito com motivo.

## 7. Independência de fornecedor

- Todas as chamadas passam pela interface `LLMProvider` (ver [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#42-llmprovider)).
- `config/llm.yaml` define fornecedor e modelo **por tarefa**, permitindo modelos diferentes (ex.: mais barato para classificação, mais capaz para geração).
- Prompts não usam funcionalidades exclusivas de um fornecedor; saída estruturada via esquema JSON no prompt + validação local (funcionalidades nativas de structured output podem ser usadas pela implementação do provider, de forma transparente).
- Nenhum fornecedor está escolhido nesta fase.

## 8. Prompts

- Um ficheiro por tarefa e versão: `prompts/<tarefa>@v<N>.md` (sistema + template + esquema de saída).
- Prompts são imutáveis depois de usados em produção; alterações criam nova versão.
- `llm_call.prompt_id` regista a versão usada — permite comparar versões e reproduzir resultados.
- Cada prompt novo/alterado deve ser acompanhado de casos de teste (fixtures de input + saída esperada ou propriedades a verificar).

## 9. Custos e limites

- Limite de tokens por execução (`llm.max_tokens_per_run`) e por tarefa; ao atingir, as tarefas restantes usam fallback por regras e o relatório indica-o.
- Cache por `input_hash` + `prompt_id`: a mesma pergunta não é repetida.
- O relatório de cada execução inclui tokens por tarefa e fornecedor.

## 10. Auditoria

- Todas as chamadas são registadas em `llm_call` (prompt, modelo, output, tokens, erro).
- Por defeito guarda-se o hash do input; guardar o input completo é configurável (atenção a volume e a dados pessoais).
- Qualquer registo criado por IA identifica-se como `llm:<prompt_id>` nos campos `*_by`.
