# tensdireito-content-engine

Editorial Intelligence Engine para o [TensDireito.com](https://tensdireito.com) — descobre, verifica, classifica, pontua e transforma informação sobre apoios e direitos sociais em conteúdo editorial publicável.

> **Estado actual: M2 — fundação executável.** As decisões fundamentais foram fechadas no M1.
> Existe apenas a fundação mínima do projecto Python (pacote, CLI `tde` com `doctor`, testes). Ainda não há recolha, verificação, pontuação, geração nem exportação; a documentação em `docs/` continua a ser a especificação da implementação.

## Propósito

Os cidadãos perdem acesso a apoios e direitos porque a informação está dispersa, é técnica, muda com frequência e é muitas vezes noticiada de forma incompleta ou antes de estar oficialmente confirmada. O TensDireito.com explica essa informação de forma clara e fiável.

Este motor apoia a equipa editorial a encontrar o que mudou, confirmar o que é verdade, decidir o que merece ser publicado e produzir o conteúdo — sem nunca confundir uma notícia com uma confirmação.

## Objectivo

Construir um sistema que:

1. **descubra** informação relevante sobre Segurança Social, prestações sociais, emprego, habitação, fiscalidade e outras matérias com impacto nos direitos dos cidadãos;
2. **normalize e agrupe** várias notícias sobre o mesmo acontecimento num único evento;
3. **verifique** alterações a direitos, valores, condições, prazos ou legislação contra fontes oficiais, distinguindo `VERIFIED_OFFICIAL` de `VERIFIED_EDITORIAL`;
4. **pontue** cada acontecimento pela sua relevância editorial — sem que o score substitua a verificação — e consiga concluir que **não há nada suficientemente importante para publicar**;
5. **produza** conteúdo em vários formatos (WhatsApp, artigo, SEO; futuramente newsletter e redes sociais) a partir do mesmo acontecimento verificado, com rastreabilidade de cada afirmação até à fonte;
6. submeta todo o conteúdo a **aprovação humana** e o exporte — sem publicação automática na V1.

## Arquitectura conceptual

```
Fontes (T1 oficiais · T2 especializadas · T3 imprensa · T4 redes/não confirmado)
   │
   ▼
COLLECT ─▶ NORMALIZE ─▶ CLASSIFY ─▶ CLUSTER ─▶ VERIFY ─▶ SCORE ─▶ GENERATE ─▶ CHECK ─▶ REVIEW ─▶ EXPORT
descoberta  normalizada              Event      VERIFIED_*  score +  conteúdo            humano    ficheiros
                                     (assunto)              gate                         APPROVED  (não publica)
                                                               │
                                                               └─▶ Relatório: revisão editorial / watchlist /
                                                                   "nada suficientemente importante para publicar"
```

- Pipeline por etapas, cada uma um comando CLI independente e idempotente, comunicando através da base de dados.
- O **acontecimento** (`Event`) é a unidade editorial; é actualizado (não duplicado) quando o assunto evolui, e os formatos de conteúdo derivam dele.
- **Claims** e **evidências** (`source_evidence`) ligam cada afirmação importante a excertos literais das fontes.
- A IA é opcional em cada etapa, está isolada atrás de uma interface independente do fornecedor, e não verifica nem aprova.
- Monólito modular em Python, gerido com `uv`; pacote `tensdireito_content_engine`; CLI `tde`.
- SQLite na primeira implementação, com SQL isolado para migração para PostgreSQL.
- Execução manual primeiro; automação (GitHub Actions) só depois de decidida a persistência durável.

Detalhe em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Princípios

1. **Descobrir não é verificar. Verificar não é aprovar. Aprovar não é publicar.**
2. Alterações a direitos, valores, condições, prazos ou legislação só são afirmadas como facto com `VERIFIED_OFFICIAL`; `VERIFIED_EDITORIAL` nunca é apresentado como confirmação legal.
3. Seis níveis distintos: descoberta → normalizada → candidato editorial → acontecimento verificado → conteúdo editorial → aprovado. A publicação fica fora do sistema na V1.
4. Várias notícias sobre o mesmo acontecimento formam um único evento.
5. "Nada a publicar" é um resultado válido.
6. A IA ajuda a descobrir, classificar, sintetizar e escrever — não inventa factos nem substitui a verificação documental.
7. Rastreabilidade entre cada afirmação importante e as suas fontes.
8. Hierarquia de fontes: oficiais > especializadas > imprensa generalista > redes sociais/não confirmado.
9. Redes sociais detectam tendências, mas nunca confirmam isoladamente alterações legais ou direitos.
10. Múltiplos formatos a partir do mesmo acontecimento.
11. Começar simples; evoluir sem monólito desnecessário.
12. Python e base de dados simples primeiro.
13. Execução manual antes de automação.
14. Sem acoplamento a um único fornecedor de IA.
15. Score e verificação são dimensões separadas: o score ordena, a verificação bloqueia.
16. Na V1, a IA não substitui a aprovação humana.

## Roadmap resumido

| Fase | Âmbito | Estado |
|------|--------|--------|
| 0 | Arquitectura e documentação (M1 — decisões fundamentais fechadas) | **Em curso** |
| 1 | Fundação, fontes, recolha e normalização (manual) | Planeada |
| 2 | Classificação, agrupamento, pontuação e relatório | Planeada |
| 3 | Verificação, claims e rastreabilidade | Planeada |
| 4 | Geração de formatos, revisão humana e exportação | Planeada |
| 5 | Automação com execuções agendadas | Planeada |
| 6 | Evolução (PostgreSQL, novos formatos, publicação, redes sociais) | A avaliar |

Detalhe e decisões pendentes em [docs/ROADMAP.md](docs/ROADMAP.md).

## Desenvolvimento

Requer [`uv`](https://docs.astral.sh/uv/) e Python 3.12+.

```bash
uv sync              # cria o ambiente virtual e instala o projecto e as dependências de desenvolvimento
uv run pytest        # executa os testes (offline)
uv run ruff check .  # lint
uv run tde --help    # ajuda da CLI
uv run tde doctor    # diagnóstico: confirma que a aplicação está instalada e executável
```

`tde doctor` é determinístico: não acede à Internet, a APIs externas, a variáveis de ambiente nem a base de dados.

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Visão geral, princípios, componentes, níveis de maturidade, decisões arquitecturais. |
| [EDITORIAL_POLICY.md](docs/EDITORIAL_POLICY.md) | Regra central, transformações proibidas, taxonomia V1, níveis de verificação, relevância, rejeição, watchlist, Event, revisão humana. |
| [STYLE_GUIDE.md](docs/STYLE_GUIDE.md) | Estilo editorial: títulos, leads, WhatsApp, artigos, SEO, CTA, incerteza. |
| [DECISION_LOG.md](docs/DECISION_LOG.md) | Registo das decisões arquitecturais e editoriais. |
| [TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) | Stack, estrutura de código, CLI, interfaces internas, requisitos não funcionais. |
| [DATA_MODEL.md](docs/DATA_MODEL.md) | Entidades, campos, estados e enumerações. |
| [CONTENT_PIPELINE.md](docs/CONTENT_PIPELINE.md) | Etapas do pipeline, regras de verificação, formatos e relatório. |
| [SOURCES.md](docs/SOURCES.md) | Modelo de fontes (registry, endpoint, document, evidence), hierarquia, registo e lista candidata. |
| [SCORING.md](docs/SCORING.md) | Score editorial (separado da verificação): dimensões, pesos, penalizações, limiares e proposta. |
| [AI_RULES.md](docs/AI_RULES.md) | Utilização permitida de IA, grounding, validações e independência de fornecedor. |
| [SECURITY.md](docs/SECURITY.md) | Segredos, recolha responsável, prompt injection, RGPD, integridade editorial. |
| [ROADMAP.md](docs/ROADMAP.md) | Fases, critérios de saída e decisões pendentes. |
