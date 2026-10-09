# Pipeline diário

## Executar

```bash
uv run tde sources validate
uv run tde daily
```

O comando inicializa e migra a base de dados local se necessário, sincroniza `config/sources.yaml`, recolhe endpoints RSS `ACTIVE`, normaliza os `raw_item` persistidos com NORMALIZE existente, elimina duplicados exatos por texto normalizado e escreve `data/reports/daily/AAAA-MM-DD.txt`. As falhas de uma fonte não impedem o processamento das restantes; o comando termina com código `2` em sucesso parcial.

`sources validate` é uma verificação local opcional que confirma a configuração antes da recolha; `daily` volta a validá-la ao carregar o YAML. Exemplos com caminhos alternativos (as opções globais `--config` e `--db` ficam antes de `daily`):

```bash
uv run tde --config config --db data/tensdireito.sqlite3 daily \
  --date 2026-10-09 --report-dir data/reports/daily
```

`--date AAAA-MM-DD` escolhe explicitamente o dia; por omissão usa a data atual em `Europe/Lisbon`. `--config DIR`, `--db PATH` e `--report-dir DIR` alteram os caminhos existentes. O código de saída é `0` quando todas as fontes consultadas terminam sem falha (incluindo zero fontes `ACTIVE`), `2` quando há falhas parciais e `1` em erro geral ou quando todas as fontes falham.

## Janela e repetição

O dia é avaliado em `Europe/Lisbon`. Se NORMALIZE reconhecer `published_at`, essa data determina a janela. Caso contrário, `fetched_at` determina se o item entra no dia; o relatório escreve `Data: não indicada`, sem transformar a recolha numa data de publicação. O estado atual de NORMALIZE interpreta timestamps ISO 8601 com fuso explícito; o `pubDate` RFC 822 habitual em RSS e outros formatos permanecem desconhecidos até à decisão D13.

A identidade já persistida por COLLECT impede reinserções do mesmo endpoint, URL e hash bruto. A deduplicação existente por texto normalizado também remove repetições do mesmo feed ou entre fontes na seleção. A ordenação é por data efetiva decrescente e, em empate, fonte, título e URL. Executar novamente no mesmo dia reescreve o mesmo relatório sem duplicar registos.

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

O workflow [.github/workflows/daily.yml](../.github/workflows/daily.yml) executa `uv run tde daily` todos os dias às 06:00 UTC e também pode ser iniciado manualmente. O CI interpreta os códigos de saída do CLI da seguinte forma: `0` termina com sucesso; `1` falha o job; `2` acrescenta um aviso ao resumo do job sem o falhar.

O workflow usa um runner efémero: a base SQLite e os ficheiros do relatório não são preservados entre execuções. Assim, o agendamento invoca o pipeline, mas não fornece persistência durável nem partilha do estado e dos relatórios com a revisão editorial. A persistência durável e partilhada prevista em DEC-013/D8 continua a exigir uma solução própria.
