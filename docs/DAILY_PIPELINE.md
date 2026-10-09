# Pipeline diário

## Executar

```bash
uv run tde sources validate
uv run tde daily
```

O ciclo de vida é **Recolha → Normalização → Scoring → Rascunhos (SQLite) → Revisão Humana → Exportação/Publicação**. `daily` inicializa e migra a base local se necessário, sincroniza `config/sources.yaml`, recolhe endpoints RSS `ACTIVE`, normaliza os `raw_item` persistidos, elimina duplicados exatos por texto normalizado, calcula um score lexical determinístico e escreve `data/reports/daily/AAAA-MM-DD.txt`. Cria ainda rascunhos WhatsApp pendentes para representantes não duplicados com score ≥ 65, fonte em estado `VALIDATED` e URL HTTPS; a fila fica na tabela `whatsapp_draft`. O score só prioriza texto e não confirma factos. Cada rascunho começa explicitamente com verificação `unverified`; a aprovação requer revisão humana e uma declaração `verified_editorial` ou `verified_official`. O texto apresenta o excerto original da fonte, assinalado como por validar, sem o reescrever.

Os comandos de revisão são `tde --db data/tde.sqlite3 drafts list` e `tde --db data/tde.sqlite3 drafts approve <id> --verification-status verified_editorial` (ou `verified_official`). Os aprovados verificados podem ser exportados em texto pronto a copiar para WhatsApp (predefinição), JSON ou Markdown:

```bash
uv run tde --db data/tde.sqlite3 drafts export
uv run tde --db data/tde.sqlite3 drafts export \
  --verification-status verified_official --format markdown
uv run tde --db data/tde.sqlite3 drafts export --format json --mark-published
```

Sem `--verification-status`, a exportação inclui os dois níveis de verificação. A exportação normal não altera estados; `--mark-published` marca atomicamente como `published` apenas os rascunhos exportados, para os excluir de futuras exportações. Esta opção deve ser usada depois da publicação manual — o CLI não envia mensagens para o WhatsApp. O envio continua manual/externo.

As falhas de uma fonte não impedem o processamento das restantes; o comando termina com código `2` em sucesso parcial.

`sources validate` é uma verificação local opcional que confirma a configuração antes da recolha; `daily` volta a validá-la ao carregar o YAML. Exemplos com caminhos alternativos (as opções globais `--config` e `--db` ficam antes de `daily`):

```bash
uv run tde --config config --db data/tensdireito.sqlite3 daily \
  --date 2026-10-09 --report-dir data/reports/daily
```

`--date AAAA-MM-DD` escolhe explicitamente o dia; por omissão usa a data atual em `Europe/Lisbon`. `--config DIR`, `--db PATH` e `--report-dir DIR` alteram os caminhos existentes. O contrato dos códigos de saída é: `0` quando todas as fontes consultadas terminam sem falha (incluindo zero fontes `ACTIVE`); `2` quando há falhas parciais; e `1` em erro geral ou quando todas as fontes falham. Erros de configuração, ligação, migração ou escrita do relatório são falhas explícitas, nunca sucesso por omissão.

## Janela e repetição

O dia é avaliado em `Europe/Lisbon`. Se NORMALIZE reconhecer `published_at`, essa data determina a janela. Caso contrário, `fetched_at` determina se o item entra no dia; o relatório escreve `Data: não indicada`, sem transformar a recolha numa data de publicação. O estado atual de NORMALIZE interpreta timestamps ISO 8601 com fuso explícito; o `pubDate` RFC 822 habitual em RSS e outros formatos permanecem desconhecidos até à decisão D13.

A identidade já persistida por COLLECT impede reinserções do mesmo endpoint, URL e hash bruto. NORMALIZE não cria documentos duplicados para os itens já processados. A deduplicação existente por texto normalizado também remove repetições do mesmo feed ou entre fontes na seleção. A ordenação é por data efetiva decrescente e, em empate, fonte, título e URL. Executar novamente no mesmo dia reescreve o mesmo relatório determinístico, sem duplicar registos. Esta idempotência tem de ser preservada quando a persistência durável for implementada (D8).

Não há classificação semântica nesta entrega. “Selecionadas” significa que os itens normalizados pertencem à janela diária e não são duplicados exatos; não significa relevância editorial confirmada.

## Fontes configuradas

`config/sources.yaml` contém o Diário da República como fonte T1 validada e o feed RSS da 1.ª Série como endpoint `ACTIVE`. O respetivo registo de verificações está em [source_validation/dre.md](source_validation/dre.md). Não foram acrescentadas outras fontes sem validação dos respetivos endpoints.

Verificações exploratórias feitas em 09/10/2026:

| Candidato | Observação técnica | Política e estado |
|---|---|---|
| Diário da República — `https://files.diariodarepublica.pt/rss/serie1-html.xml` | Feed RSS oficial da 1.ª Série, confirmado na página de notificações do Diário da República; detalhes das verificações V1–V5 em [source_validation/dre.md](source_validation/dre.md). | Fonte T1 `VALIDATED` e endpoint `ACTIVE` em `config/sources.yaml`. |
| Observador — `https://observador.pt/feed/` | O próprio site declara o link RSS. HTTPS, sem redirect, HTTP 200, `text/xml`; RSS 2.0, 51 itens em duas recolhas e metadados estáveis. Os itens contêm título, URL, `pubDate` e descrição. `robots.txt` não proíbe o feed. | Os termos publicados dizem que o conteúdo não pode ser utilizado sem consentimento. Não foi encontrada autorização explícita para esta recolha e reutilização; não ativado. |
| ECO — `https://eco.sapo.pt/feed/` | HTTPS e parser RSS 2.0 aceitam o feed; uma consulta devolveu 22 itens com título, URL, `pubDate` e descrição. O `robots.txt` permite o caminho `/feed/`. | O site não declarou esse feed no HTML consultado e não foi confirmada autorização aplicável. Não ativado. |
| Segurança Social, IEFP, Portal do Governo e Assembleia da República | As páginas iniciais consultadas não declararam RSS/Atom. Os endpoints adivinhados para Segurança Social e Governo não responderam como feeds RSS válidos. | Não foi encontrado endpoint para validar ou ativar; nenhuma URL foi adicionada por suposição. |

Os testes ponta a ponta usam `tests/fixtures/rss/valid.xml` e transporte HTTP falso, sem depender de rede ou de fontes reais.

## Execução diária automatizada

O workflow [.github/workflows/daily.yml](../.github/workflows/daily.yml) executa `uv run tde daily` todos os dias às 06:00 UTC e também pode ser iniciado manualmente. O CI interpreta rigorosamente os códigos de saída do CLI: `0` termina com sucesso; `1` falha o job; `2` acrescenta um aviso ao resumo do job sem o falhar, preservando o resultado parcial; qualquer outro código falha o passo. A implementação de D8 deve manter este contrato: indisponibilidade da base, migração ou falha ao persistir o relatório não pode ser mascarada como sucesso.

O workflow usa um runner efémero: a base SQLite e os ficheiros do relatório não são preservados entre execuções. Assim, o agendamento invoca o pipeline, mas não fornece persistência durável nem partilha do estado e dos relatórios com a revisão editorial. A proposta D8 (DEC-047) de PostgreSQL gerido + S3/R2 está **Em Avaliação / Pendente de Aprovação**; não está implementada e não fecha D8. Ver também a proposta e as salvaguardas de idempotência em [ARCHITECTURE.md](ARCHITECTURE.md#7-proposta-de-persistência-durável-d8).
