# Validação de fontes — economia_financas

> Rascunho gerado em 2026-10-11 (DEC-061) com observações técnicas dos runs automáticos. As verificações V1–V5 continuam **pendentes**: só uma pessoa as pode registar (`checked_by`), seguindo [README.md](README.md). Este ficheiro é só acrescentado.

## Identificação

- `source_id`: economia_financas
- Nome: Economia e Finanças
- Tier registado: T3
- `endpoint_id` abrangidos: economiafinancas-rss

## Observações técnicas automáticas (não substituem V1–V5)

- `economiafinancas-rss` (ACTIVE) — https://economiafinancas.com/feed/ — recolha sem falhas no run de 2026-10-11 10:12 UTC

## Registos de verificação

| Verificação | Âmbito | Estado | A preencher |
|---|---|---|---|
| V1 Existência da fonte | fonte | pendente | `checked_at`, `checked_by`, `method`, `observation`, `result` |
| V2 Existência do endpoint | cada endpoint | pendente | idem |
| V3 Validade técnica | cada endpoint | pendente (ver observações acima) | idem |
| V4 Adequação editorial | fonte | pendente | idem |
| V5 Autorização de recolha (termos, robots.txt) | cada endpoint | pendente | idem |

## Acrescento de 2026-10-12 (DEC-074) — `economiafinancas-rss` passa a INACTIVE

### Observações técnicas automáticas

Desde o run das 15:19 UTC, `https://economiafinancas.com/feed/` responde 302 para `https://follow.it/economiafinancas/rss` (em seis pedidos de teste às 19:3x UTC, com e sem `Accept` de feed, todos 302). O feed do follow.it (cópia enviada por Nuno em 2026-10-12) declara-se como `follow.it/economia-e-financas/rss` (indício de um segundo redirect) e os links dos itens são de rastreio (`api.follow.it/track-rss-story-click/...`), não os URLs do site: não serve como fonte. O site não tem news sitemap (`/news-sitemap.xml` → 404); o `post-sitemap.xml` do Yoast não tem `news:news`. O endpoint passa a `INACTIVE` por decisão do pull request; alternativa a avaliar na fase 4 (API JSON do WordPress, `json_api`).
