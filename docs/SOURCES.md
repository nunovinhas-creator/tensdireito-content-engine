# Fontes

> Estado: **especificação (M1)**. Define o modelo de fontes, a hierarquia de confiança, o registo e as regras de utilização. A lista de fontes é uma **lista candidata**: nenhuma fonte foi testada, **nenhum URL, feed, RSS ou API é assumido**, e o mecanismo de recolha de cada uma só será conhecido após validação manual.

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
      validated_at: null
```

Regras:
- Um endpoint só é recolhido em `ACTIVE`, e só passa a `VALIDATED`/`ACTIVE` após validação manual registada (URL confirmado, mecanismo, termos de utilização, `robots.txt`), com `validated_at` e decisão `VALIDATE_SOURCE` em `editorial_decision`.
- Uma fonte pode estar `VALIDATED` sem nenhum endpoint activo (útil para reconhecer o tier de pistas manuais pelo domínio).
- `tde sources validate` verifica o esquema, IDs únicos, tiers válidos e campos obrigatórios; recusa endpoints `ACTIVE` sem `url` e sem `validated_at`.

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
- Desactivar ou alterar o tier de uma fonte é uma decisão registada.
