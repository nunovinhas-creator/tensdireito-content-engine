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

O score é uma heurística lexical de priorização, não uma avaliação jurídica. Os rascunhos começam como `unverified`; o texto conserva o excerto original e assinala que está por validar. A aprovação exige revisão humana e um nível de verificação explícito.

## Revisão e exportação

```bash
uv run tde drafts list
uv run tde drafts approve 1 --verification-status verified_official
uv run tde drafts export --verification-status verified_official
uv run tde drafts sync-issues
```

A exportação produz texto para cópia manual. Não envia mensagens para o WhatsApp. A sincronização GitHub cria issues para rascunhos ainda não verificados, usando o URL da fonte como chave de idempotência.

## GitHub Actions e persistência

O workflow `.github/workflows/daily.yml` é **manual (`workflow_dispatch`)**, não agendado. Os runners hospedados são efémeros e o SQLite local não é partilhado nem preservado entre execuções. Cada execução manual preserva o relatório como artefacto por 14 dias e pode sincronizar rascunhos para GitHub Issues. Não activar agendamento recorrente até estar implementada e aprovada uma solução de persistência durável/partilhada, conforme DEC-013 e D8.

## Documentação

- `docs/ARCHITECTURE.md` — arquitectura e limites actuais
- `docs/DAILY_PIPELINE.md` — execução, janela temporal e workflow
- `docs/SOURCES.md` — modelo, hierarquia e validação das fontes
- `docs/EDITORIAL_POLICY.md` — salvaguardas editoriais
- `docs/SCORING.md` — pontuação de prioridade
- `docs/SECURITY.md` — segurança e recolha responsável
- `docs/ROADMAP.md` e `docs/DECISION_LOG.md` — trabalho futuro e decisões
