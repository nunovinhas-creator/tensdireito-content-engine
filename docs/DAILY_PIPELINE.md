# Pipeline diário

## Executar

```bash
uv run tde daily
```

O comando inicializa e migra a base de dados local se necessário, sincroniza `config/sources.yaml`, recolhe endpoints RSS `ACTIVE`, normaliza os `raw_item` persistidos com NORMALIZE existente, elimina duplicados exatos por texto normalizado e escreve `data/reports/daily/AAAA-MM-DD.txt`. As falhas de uma fonte não impedem o processamento das restantes; o comando termina com código `2` em sucesso parcial.

Opções: `--date AAAA-MM-DD` escolhe explicitamente o dia; por omissão usa a data atual em `Europe/Lisbon`. `--config DIR`, `--db PATH` e `--report-dir DIR` alteram os caminhos existentes.

## Janela e repetição

O dia é avaliado em `Europe/Lisbon`. Se NORMALIZE reconhecer `published_at`, essa data determina a janela. Caso contrário, `fetched_at` determina se o item entra no dia; o relatório escreve `Data: não indicada`, sem transformar a recolha numa data de publicação. O estado atual de NORMALIZE interpreta timestamps ISO 8601 com fuso explícito; `pubDate` RSS noutros formatos permanece desconhecido.

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