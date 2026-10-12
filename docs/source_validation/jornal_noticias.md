# Validação de fontes — jornal_noticias

> Rascunho gerado em 2026-10-11 (DEC-061) com observações técnicas dos runs automáticos. As verificações V1–V5 continuam **pendentes**: só uma pessoa as pode registar (`checked_by`), seguindo [README.md](README.md). Este ficheiro é só acrescentado.

## Identificação

- `source_id`: jornal_noticias
- Nome: Jornal de Notícias
- Tier registado: T3
- `endpoint_id` abrangidos: jn-rss

## Observações técnicas automáticas (não substituem V1–V5)

- `jn-rss` (INACTIVE) — https://www.jn.pt/rss — HTTP 403

## Registos de verificação

| Verificação | Âmbito | Estado | A preencher |
|---|---|---|---|
| V1 Existência da fonte | fonte | pendente | `checked_at`, `checked_by`, `method`, `observation`, `result` |
| V2 Existência do endpoint | cada endpoint | pendente | idem |
| V3 Validade técnica | cada endpoint | pendente (ver observações acima) | idem |
| V4 Adequação editorial | fonte | pendente | idem |
| V5 Autorização de recolha (termos, robots.txt) | cada endpoint | pendente | idem |


## Acrescento de 2026-10-12 (DEC-069) — endpoint `jn-news-sitemap`

### Observações técnicas automáticas (não substituem V1–V5)

- `jn-news-sitemap` (ACTIVE) — https://www.jn.pt/feed/news/sitemap.xml — declarado no robots.txt de www.jn.pt (linha `Sitemap:`), lido em 2026-10-12. O robots.txt não proíbe `/feed/` para `User-agent: *`. A leitura do próprio sitemap a partir da sessão de trabalho falhou (erro do cliente); a primeira confirmação técnica é o run real do PR da fase 2b.
- `domains` acrescentados: `jn.pt`, `www.jn.pt` (as duas formas, para a junção de `www.` da §4.1).

### Registos de verificação do novo endpoint

| Verificação | Âmbito | Estado |
|---|---|---|
| V2 Existência do endpoint | jn-news-sitemap | pendente |
| V3 Validade técnica | jn-news-sitemap | pendente (ver observações acima) |
| V5 Autorização de recolha (termos, robots.txt) | jn-news-sitemap | pendente |

## Acrescento de 2026-10-12 — registo humano do endpoint `jn-news-sitemap`

- `endpoint_id`: jn-news-sitemap
- `checked_at`: 2026-10-12T15:32+01:00
- `checked_by`: nuno
- `method`: leitura dos runs reais do PR #72 (fase 2b) no GitHub Actions, incluindo o run 38261967714.
- `observation` (nas palavras de Nuno): «acessível no CI em 2026-10-12; 403 observado fora desse ambiente».
- Declarado por Nuno ao aprovar o merge do PR #72. Este registo não altera os anteriores; as linhas `pendente` acima ficam como histórico.

## Acrescento de 2026-10-12 (DEC-074) — `jn-news-sitemap` passa a INACTIVE

### Observações técnicas automáticas

Nos dois runs do daily no `main` depois do merge do PR #72 (15:19 e 17:48 UTC), o pedido ao sitemap teve HTTP 403; `last_success_at` continua nulo na base do `main`. O registo humano anterior («acessível no CI em 2026-10-12») mantém-se como histórico. O endpoint passa a `INACTIVE` por decisão do pull request; volta a `ACTIVE` só com nova verificação humana de que o sitemap responde ao `User-Agent` do projecto a partir do GitHub Actions.
