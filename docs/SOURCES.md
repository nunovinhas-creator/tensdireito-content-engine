# Fontes

> Estado: **especificação**. Define a hierarquia de fontes, o formato do registo e as regras de utilização. A lista de fontes concretas é uma **lista candidata**: nenhuma fonte foi ainda testada, e o mecanismo de recolha (RSS, página HTML, manual) de cada uma tem de ser confirmado na Fase 1.

## 1. Hierarquia

| Tier | Categoria | Pode descobrir? | Pode confirmar claims críticas? | Exemplos de tipo |
|------|-----------|-----------------|--------------------------------|------------------|
| **T1** | Fontes oficiais | Sim | **Sim** | Diário da República, portais de organismos públicos, Governo, Assembleia da República. |
| **T2** | Fontes especializadas | Sim | Não isoladamente; reforço e contexto. Excepção controlada: ver 3.3. | Ordens profissionais, associações de defesa do consumidor, publicações jurídicas/fiscais especializadas. |
| **T3** | Imprensa generalista | Sim | Não | Jornais e agências de notícias nacionais. |
| **T4** | Redes sociais / não confirmado | Sim (sinal/tendência) | **Nunca** | Publicações em redes sociais, fóruns, pistas manuais sem origem verificável. |

Regras derivadas:
- O tier é atributo da **fonte**, não do item. Um artigo de imprensa que cita um diploma é T3; o diploma é T1 e tem de ser recolhido como documento próprio para servir de evidência.
- Uma página oficial que reproduz um anúncio político ("o Governo vai...") é T1 enquanto fonte, mas a claim correspondente é um anúncio, não uma alteração em vigor (ver `change_type = announcement`).
- Conteúdo T4 pode criar eventos candidatos e aumentar a dimensão de *interesse público* na pontuação, mas nunca a dimensão de *confiança*.

## 2. Registo de fontes (`config/sources.yaml`)

Formato:

```yaml
- id: dre_serie_1                 # identificador estável, snake_case
  name: "Diário da República — 1.ª Série"
  tier: T1
  source_type: html_page          # rss | html_page | manual
  url: "https://..."              # a preencher após validação
  topics: [legislation]           # temas predominantes (taxonomy.yaml)
  active: false                   # só true após validação
  fetch:
    frequency: daily              # hourly | daily | weekly — indicativo para agendamento
    rate_limit_seconds: 5
    max_items: 50
    selectors: {}                 # apenas html_page: selectores CSS de lista/título/link/data
  notes: "Validar existência de feed e termos de utilização."
  validated_at: null              # data da última validação manual
```

Regras:
- Uma fonte só passa a `active: true` depois de validada manualmente (URL, mecanismo, termos de utilização, `robots.txt`), com `validated_at` preenchido.
- Alterações ao registo são feitas por pull request.
- `tde sources validate` verifica o esquema, IDs únicos, tiers válidos e campos obrigatórios por `source_type`.

## 3. Regras de utilização

### 3.1 Descoberta vs. confirmação
Qualquer tier pode originar um candidato. Só T1 confirma claims críticas (ver [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md#etapa-5--verify)).

### 3.2 Independência
Duas notícias T3 que reproduzem o mesmo comunicado ou a mesma agência **não** são duas fontes independentes. Na v1, a independência é avaliada de forma conservadora: documentos com elevada similaridade textual entre si contam como uma só fonte para efeitos de pontuação.

### 3.3 Ausência de fonte oficial
Há matérias em que não existe fonte oficial publicada em tempo útil (ex.: alteração de procedimento comunicada apenas por canais informais). Nesses casos:
- o evento fica, no máximo, `partially_verified` ou `unverified`;
- só pode passar a `verified` com ≥2 evidências T2 independentes **e** override humano registado com motivo;
- o conteúdo gerado tem de identificar a origem da informação e a ausência de confirmação oficial.

### 3.4 Redes sociais
- Na v1 **não** existe recolha automática de redes sociais. Pistas vistas em redes sociais entram via `tde add-manual` como T4.
- Recolha automatizada de redes sociais exige decisão prévia sobre plataformas, termos de utilização, custos de API e protecção de dados (ver [SECURITY.md](SECURITY.md)).
- Nunca guardar dados pessoais de autores de publicações para além do estritamente necessário (URL da publicação).

## 4. Lista candidata inicial (a validar)

Esta lista identifica **organismos e tipos de fonte** relevantes para o âmbito editorial. URL, mecanismo de recolha e termos de utilização ainda não foram verificados — por isso não são indicados URLs nem se assume a existência de feeds.

### T1 — Oficiais
| Fonte | Temas | Observações |
|-------|-------|-------------|
| Diário da República (1.ª Série) | legislação, todos | Fonte primária para confirmação de diplomas. |
| Segurança Social (portal e notícias) | seguranca_social, prestacoes_familiares, desemprego, pensoes_reforma, deficiencia_incapacidade | |
| Portal das Finanças / Autoridade Tributária | fiscalidade_irs | |
| IEFP | emprego_formacao, desemprego | |
| Portal da Habitação / IHRU | habitacao | |
| Portal do Governo (comunicados do Conselho de Ministros) | todos | Frequentemente anúncios, não diplomas — usar `change_type = announcement`. |
| ePortugal / gov.pt | procedimentos | Útil para claims de procedimento ("como pedir"). |
| Assembleia da República | legislação | Iniciativas legislativas: sinal de futuro, não de alteração em vigor. |
| SNS / DGS | saude | |
| ACT — Autoridade para as Condições do Trabalho | direitos_laborais | |

### T2 — Especializadas
| Fonte | Temas | Observações |
|-------|-------|-------------|
| DECO / Proteste | consumo, fiscalidade_irs, energia_custo_vida | |
| Ordens profissionais relevantes (ex.: contabilistas certificados) | fiscalidade_irs | |
| Publicações jurídicas/fiscais especializadas | legislação | A definir. |

### T3 — Imprensa generalista
Jornais e agências nacionais com secções de economia/sociedade. **Selecção a definir** (decisão editorial).

### T4 — Redes sociais / não confirmado
Apenas entrada manual na v1.

## 5. Manutenção

- Rever o registo mensalmente: fontes com erros repetidos (`last_error`) ou sem itens relevantes em 60 dias são candidatas a desactivação.
- Alterações de estrutura em fontes `html_page` devem ser detectadas por testes com fixtures e por alerta quando uma fonte devolve 0 itens em N execuções consecutivas.
