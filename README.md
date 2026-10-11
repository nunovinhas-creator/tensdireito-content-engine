# TensDireito Content Engine

Motor editorial em Python para recolher informação, normalizar itens, eliminar duplicados exactos, calcular uma pontuação lexical de prioridade e preparar rascunhos WhatsApp para revisão humana. O sistema **não confirma alterações legais nem publica automaticamente**.

## Estado actual

A implementação existente cobre a fundação, fontes RSS, transporte HTTPS restrito, persistência SQLite local, normalização, pontuação básica, relatório diário, fila de rascunhos e sincronização de rascunhos não verificados com GitHub Issues. Não estão implementados o fluxo completo de `Event`/claims/evidências, verificação jurídica automática, classificação semântica, agrupamento semântico nem geração de artigos/SEO.

O registo de produção em `config/sources.yaml` contém apenas o Diário da República — 1.ª Série — porque é a fonte cujo endpoint está documentado e validado no repositório. As outras fontes observadas nos logs anteriores devolveram erros HTTP, redirects, HTML em vez de RSS ou timeouts. Não devem continuar marcadas como `ACTIVE`/`VALIDATED` sem uma nova validação documental e técnica. Ver `docs/SOURCES.md` e `docs/source_validation/dre.md`.

## Requisitos

- Python 3.12 ou superior
- [`uv`](https://docs.astral.sh/uv/)

## Instalação e testes

```bash
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run tde --help
uv run tde doctor
```

## Pipeline diário local

```bash
uv run tde sources validate
uv run tde daily
```

O pipeline inicializa/migra a base SQLite, sincroniza `config/sources.yaml`, recolhe endpoints RSS `ACTIVE`, normaliza os itens persistidos, elimina duplicados exactos e escreve `data/reports/daily/AAAA-MM-DD.txt`. Pode indicar a data e o directório do relatório:

```bash
uv run tde daily --date 2026-10-09 --report-dir data/reports/daily
```

As opções globais `--config DIR` e `--db PATH` têm de preceder `daily`. O dia é interpretado em `Europe/Lisbon`. O código de saída é `0` para sucesso, `2` para sucesso parcial e `1` para erro fatal/todas as fontes falhadas.

O score é uma heurística lexical de priorização, não uma avaliação jurídica, reforçada pelos termos de `config/apoios.yaml` (DEC-056). Só entram notícias publicadas no próprio dia (DEC-057). Os rascunhos começam como `unverified`; seguem o formato curto de DEC-053 e, quando o título refere um apoio com guia no tensdireito.com, o link aponta para o guia (DEC-058). A aprovação exige revisão humana e um nível de verificação explícito.

## Revisão e exportação

```bash
uv run tde drafts list
uv run tde drafts approve 1 --verification-status verified_official
uv run tde drafts export --verification-status verified_official
uv run tde drafts sync-issues
```

A exportação produz texto para cópia manual. Não envia mensagens para o WhatsApp. A sincronização GitHub cria issues para rascunhos ainda não verificados, usando o URL da fonte como chave de idempotência.

## GitHub Actions e persistência

O workflow `.github/workflows/daily.yml` corre três vezes por dia (08:07, 13:07 e 18:07 UTC) e pode ser iniciado manualmente (DEC-050). Executa `tde daily --summary-md "$GITHUB_STEP_SUMMARY"` (resumo por fonte na página do run), `tde drafts sync-issues` (issues com etiqueta por área, deduplicadas pelo URL da fonte em todas as issues) e `tde drafts close-stale --days 3` (fecha rascunhos antigos), e guarda o relatório como artefacto por 14 dias (DEC-058). A base SQLite passa entre execuções pelo cache do GitHub Actions e é limpa de itens com mais de 60 dias (`tde prune`); `tde llm check` regista no resumo se a IA respondeu (DEC-061). A fila operacional continuam a ser as issues.

## Documentação

- `docs/ARCHITECTURE.md` — arquitectura e limites actuais
- `docs/DAILY_PIPELINE.md` — execução, janela temporal e workflow
- `docs/SOURCES.md` — modelo, hierarquia e validação das fontes
- `docs/EDITORIAL_POLICY.md` — salvaguardas editoriais
- `docs/SCORING.md` — pontuação de prioridade
- `docs/SECURITY.md` — segurança e recolha responsável
- `docs/ROADMAP.md` e `docs/DECISION_LOG.md` — trabalho futuro e decisões
