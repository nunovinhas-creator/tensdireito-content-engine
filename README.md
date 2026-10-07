# tensdireito-content-engine

Editorial Intelligence Engine para o [TensDireito.com](https://tensdireito.com) — descobre, verifica, classifica, pontua e transforma informação sobre apoios e direitos sociais em conteúdo editorial publicável.

> **Estado actual: Architecture / Documentation phase.**
> Ainda não existe código de aplicação. Este repositório contém, nesta fase, apenas a documentação técnica que servirá de especificação para a implementação.

## Propósito

Os cidadãos perdem acesso a apoios e direitos porque a informação está dispersa, é técnica, muda com frequência e é muitas vezes noticiada de forma incompleta ou antes de estar oficialmente confirmada. O TensDireito.com explica essa informação de forma clara e fiável.

Este motor apoia a equipa editorial a encontrar o que mudou, confirmar o que é verdade, decidir o que merece ser publicado e produzir o conteúdo — sem nunca confundir uma notícia com uma confirmação.

## Objectivo

Construir um sistema que:

1. **descubra** informação relevante sobre Segurança Social, prestações sociais, emprego, habitação, fiscalidade e outras matérias com impacto nos direitos dos cidadãos;
2. **normalize e agrupe** várias notícias sobre o mesmo acontecimento num único evento;
3. **verifique** alterações a direitos, valores, condições, prazos ou legislação contra fontes oficiais;
4. **pontue** cada acontecimento pela sua relevância editorial — e consiga concluir que **não há nada a publicar**;
5. **produza** conteúdo em vários formatos (WhatsApp, artigo, SEO; futuramente newsletter e redes sociais) a partir do mesmo acontecimento verificado, com rastreabilidade de cada afirmação até à fonte.

## Arquitectura conceptual

```
Fontes (T1 oficiais · T2 especializadas · T3 imprensa · T4 redes/não confirmado)
   │
   ▼
COLLECT ─▶ NORMALIZE ─▶ CLASSIFY ─▶ CLUSTER ─▶ VERIFY ─▶ SCORE ─▶ GENERATE ─▶ REVIEW ─▶ EXPORT
descoberta  normalizada              candidato  verificado         conteúdo    pronto a publicar
                                                   │
                                                   └─▶ Relatório: seleccionados / watchlist / "nada a publicar"
```

- Pipeline por etapas, cada uma um comando CLI independente e idempotente, comunicando através da base de dados.
- O **acontecimento** (`Event`) é a unidade editorial; os formatos de conteúdo derivam dele.
- **Claims** e **evidências** ligam cada afirmação importante a excertos literais das fontes.
- A IA é opcional em cada etapa e está isolada atrás de uma interface independente do fornecedor.
- Python + SQLite na primeira implementação; preparado para PostgreSQL.
- Execução manual primeiro; automação (GitHub Actions) depois, invocando os mesmos comandos.

Detalhe em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Princípios

1. Descoberta de informação **não é** confirmação de informação.
2. Alterações a direitos, valores, condições, prazos ou legislação são confirmadas em fonte oficial sempre que possível.
3. Seis níveis distintos: descoberta → normalizada → candidato editorial → acontecimento verificado → conteúdo editorial → pronto para publicação.
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

## Roadmap resumido

| Fase | Âmbito | Estado |
|------|--------|--------|
| 0 | Arquitectura e documentação | **Em curso** |
| 1 | Fundação, fontes, recolha e normalização (manual) | Planeada |
| 2 | Classificação, agrupamento, pontuação e relatório | Planeada |
| 3 | Verificação, claims e rastreabilidade | Planeada |
| 4 | Geração de formatos, revisão humana e exportação | Planeada |
| 5 | Automação com execuções agendadas | Planeada |
| 6 | Evolução (PostgreSQL, novos formatos, publicação, redes sociais) | A avaliar |

Detalhe e decisões pendentes em [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Visão geral, princípios, componentes, níveis de maturidade, decisões arquitecturais. |
| [TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) | Stack, estrutura de código, CLI, interfaces internas, requisitos não funcionais. |
| [DATA_MODEL.md](docs/DATA_MODEL.md) | Entidades, campos, estados e enumerações. |
| [CONTENT_PIPELINE.md](docs/CONTENT_PIPELINE.md) | Etapas do pipeline, regras de verificação, formatos e relatório. |
| [SOURCES.md](docs/SOURCES.md) | Hierarquia de fontes, registo, regras de utilização e lista candidata. |
| [SCORING.md](docs/SCORING.md) | Dimensões, pesos, penalizações, limiares e decisão. |
| [AI_RULES.md](docs/AI_RULES.md) | Utilização permitida de IA, grounding, validações e independência de fornecedor. |
| [SECURITY.md](docs/SECURITY.md) | Segredos, recolha responsável, prompt injection, RGPD, integridade editorial. |
| [ROADMAP.md](docs/ROADMAP.md) | Fases, critérios de saída e decisões pendentes. |
