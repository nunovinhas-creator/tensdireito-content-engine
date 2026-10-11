# Regras de Utilização de IA

> Estado: **especificação (M1)**, com uma primeira tarefa implementada: `generate:whatsapp` (DEC-059), via Google Gemini e Groq, planos gratuitos com chave própria (DEC-062; `config/llm.yaml`). Aplica-se a qualquer modelo de linguagem utilizado pelo sistema, independentemente do fornecedor.

## 1. Princípio

A IA **ajuda** na descoberta, classificação, síntese e produção editorial. A IA **não**:
- inventa factos, valores, datas, prazos, nomes de diplomas, entidades, fontes ou URLs;
- verifica informação — o `verification_status` resulta de regras deterministas sobre evidência validada (ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify));
- decide o `legal_stage` de um evento, que só avança com evidência;
- aprova conteúdo: **na V1, a IA não substitui a aprovação humana**. Nenhuma decisão em `editorial_decision` pode ter como `actor` um modelo (`llm:*`);
- publica — a V1 não publica em nenhum canal.

As saídas da IA são sempre **propostas**, identificadas como `llm:<prompt_id>`.

## 2. Tarefas permitidas

| Tarefa | Etapa | Saída | Pode ser substituída por regras? |
|--------|-------|-------|----------------------------------|
| `classify` | CLASSIFY | JSON: categoria, subcategoria, audiência, `impact_type`, `legal_stage` proposto, relevância, justificação | Sim (palavras-chave) |
| `same_event` | CLUSTER | JSON: sim/não/incerto + justificação | Sim (só similaridade lexical) |
| `extract_claims` | VERIFY | JSON: claims atómicas + tipo + `legal_stage` + crítica | Parcialmente (padrões para valores/datas); sem IA, extracção manual |
| `match_evidence` | VERIFY | JSON: claim_id, excerto literal, stance | Sim (pesquisa literal de valores/datas) |
| `assess_dimensions` | SCORE | JSON: `reach`, `actionability`, `impact` com justificação | Sim (heurísticas por `impact_type`) |
| `summarize_event` | CLUSTER/VERIFY | Resumo interno | Sim (título do disparador) |
| `generate:<formato>` | GENERATE | Texto + `claim_refs` usados | Sim (templates simples) |

Qualquer outra utilização de IA tem de ser documentada aqui antes de ser implementada.

**M2.12:** a definição documental de CLASSIFY V1 é rules-only. A possibilidade de classificação assistida por IA descrita nesta tabela é futura, continua dependente de D3 e não faz parte do comando nem do contrato M2.12.

## 3. Regras de entrada (grounding)

- O modelo recebe **apenas** o material necessário: texto dos documentos, claims (com estado de verificação e `legal_stage`) e evidências do evento. Não se pede ao modelo conhecimento "de memória" sobre legislação ou valores.
- O prompt indica explicitamente: "Usa exclusivamente a informação fornecida. Se a informação não estiver no material, responde que não consta."
- Conteúdo recolhido de fontes externas é tratado como **dados não confiáveis** — delimitado no prompt e nunca interpretado como instruções (ver [SECURITY.md](SECURITY.md)).

## 4. Regras de saída

- Tarefas analíticas devolvem **JSON validado contra esquema**; resposta inválida → nova tentativa (máx. 1) → fallback para regras ou marcação para revisão humana.
- Temperatura 0 (ou a mais baixa suportada) para classificação, extracção e associação; valor moderado configurável apenas para geração editorial.
- Excertos (`quote`) têm de ser cópias literais; a validação procura o excerto no texto original e rejeita se não existir.
- Toda a geração editorial devolve a lista de `claim_refs` utilizadas.

## 5. Regras editoriais para geração

A geração segue a [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md) e o [STYLE_GUIDE.md](STYLE_GUIDE.md). Em particular:

- Só usa claims `VERIFIED_OFFICIAL` (como facto, no seu estágio) e `VERIFIED_EDITORIAL` (com atribuição e indicação de que não há confirmação oficial). Nunca usa claims `UNVERIFIED` ou `CONTRADICTED`.
- Nunca transforma proposta em medida aprovada, anúncio em lei, intenção em direito adquirido, estimativa em valor definitivo, notícia em confirmação jurídica, previsão em facto, ou informação antiga em novidade.
- O verbo segue o `legal_stage` (tabela em [STYLE_GUIDE.md](STYLE_GUIDE.md#5-formulações-por-estágio-e-nível-de-verificação)).
- Explicita a incerteza relevante no próprio texto.
- Não impõe limites artificiais de extensão: os formatos seguem as orientações do guia de estilo (não existe limite rígido para WhatsApp).
- Escreve em português de Portugal segundo o **Acordo Ortográfico de 1990** (variante europeia), preservando a grafia original em citações literais, excertos de legislação e nomes oficiais ([STYLE_GUIDE.md](STYLE_GUIDE.md#11-norma-ortográfica-e-âmbito)).
- Não inclui aconselhamento jurídico individual. Pode **propor** a nota de responsabilidade quando se aplicam os critérios de risco do guia de estilo; a decisão de a incluir é humana e não é automática.

## 6. Validações automáticas pós-geração

Executadas sobre cada `content_piece`; resultado guardado em `content_piece.checks`. Só um conteúdo sem falhas bloqueantes passa a `HUMAN_REVIEW_REQUIRED`. Passar nas validações **não** é aprovação.

| Validação | Regra | Falha → |
|-----------|-------|---------|
| Claims referidas | Todas as `claim_refs` existem e nenhuma está `UNVERIFIED` ou `CONTRADICTED`. | bloqueia (sem override) |
| Números não suportados | Todo o valor numérico (montantes, percentagens) no texto aparece numa claim referida. | bloqueia |
| Datas não suportadas | Toda a data no texto aparece numa claim referida. | bloqueia |
| Referências legais | Toda a referência a diploma consta das claims/evidências. | bloqueia |
| Estágio legal | Expressões de facto em vigor ("está em vigor", "nova lei", "já pode pedir", "passa a receber", …) só aparecem se as claims correspondentes forem `VERIFIED_OFFICIAL` com `legal_stage` compatível. | bloqueia |
| Atribuição | Cada claim `VERIFIED_EDITORIAL` usada tem atribuição à fonte e indicação de ausência de confirmação oficial. | bloqueia |
| Fontes | O artigo contém secção de fontes com ≥1 fonte; se existir evidência T1, é citada. | aviso |
| Orientações de formato | Extensões indicativas do [STYLE_GUIDE.md](STYLE_GUIDE.md) (ex.: título SEO, meta description). | aviso (nunca bloqueia) |

As validações heurísticas bloqueantes (números, datas, referências legais, estágio legal, atribuição) podem ser ultrapassadas apenas por decisão humana registada, com nota, em caso de falso positivo. A validação "Claims referidas" não admite override.

## 7. Independência de fornecedor

- Todas as chamadas passam pela interface `LLMProvider` (ver [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#42-llmprovider)).
- `config/llm.yaml` define fornecedor e modelo **por tarefa**.
- Prompts não usam funcionalidades exclusivas de um fornecedor; saída estruturada via esquema JSON + validação local.
- D3 fechada parcialmente (DEC-062): Google Gemini (`gemini-3.5-flash-lite`, `GEMINI_API_KEY`) e, em alternativa, Groq (`openai/gpt-oss-120b`, `GROQ_API_KEY`), ambos em plano gratuito, para `generate:whatsapp`; a Anthropic (paga) fica disponível por configuração. Os textos enviados são excertos de notícias públicas; o plano gratuito do Gemini pode usá-los para melhorar os modelos. As restantes tarefas continuam sem fornecedor.

## 8. Implementação de `generate:whatsapp` (DEC-059)

Enquanto não existem claims e evidências (CLUSTER/VERIFY), a geração de rascunhos WhatsApp usa como material **apenas o título e o texto do item da fonte**, delimitados em `<fonte>` como dados não confiáveis. O resultado é sempre `unverified` e segue para revisão humana nas issues; não é aprovação nem publicação. Validações locais: JSON com emoji de lista fechada, título ≤ 90 caracteres, 2–3 pontos ≤ 160 caracteres; **todo o número gerado tem de existir na fonte**. Resposta inválida → uma nova tentativa → rascunho por regras. Sem credencial, ou se o fornecedor falhar ou exceder o limite gratuito, só regras. O cliente (`llm.py`) é o segundo módulo com acesso à rede, apenas para os URLs HTTPS configurados em `config/llm.yaml`.

## 8. Prompts

- Um ficheiro por tarefa e versão: `prompts/<tarefa>@v<N>.md` (sistema + template + esquema de saída).
- Prompts são imutáveis depois de usados em produção; alterações criam nova versão.
- `llm_call.prompt_id` regista a versão usada.
- Cada prompt novo/alterado é acompanhado de casos de teste (fixtures de input + saída esperada ou propriedades a verificar), incluindo casos de anúncio vs. lei em vigor.

## 9. Custos e limites

- Limite de tokens por execução (`llm.max_tokens_per_run`) e por tarefa; ao atingir, as tarefas restantes usam fallback por regras e o relatório indica-o.
- Cache por `input_hash` + `prompt_id`.
- O relatório de cada execução inclui tokens por tarefa e fornecedor.

## 10. Auditoria

- Todas as chamadas são registadas em `llm_call` (prompt, modelo, output, tokens, erro).
- Por defeito guarda-se o hash do input; guardar o input completo é configurável (atenção a volume e a dados pessoais).
- Qualquer registo criado por IA identifica-se como `llm:<prompt_id>` nos campos `*_by`.
