# Fontes

> Estado: **especificação + registo operacional**. Define o modelo de fontes, a hierarquia de confiança, o registo e as regras de utilização. `config/sources.yaml` contém endpoints reais, mas a presença no YAML não é prova suficiente de validação: estados `ACTIVE`/`VALIDATED` exigem evidência e revisão; endpoints com falhas recentes foram desactivados até nova validação.

## 1. Princípio

> **SOURCE DISCOVERY ≠ SOURCE VERIFICATION**

- Saber (ou supor) que uma entidade publica informação útil é **descoberta de fonte**. Não autoriza recolha nem atribui confiança.
- **Verificação de fonte** é a validação manual de que um endpoint concreto pertence de facto à entidade, funciona, e pode ser usado (termos de utilização, `robots.txt`). Só depois a fonte pode ser recolhida e servir de evidência com o seu tier.
- Da mesma forma, encontrar um documento numa fonte é descoberta de informação; não verifica as afirmações que contém (ver [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md#2-regra-central)).

Uma fonte não passa a existir no sistema por ser conveniente. Um link oficial citado numa notícia não torna o seu domínio uma fonte T1 validada.

## 2. Modelo de fontes

Quatro conceitos, com funções distintas:

| Conceito | Função | Ciclo de vida | Exemplo (natureza, sem URLs) |
|----------|--------|---------------|------------------------------|
| **`source_registry`** | Identifica **quem** publica e **que confiança** merece (tier). Uma entrada por entidade ou publicação. | `CANDIDATE` → `VALIDATED` → `INACTIVE` | "Segurança Social" (T1). |
| **`source_endpoint`** | Identifica **onde e como** se obtém informação dessa fonte: uma página de listagem, um feed, entrada manual. Uma fonte pode ter vários endpoints, ou nenhum conhecido. | `CANDIDATE` → `VALIDATED` → `ACTIVE` → `INACTIVE` | "Página de notícias da Segurança Social" — URL desconhecido até validação. |
| **`source_document`** | Um **documento concreto** obtido a partir de um endpoint (ou entrada manual): um diploma, uma página de prestação, uma notícia. Captura bruta em `raw_item`, versão normalizada em `source_document`. | descoberto → normalizado | O texto de um diploma publicado. |
| **`source_evidence`** | Um **excerto literal** de um `source_document` ligado a uma `claim`, com posição (`supports`, `contradicts`, `context`). É o que sustenta a verificação. | proposto → validado (excerto encontrado literalmente) | A frase do diploma que fixa um valor. |

Relações: `source_registry 1─N source_endpoint 1─N source_document 1─N source_evidence N─1 claim`.

Esquema em [DATA_MODEL.md](DATA_MODEL.md#21-modelo-de-fontes--quatro-conceitos-distintos).

## 3. Hierarquia de confiança

| Tier | Categoria | Pode descobrir? | Contribui para `VERIFIED_EDITORIAL`? | Pode produzir `VERIFIED_OFFICIAL`? | Exemplos de tipo |
|------|-----------|-----------------|--------------------------------------|-----------------------------------|------------------|
| **T1** | Fontes oficiais | Sim | Sim | **Sim** (se o documento for adequado ao estágio da claim) | Jornal oficial, organismos públicos, Governo, Assembleia da República. |
| **T2** | Fontes especializadas | Sim | Sim | **Nunca** | Associações de defesa do consumidor, ordens profissionais, publicações jurídicas/fiscais especializadas. |
| **T3** | Imprensa generalista | Sim | Sim, com ≥2 fontes independentes | **Nunca** | Jornais e agências nacionais. |
| **T4** | Redes sociais / não confirmado | Sim (sinal) | **Nunca** | **Nunca** | Redes sociais, fóruns, pistas sem origem verificável. |

A hierarquia privilegia sempre as fontes oficiais: perante evidência T1 validada, prevalece a T1.

### 3.1 Regras derivadas
- O tier é atributo da **fonte** (`source_registry`), não do documento. Um artigo de imprensa que cita um diploma é T3; o diploma é T1 e tem de ser recolhido como `source_document` próprio para servir de evidência oficial.
- Uma página oficial que reproduz um anúncio político ("o Governo vai…") é T1 enquanto fonte, mas só confirma o **anúncio** (`legal_stage = announcement`), não uma alteração em vigor.
- Uma fonte cujo registo não está `VALIDATED` é tratada como T4, seja qual for o tier que viria a ter.
- Conteúdo T4 pode originar eventos candidatos e contar como sinal de interesse; nunca conta como evidência.

### 3.2 Independência
Duas notícias que reproduzem o mesmo comunicado ou a mesma agência **não** são fontes independentes. Na V1, a independência é avaliada de forma conservadora: documentos com elevada similaridade textual entre si contam como uma só fonte.

### 3.3 Ausência de fonte oficial
Há matérias em que não existe fonte oficial publicada em tempo útil. Nesses casos:
- o evento fica, no máximo, `VERIFIED_EDITORIAL`;
- nenhuma decisão humana o eleva a `VERIFIED_OFFICIAL` — só a ligação de evidência oficial validada o faz;
- o conteúdo gerado identifica a origem da informação e a ausência de confirmação oficial.

(Resolve a decisão pendente D5 da especificação inicial — ver [DECISION_LOG.md](DECISION_LOG.md), DEC-004.)

### 3.4 Pistas manuais
- Pistas vistas fora das fontes registadas (ex.: redes sociais, indicação de um leitor) entram por entrada manual (`tde add-manual`).
- O tier de uma pista manual **não é declarado pelo utilizador**: é T1/T2/T3 apenas se o URL pertencer a um domínio registado (`source_registry.domains`) de uma fonte `VALIDATED`; caso contrário é T4.

### 3.5 Redes sociais
- Na V1 **não** existe recolha automática de redes sociais.
- Recolha automatizada exige decisão prévia sobre plataformas, termos de utilização, custos e protecção de dados (ver [SECURITY.md](SECURITY.md)).
- Nunca guardar dados pessoais de autores de publicações para além do URL da publicação.

## 4. Registo (`config/sources.yaml`)

O registo vive num ficheiro versionado (a criar na implementação), revisto por pull request. Formato conceptual — os valores abaixo são **marcadores**, não dados reais:

```yaml
- id: exemplo_fonte_oficial         # identificador estável, snake_case
  name: "<nome da entidade>"
  entity_type: public_body          # public_body | official_journal | government | parliament | specialised | press | social | other
  tier: T1
  categories: [seguranca_social]    # códigos da taxonomia (EDITORIAL_POLICY.md)
  domains: []                       # preenchido só após validação
  registry_status: CANDIDATE        # CANDIDATE | VALIDATED | INACTIVE
  validated_at: null
  validated_by: null                # pessoa que validou; obrigatório em VALIDATED
  notes: "Por validar: endpoints, termos de utilização, robots.txt."
  endpoints:
    - id: exemplo_fonte_oficial_noticias
      endpoint_type: html_page      # rss | html_page | manual
      url: null                     # nunca preenchido por suposição
      endpoint_status: CANDIDATE    # CANDIDATE | VALIDATED | ACTIVE | INACTIVE
      fetch:
        frequency: daily            # indicativo
        rate_limit_seconds: 5
        max_items: 50
        selectors: {}               # apenas html_page
      redirect_hosts: []            # DEC-065/070: anfitriões exactos para onde se aceita um redirect
      redirect_is_throttle: false   # DEC-066/070: só as pesquisas do Bing (302/307 = limitação)
      expect_min_items: null        # DEC-072: mínimo de itens por run (canário)
      validated_at: null
      validated_by: null            # obrigatório em VALIDATED/ACTIVE
```

Formato do ficheiro:
- **Codificação e sintaxe:** UTF-8; outra codificação não é suportada. Uma chave repetida no mesmo mapeamento é erro (DEC-025).
- **Schema fechado:** cada fonte e cada endpoint só aceita os campos do exemplo acima; qualquer outro campo é erro. O conteúdo de `fetch` não é validado para além de ser um mapeamento (DEC-023).
- **Estados:** `registry_status` e `endpoint_status` escrevem-se na forma documental em maiúsculas (`CANDIDATE`, `VALIDATED`, `ACTIVE`, `INACTIVE`); minúsculas são erro. Na implementação são convertidos para o valor interno em minúsculas. `entity_type`, `endpoint_type` e `tier` escrevem-se como no exemplo, que é também o valor interno (DEC-024).
- **Datas:** `validated_at` em ISO 8601 com fuso explícito; nenhum fuso é assumido.
- **Canário (DEC-072):** `expect_min_items` é opcional (inteiro positivo); abaixo dele em 2 runs seguidos, o endpoint aparece como `suspeito` no resumo do run.
- **Redirects (DEC-070):** `redirect_hosts` é opcional (por omissão, nenhum redirect é seguido) e cada anfitrião acrescentado exige o registo humano do destino em `docs/source_validation/<id>.md`; `redirect_is_throttle` é opcional (por omissão, `false`) e não se combina com `redirect_hosts`.

Regras:
- Um endpoint só é recolhido em `ACTIVE`, e só passa a `VALIDATED`/`ACTIVE` após validação manual (URL confirmado, mecanismo, termos de utilização, `robots.txt`), registada no próprio registo com `validated_at` e `validated_by` e revista por pull request.
- **Estado de validação operacional vs. decisão editorial (DEC-030):** nesta fase, `validated_at` e `validated_by` do registo constituem o estado de validação operacional de uma fonte ou endpoint `VALIDATED`/`ACTIVE`. A decisão editorial `VALIDATE_SOURCE` em `editorial_decision` ([DATA_MODEL.md](DATA_MODEL.md#37-editorial_decisiondecision) §3.7) não é requisito actual, porque essa entidade ainda não existe; fica para a unidade futura que a introduzir, que pode rever esta regra.
- Uma fonte pode estar `VALIDATED` sem nenhum endpoint activo (útil para reconhecer o tier de pistas manuais pelo domínio).
- `tde sources validate` verifica o esquema, IDs únicos, tiers válidos e campos obrigatórios; recusa endpoints `ACTIVE` sem `url` e sem `validated_at`, e endpoints `ACTIVE` cuja fonte não esteja `VALIDATED` (DEC-035; implementado no M2.10). Não verifica `domains`, a evidência de validação, as verificações V1–V5 nem a identidade de quem valida, que ficam para a revisão do pull request (secção 8).
- **`fetch` no M2.9:** `fetch` continua fora da projecção para o domínio e o SQLite (DEC-028). Os valores de `frequency`, `rate_limit_seconds`, `max_items` e `selectors` **não têm efeito** na recolha; o collector `rss` usa os limites fixos de DEC-033. A execução é sempre manual (`tde collect`); `frequency` não agenda nada (D8, D9).
- O procedimento de validação manual, a correspondência entre verificações e estados e o formato do registo de evidência estão na secção 8 (DEC-034).

## 5. Evidência oficial adequada

Nem todo o documento T1 confirma tudo. O que um documento oficial pode confirmar depende do seu tipo (`document_kind`) e do estágio da claim:

| `legal_stage` da claim | Evidência oficial adequada para `VERIFIED_OFFICIAL` |
|------------------------|-----------------------------------------------------|
| `proposal` | Documento oficial da proposta ou da iniciativa (Governo, Assembleia da República, consulta pública). |
| `announcement` | Comunicação oficial do órgão que anuncia. |
| `approved` | Comunicação oficial do órgão que aprovou. |
| `published` / `in_force` / `ended` (alterações legislativas) | Publicação oficial do diploma (`legal_text`); a **versão consolidada oficial** (`consolidated_legal_text`) é privilegiada quando aplicável, nomeadamente para o texto vigente após várias alterações. |
| Regras administrativas, valores, procedimentos e prazos aplicados por um organismo | Página ou documento oficial do organismo competente (`official_page`), ou o diploma. |

Uma comunicação política oficial ("o Governo aprovou…") **não** confirma que a medida está em vigor.

## 6. Lista candidata inicial (a validar)

Organismos e tipos de fonte relevantes para o âmbito editorial. **Nada nesta lista foi validado**: não se indicam URLs, nem se assume a existência de RSS, feeds ou APIs. A designação e a orgânica de ministérios e organismos pode mudar com o Governo; confirmar na validação.

### T1 — Oficiais (candidatas)
| Fonte | Categorias principais | Observações |
|-------|-----------------------|-------------|
| Diário da República | todas | Fonte primária para confirmar diplomas; verificar disponibilidade de versão consolidada para cada caso. |
| Segurança Social | `seguranca_social`, `pensoes_reformas`, `apoios_familias`, `emprego_desemprego`, `deficiencia_inclusao`, `idosos_cuidadores` | |
| gov.pt | várias | Mencionado como candidato; natureza do conteúdo e relação com outros portais públicos a confirmar na validação. |
| Portal do Governo (comunicados, incluindo do Conselho de Ministros) | todas | Frequentemente anúncios ou aprovações, não diplomas — `legal_stage ∈ {announcement, approved}`. |
| Ministério com a tutela do Trabalho, Solidariedade e Segurança Social | `emprego_desemprego`, `seguranca_social`, `salarios_rendimento` | Designação actual: Ministério do Trabalho, Solidariedade e Segurança Social (a confirmar). |
| IEFP | `emprego_desemprego` | |
| Autoridade Tributária / Portal das Finanças | `fiscalidade_particulares` | Duas designações candidatas; relação entre ambas a confirmar na validação. |
| IHRU / portal público de habitação | `habitacao_arrendamento` | |
| DGES | `educacao_estudantes` | Ensino superior (acesso, bolsas). |
| ePortugal | procedimentos, todas | Útil para claims de procedimento. Relação com gov.pt a confirmar. |
| Assembleia da República | todas | Iniciativas legislativas: sinal de futuro (`proposal`), não de alteração em vigor. |
| SNS / DGS | `saude_apoios` | |
| ACT — Autoridade para as Condições do Trabalho | `emprego_desemprego` | |
| Outras entidades públicas relevantes por tema | conforme o tema | Ex.: reguladores sectoriais (energia, água, comunicações), entidades de defesa do consumidor públicas. Acrescentadas por decisão registada. |

### T2 — Especializadas (candidatas)
| Fonte | Categorias | Observações |
|-------|-----------|-------------|
| DECO / Proteste | `consumo`, `fiscalidade_particulares`, `energia_agua` | |
| Ordens profissionais relevantes (ex.: contabilistas certificados) | `fiscalidade_particulares` | |
| Publicações jurídicas/fiscais especializadas | várias | A definir. |

### T3 — Imprensa generalista
Jornais e agências nacionais com secções de economia/sociedade. **Selecção a definir** (decisão editorial, D2).

### T4 — Redes sociais / não confirmado
Apenas entrada manual na V1.

## 7. Manutenção

- Rever o registo mensalmente: endpoints com erros repetidos ou sem itens relevantes em 60 dias são candidatos a `INACTIVE`.
- Alterações de estrutura em endpoints `html_page` devem ser detectadas por testes com fixtures e por alerta quando um endpoint devolve 0 itens em N execuções consecutivas.
- Desactivar ou alterar o tier de uma fonte é uma decisão registada: nesta fase, por pull request no registo; a decisão `DEACTIVATE_SOURCE` em `editorial_decision` aplica-se quando essa entidade existir (DEC-030).

## 8. Protocolo de validação de fontes

> Decisões: DEC-034 (verificações e estados), DEC-035 (regra automática "endpoint `ACTIVE` só em fonte `VALIDATED`") e DEC-036 (validador, resultados e registo de evidência). O processo é definido pelo M2.10 ([ROADMAP.md](ROADMAP.md#m210--validação-de-fontes)) e executado por uma pessoa, separado do código dos collectors. Existe um registo de verificações para o Diário da República em [source_validation/dre.md](source_validation/dre.md); a validação das restantes fontes e a revisão contínua dos endpoints continuam a exigir evidência própria.

### 8.1 Cinco verificações distintas

Uma fonte não passa a ser válida por existir tecnicamente. Cada verificação é registada à parte; nenhuma é inferida de outra.

| # | Verificação | Pergunta | Exemplos de evidência (natureza, sem URLs) |
|---|-------------|----------|---------------------------------------------|
| V1 | Existência da fonte | A entidade existe e é quem diz ser? Que tier merece? | Designação oficial e orgânica actual; domínio institucional da entidade. |
| V2 | Existência do endpoint | O ponto de acesso é publicado pela própria entidade, num domínio seu, e foi encontrado a partir dela? | Página da entidade que anuncia o feed ou a listagem; caminho de navegação desde a página inicial do domínio oficial. |
| V3 | Validade técnica | O endpoint cumpre o contrato do collector do seu tipo e a política de transporte? | Para `rss` (DEC-032, DEC-033): `https`, sem redirect, `200`, `Content-Type` aceite, sem compressão, dentro dos limites, RSS 2.0 sem `DOCTYPE`, cada item com `<title>` e `<link>` absoluto; dois pedidos espaçados com itens estáveis. |
| V4 | Adequação editorial | A fonte e o conteúdo do endpoint cabem no âmbito editorial e na taxonomia ([EDITORIAL_POLICY.md](EDITORIAL_POLICY.md)), em português, com o tier confirmado? | Amostra de itens classificada manualmente por categoria; tipo de conteúdo (anúncios, diplomas, procedimentos). |
| V5 | Autorização de recolha | Os termos de utilização e o `robots.txt` permitem a recolha automática? Há paywall, autenticação ou medidas anti-bot? | Termos de utilização lidos na data; conteúdo relevante do `robots.txt` na data. |

### 8.2 Correspondência com os estados do registo

| Estado | Exige | Notas |
|--------|-------|-------|
| Fonte `CANDIDATE` | — | Descoberta. Sem `domains`. |
| Fonte `VALIDATED` | V1 e V4 (da fonte) | `domains` confirmados; `validated_at`/`validated_by` (DEC-030). |
| Endpoint `CANDIDATE` | — | `url` nulo, mesmo que V2 já esteja registada. |
| Endpoint `VALIDATED` | V2, V3, V5 | `url` = URL confirmado (o final, sem redirects); `validated_at`/`validated_by`. |
| Endpoint `ACTIVE` | Endpoint `VALIDATED`, fonte `VALIDATED`, V4 do endpoint, collector registado no código para o `endpoint_type`, decisão explícita de activar | A exigência de fonte `VALIDATED` é verificada por `tde sources validate` desde a implementação do M2.10 (DEC-035): um endpoint `ACTIVE` numa fonte `CANDIDATE` ou `INACTIVE` é erro, e `tde sources sync` recusa esse registo. As restantes exigências continuam a ser verificadas na revisão. A decisão de activar é um pull request próprio, posterior ao que torna o endpoint `VALIDATED` (DEC-036). |
| `INACTIVE` | Decisão registada por pull request | Ver secção 7. |

Cada passagem de estado é um pull request no registo, revisto por uma pessoa. Uma entrada não avança dois estados no mesmo pull request (DEC-036).

### 8.3 Origem dos dados

- URLs, feeds e endpoints obtêm-se **apenas** por navegação ou documentação das fontes oficiais, feitas por uma pessoa.
- Nunca são inferidos, completados ou sugeridos por um modelo de IA, nem copiados de terceiros (uma notícia que cita um link oficial não valida esse link — secção 1).
- Um modelo pode ajudar a redigir o registo, mas não fornece URLs e não é `validated_by` (DEC-014).

### 8.4 Registo de evidência

Cada verificação fica registada de forma reproduzível no ficheiro versionado `docs/source_validation/<source_id>.md` (um por fonte, cobrindo a fonte e os seus endpoints), criado ou alterado no pull request que altera o estado; a descrição do pull request remete para ele (DEC-036). O ficheiro é só acrescentado: nenhum registo, incluindo os de verificações falhadas, é apagado ou reescrito. Campos de cada registo:

| Campo | Conteúdo |
|-------|----------|
| `source_id` / `endpoint_id` | Identificadores do registo. |
| `check` | `V1` a `V5`. |
| `checked_at` | Data e hora ISO 8601 com fuso explícito. |
| `checked_by` | Pessoa (nunca um modelo). |
| `method` | Passos para repetir a verificação (ex.: navegação desde a página inicial do domínio oficial; pedido `GET` com a ferramenta indicada e o `User-Agent` do projecto). |
| `observation` | O que foi observado (ex.: código HTTP, `Content-Type`, tamanho, número de itens, presença de `<title>`/`<link>`, excerto relevante dos termos ou do `robots.txt`). |
| `result` | `ok` · `falha` · `não aplicável`, com motivo. |

Amostras reais de feeds não entram em `tests/fixtures/`: os testes usam fixtures sintéticas, sem fontes nem URLs reais.

### 8.5 Resultados, limitações e validador

- **Resultados (DEC-036):** uma passagem de estado exige `ok` em todas as verificações que a secção 8.2 exige para o estado pedido. `falha`, ausência de registo ou `não aplicável` numa verificação exigida impedem a passagem. `não aplicável` só regista que uma verificação não se aplica à entidade. Para V3, `ok` só é possível para um `endpoint_type` com collector e contrato definidos — hoje apenas `rss`.
- **Limitações:** registadas na secção de limitações do ficheiro de evidência, com a verificação e a questão aberta a que se referem (ex.: Q2, Q3, D12, D13). Uma limitação que torne negativa ou desconhecida a resposta à pergunta da verificação é `falha`, não `ok` com reserva.
- **Validador:** `checked_by` e `validated_by` identificam uma pessoa (DEC-014), nunca um modelo (`llm:*` ou outro), conta de automação ou bot. O `validated_by` de uma passagem consta como `checked_by` de pelo menos uma das verificações exigidas. A passagem produz efeito com o merge do pull request. Um modelo pode ajudar a redigir ou rever o registo, mas não fornece URLs, não executa as verificações e não decide o resultado.
