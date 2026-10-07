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
- **Estado:** Aceite
- **Data:** 2026-10-07

### DEC-006 — Taxonomia editorial V1
- **Decisão:** 14 categorias (Segurança Social e prestações; Pensões e reformas; Emprego e desemprego; Salários e rendimento; Fiscalidade para particulares; Habitação e arrendamento; Apoios às famílias; Educação e estudantes; Saúde e apoios relacionados; Energia e água; Consumo e direitos do consumidor; Deficiência e inclusão; Idosos e cuidadores; Justiça e direitos dos cidadãos). Cada evento tem `category` (1), `subcategory` (0..1), `secondary_categories` (0..N), `audience` (1..N) e `impact_type` (1). A taxonomia é extensível e as categorias não têm o mesmo peso editorial. Campos conceptuais, não implementados.
- **Razão:** Resolver D4 e dar base comum à classificação, ao score e ao estilo.
- **Alternativas consideradas:** Manter a lista inicial de temas (misturava níveis, ex.: `desemprego` e `emprego_formacao`, sem audiência nem impacto); taxonomia hierárquica profunda (prematura sem dados reais).
- **Estado:** Aceite
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
- **Estado:** Aceite (texto final da nota de responsabilidade e norma ortográfica pendentes — D6, D11)
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
