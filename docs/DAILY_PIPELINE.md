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

`config/sources.yaml` continua vazio: não há fontes `ACTIVE`. O registo aceita fontes e endpoints no formato existente; só configurar um endpoint `ACTIVE` depois de verificar origem, formato, comportamento HTTP, `robots.txt` e autorização aplicável.

Verificações exploratórias feitas em 09/10/2026:

| Candidato | Observação técnica | Política e estado |
|---|---|---|
| Observador — `https://observador.pt/feed/` | O próprio site declara o link RSS. HTTPS, sem redirect, HTTP 200, `text/xml`; RSS 2.0, 51 itens em duas recolhas e metadados estáveis. Os itens contêm título, URL, `pubDate` e descrição. `robots.txt` não proíbe o feed. | Os termos publicados dizem que o conteúdo não pode ser utilizado sem consentimento. Não foi encontrada autorização explícita para esta recolha e reutilização; não ativado. |
| ECO — `https://eco.sapo.pt/feed/` | HTTPS e parser RSS 2.0 aceitam o feed; uma consulta devolveu 22 itens com título, URL, `pubDate` e descrição. O `robots.txt` permite o caminho `/feed/`. | O site não declarou esse feed no HTML consultado e não foi confirmada autorização aplicável. Não ativado. |
| Segurança Social, IEFP, Portal do Governo, Assembleia da República e Diário da República | As páginas iniciais consultadas não declararam RSS/Atom. Os endpoints adivinhados para Segurança Social, Governo e Diário da República não responderam como feeds RSS válidos. | Não foi encontrado endpoint para validar ou ativar; nenhuma URL foi adicionada por suposição. |

Os testes ponta a ponta usam `tests/fixtures/rss/valid.xml` e transporte HTTP falso, sem depender de rede ou de fontes reais.

## Execução diária automatizada

Não existe workflow agendado, cron ou timer configurado neste repositório. A automatização não foi implementada: a base de dados SQLite e os relatórios são ficheiros locais, sem persistência durável nem partilha com a revisão editorial. DEC-013/D8 mantém a execução agendada bloqueada até ser decidida e implementada uma persistência durável; agendar num runner efémero poderia perder o estado entre execuções. Além disso, `config/sources.yaml` está vazio, pelo que uma execução diária apenas produziria um relatório sem notícias.

Até esses bloqueios serem resolvidos, executar manualmente `uv run tde daily` numa máquina com ambiente `uv` configurado. Para automatizar mais tarde, primeiro definir o armazenamento durável e partilhado, o anfitrião persistente, o fuso e hora pretendidos, retenção e acesso aos relatórios, registos/falhas e prevenção de execuções concorrentes; depois escolher o scheduler já disponível nesse ambiente para invocar o mesmo comando CLI. Não foi adicionado um serviço ou scheduler específico ao projecto.
