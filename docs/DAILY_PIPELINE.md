# Pipeline diário

## Executar

```bash
uv run tde sources validate
uv run tde daily
```

O ciclo de vida é **Recolha → Normalização → Scoring → Rascunhos (SQLite) → Revisão Humana → Exportação/Publicação**. `daily` inicializa e migra a base local se necessário, sincroniza `config/sources.yaml`, recolhe endpoints RSS `ACTIVE`, normaliza os `raw_item` persistidos, elimina duplicados exatos por texto normalizado, calcula um score lexical determinístico e escreve `data/reports/daily/AAAA-MM-DD.txt`. Cria ainda rascunhos WhatsApp pendentes para representantes não duplicados com score ≥ 65, fonte em estado `VALIDATED` e URL HTTPS; a fila fica na tabela `whatsapp_draft`. O score só prioriza texto e não confirma factos. Cada rascunho começa explicitamente com verificação `unverified`; a aprovação requer revisão humana e uma declaração `verified_editorial` ou `verified_official`. O texto usa as primeiras frases do resumo da fonte, no formato curto de DEC-053; o aviso de validação fica no corpo da issue. Só são seleccionadas notícias com data de publicação do próprio dia (DEC-057).

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

`config/sources.yaml` mantém o registo de fontes e endpoints. Os endpoints com erros persistentes no log de 09/10/2026 foram colocados em `INACTIVE` até serem descobertos e validados novamente; não se deve tentar contornar paywalls, respostas `403` ou protecções anti-bot. ACT permanece activo porque o log apenas indica timeout transitório ao consultar `robots.txt`, que deve ser reavaliado numa execução posterior.

| Endpoint | Resultado no log de 09/10/2026 | Estado aplicado |
|---|---|---|
| Assembleia da República (`ar-rss`) | HTTP 404 | `INACTIVE` |
| CNN Portugal (`cnn-rss`) | `text/html`, não um feed | `INACTIVE` |
| Diário de Notícias (`dn-rss`) | HTTP 404 | `INACTIVE` |
| Expresso (`expresso-rss`) | HTTP 403 | `INACTIVE` |
| Portal do Governo (`governo-rss`) | Redirect 307 não seguido | `INACTIVE` |
| IEFP (`iefp-rss`) | HTTP 404 | `INACTIVE` |
| JM Madeira (`jm-rss`) | Redirect 301 não seguido | `INACTIVE` |
| Jornal de Notícias (`jn-rss`) | HTTP 403 | `INACTIVE` |
| Lusa (`lusa-rss`) | `text/html`, não um feed | `INACTIVE` |
| Público (`publico-rss`) | HTTP 404 | `INACTIVE` |
| Segurança Social (`ss-rss`) | Redirect 302 não seguido | `INACTIVE` |
| ACT (`act-rss`) | Timeout ao consultar `robots.txt` | Mantido `ACTIVE` para nova tentativa; não contar como validado por este log |

Os outros endpoints que não falharam nessa execução permanecem configurados. A ausência de erro num único pedido não substitui as verificações V1–V5 nem a revisão dos termos de utilização. Para reactivar um endpoint, confirmar a URL a partir do site oficial, os termos e `robots.txt`, e testar o contrato técnico do collector. Os redirects não são seguidos pelo transporte actual por decisão de segurança (DEC-033); actualize a URL para o destino canónico apenas depois de o confirmar manualmente.

## Execução através de GitHub Actions

O workflow [.github/workflows/daily.yml](../.github/workflows/daily.yml) corre três vezes por dia (08:00, 13:00 e 18:00 UTC) e pode ser iniciado manualmente (DEC-050). Executa `tde daily --summary-md "$GITHUB_STEP_SUMMARY"` (resumo por fonte na página do run), `tde drafts sync-issues` (issues com etiqueta por área, deduplicadas pelo URL da fonte em todas as issues) e `tde drafts close-stale --days 3` (fecha rascunhos antigos), e guarda o relatório como artefacto por 14 dias (DEC-058). O runner é efémero: o SQLite não persiste entre execuções e a fila operacional são as issues; a persistência durável continua pendente em D8.

### Revisão através de GitHub Issues

```text
tde daily
  └─ cria rascunhos elegíveis na fila SQLite (pending / unverified)
      └─ tde drafts sync-issues
          ├─ encontra issue associada à referência da fonte → não duplica
          └─ sem referência existente → cria issue [Rascunho WhatsApp] <Título>
                label: draft-whatsapp
                corpo: texto WhatsApp + score + fonte + instruções
                └─ revisão humana → copiar para WhatsApp → publicar → fechar issue
```

O identificador estável é o URL da fonte original, incluído como referência oculta no corpo da issue. A sincronização consulta issues abertas e fechadas, pelo que uma issue já resolvida também impede que a mesma fonte volte a ser criada em execuções posteriores. Só são sincronizados rascunhos ainda pendentes e `unverified`; aprovação editorial continua a exigir os comandos de revisão locais e uma indicação explícita de verificação.

Fechar a issue após publicação é um registo operacional visível no GitHub, não uma atualização do estado SQLite: a base continua local e efémera no runner, e não existe neste fluxo uma aprovação automática nem histórico durável de publicação no SQLite. O workflow de fecho que faria `tde drafts approve` e `--mark-published` não está ativado por essa razão. Fechar a issue só depois de copiar e publicar manualmente o texto.

O workflow usa um runner efémero: a base SQLite e os ficheiros do relatório não são preservados entre execuções. Assim, o agendamento invoca o pipeline, mas não fornece persistência durável nem partilha do estado e dos relatórios com a revisão editorial. A proposta D8 (DEC-047) de PostgreSQL gerido + S3/R2 está **Em Avaliação / Pendente de Aprovação**; não está implementada e não fecha D8. Ver também a proposta e as salvaguardas de idempotência em [ARCHITECTURE.md](ARCHITECTURE.md#7-proposta-de-persistência-durável-d8).
