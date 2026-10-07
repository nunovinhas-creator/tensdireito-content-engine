# Registo de evidência da validação de fontes

> Decisões: DEC-034 (verificações V1–V5 e correspondência com os estados), DEC-035 (regra automática "endpoint `ACTIVE` só em fonte `VALIDATED`") e DEC-036 (validador, resultados e registo de evidência). Protocolo em [SOURCES.md](../SOURCES.md#8-protocolo-de-validação-de-fontes) §8; contrato da unidade em [ROADMAP.md](../ROADMAP.md#m210--validação-de-fontes) M2.10.
>
> Este directório contém apenas este README. **Nenhuma fonte foi ainda validada** (D1 OPEN): não existe nenhum ficheiro de evidência de uma fonte real, e o modelo abaixo usa só marcadores (`<…>`).

## 1. O que é e onde fica

- **Um ficheiro por fonte:** `docs/source_validation/<source_id>.md`, em que `<source_id>` é o `id` da fonte em `config/sources.yaml`. O ficheiro cobre a fonte e todos os seus endpoints.
- **Versionado e revisto com o registo:** o ficheiro é criado ou alterado **no mesmo pull request** que muda o estado da fonte ou de um dos seus endpoints em `config/sources.yaml`. A descrição do pull request remete para o ficheiro, mas não o substitui.
- **Auditoria:** fonte, endpoint, data, pessoa, evidência V1–V5, resultado e limitações ficam no ficheiro; o estado resultante fica em `config/sources.yaml`; ambos são revistos no mesmo pull request. O histórico do git liga cada registo ao pull request que o introduziu.

## 2. Só acrescentado

- O ficheiro é **só acrescentado** (append-only): registos anteriores nunca são apagados nem reescritos.
- **Verificações falhadas não são apagadas:** um registo com `falha` fica no ficheiro, mesmo depois de uma verificação posterior com `ok`.
- Uma revalidação acrescenta registos novos, com o seu `checked_at`; não altera os anteriores.

## 3. Quem valida

- A validação é **humana**. `checked_by` (cada verificação) e `validated_by` (cada passagem de estado) identificam uma **pessoa**, de forma declarativa (sem autenticação na V1 — DEC-014).
- **Não são validadores:** modelos de IA (`llm:*` ou qualquer outro identificador de modelo), bots e contas de automação.
- O `validated_by` de uma passagem de estado consta como `checked_by` de pelo menos uma das verificações exigidas para esse estado.
- A passagem produz efeito com o merge do pull request por uma pessoa com permissão de merge. Na V1 não se exige revisor diferente do validador.
- A lista nominal de validadores não é fixada (D7 continua em aberto).
- **Papel do modelo:** pode ajudar a redigir o registo, a rever a sua forma ou a resumir observações fornecidas por uma pessoa. Não fornece nem completa URLs, feeds ou endpoints (SOURCES.md §8.3), não executa as verificações, não decide `result` e nunca é `checked_by` nem `validated_by`.

## 4. O sistema não lê este ficheiro

- Nenhum comando, tabela, campo do YAML ou verificação automática lê ou valida a evidência.
- A única regra automática relacionada é a de DEC-035, verificada por `tde sources validate` a partir de `config/sources.yaml`: um endpoint `ACTIVE` exige fonte `VALIDATED`. A existência e o conteúdo da evidência, os `domains`, as verificações V1–V5 e a identidade de quem valida verificam-se na revisão do pull request.

## 5. Conteúdo do ficheiro

Cada ficheiro tem quatro partes:

1. **Identificação:** `source_id` e os `endpoint_id` abrangidos.
2. **Registos de verificação**, com os campos de SOURCES.md §8.4, sem alterações:

   | Campo | Conteúdo |
   |-------|----------|
   | `source_id` / `endpoint_id` | Identificadores do registo. |
   | `check` | `V1` a `V5` (SOURCES.md §8.1). |
   | `checked_at` | Data e hora ISO 8601 com fuso explícito. |
   | `checked_by` | Pessoa (nunca um modelo). |
   | `method` | Passos para repetir a verificação. |
   | `observation` | O que foi observado. |
   | `result` | `ok` · `falha` · `não aplicável`, com motivo quando não é `ok`. |

3. **Limitações:** cada limitação com a verificação e a questão aberta a que se refere (por exemplo, Q2, Q3, Q5, Q6, Q7, D12, D13).
4. **Passagens de estado pedidas:** entidade, estado anterior → estado novo, `validated_at`, `validated_by`.

## 6. Regras de resultado

- **Verificações exigidas por estado** (SOURCES.md §8.2):

  | Entidade | Estado pedido | Exige `ok` em |
  |----------|---------------|---------------|
  | Fonte | `VALIDATED` | V1 e V4 da fonte |
  | Endpoint | `VALIDATED` | V2, V3 e V5 |
  | Endpoint | `ACTIVE` | V4 do endpoint (com endpoint já `VALIDATED`, fonte `VALIDATED`, collector registado para o `endpoint_type` e decisão explícita de activar) |

- Uma passagem de estado exige `ok` em **todas** as verificações exigidas para o estado pedido. `falha`, ausência de registo ou `não aplicável` numa verificação exigida impedem a passagem; a entrada mantém o estado anterior e os registos ficam no ficheiro.
- `não aplicável` só regista que uma verificação não se aplica à entidade (por exemplo, V3 numa fonte); nunca substitui `ok` numa verificação exigida.
- Nenhuma verificação é inferida de outra (DEC-034).
- Para V3, `ok` só é possível para um `endpoint_type` com collector registado e contrato definido — hoje apenas `rss` (DEC-032, DEC-033).
- Uma limitação que torne negativa ou desconhecida a resposta à pergunta da verificação obriga a `falha`, não a `ok` com reserva.
- **Passagens:** cada passagem é um pull request; uma entrada não avança dois estados no mesmo pull request. Um endpoint passa a `VALIDATED` num pull request e a `ACTIVE` noutro, posterior, que é a decisão explícita de activar. A fonte e os seus endpoints podem mudar de estado no mesmo pull request, cada um uma vez. `url` continua nulo em `CANDIDATE`.

## 7. Modelo

Copiar para `docs/source_validation/<source_id>.md` e substituir **todos** os marcadores `<…>`. O modelo não contém nenhuma fonte, URL, pessoa nem resultado; não é um exemplo de validação. Repetir o bloco de verificação tantas vezes quantas as verificações feitas; nunca apagar blocos anteriores.

````markdown
# Validação de fontes — <source_id>

## Identificação

- `source_id`: <source_id>
- `endpoint_id` abrangidos: <endpoint_id>, <endpoint_id>

## Registos de verificação

### <source_id ou endpoint_id> — <V1 | V2 | V3 | V4 | V5> — <checked_at>

- `source_id`: <source_id>
- `endpoint_id`: <endpoint_id ou "—" numa verificação da fonte>
- `check`: <V1 | V2 | V3 | V4 | V5>
- `checked_at`: <data e hora ISO 8601 com fuso explícito>
- `checked_by`: <pessoa>
- `method`: <passos para repetir a verificação>
- `observation`: <o que foi observado>
- `result`: <ok | falha | não aplicável> — <motivo, obrigatório quando não é ok>

## Limitações

- <verificação> — <questão aberta> — <descrição da limitação>

## Passagens de estado pedidas

| Entidade | Estado anterior → estado novo | `validated_at` | `validated_by` |
|----------|-------------------------------|----------------|----------------|
| <source_id ou endpoint_id> | <ESTADO> → <ESTADO> | <data e hora ISO 8601 com fuso explícito> | <pessoa> |
````
