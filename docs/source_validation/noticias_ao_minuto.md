# Validação de fontes — noticias_ao_minuto

> Criado em 2026-10-12 (DEC-069, fase 2b) com as observações técnicas que levaram à proposta deste endpoint. As verificações V1–V5 continuam **pendentes**: só uma pessoa as pode registar (`checked_by`), seguindo [README.md](README.md). A passagem a `ACTIVE` produz efeito com o merge do pull request da fase 2b. Este ficheiro é só acrescentado.

## Identificação

- `source_id`: noticias_ao_minuto
- Nome: Notícias ao Minuto
- Tier registado: T3
- `domains`: `noticiasaominuto.com`, `www.noticiasaominuto.com`
- `endpoint_id` abrangidos: noticiasaominuto-news-sitemap

## Observações técnicas automáticas (não substituem V1–V5)

- `noticiasaominuto-news-sitemap` (ACTIVE) — https://www.noticiasaominuto.com/sitemap.xml — `sitemap.xml` declarado no robots.txt, lido em 2026-10-12; é um `urlset` com etiquetas `news:news` em cada entrada e `news:publication_date` (sem `lastmod`). O robots.txt proíbe `/rss/` para `User-agent: *` (por isso não há endpoint RSS) e proíbe todo o site a uma lista de crawlers de IA nomeados; o `User-Agent` deste projecto (`tensdireito-content-engine`) não consta dessa lista, mas a V5 tem de o confirmar.

## Registos de verificação

| Verificação | Âmbito | Estado | A preencher |
|---|---|---|---|
| V1 Existência da fonte | fonte | pendente | `checked_at`, `checked_by`, `method`, `observation`, `result` |
| V2 Existência do endpoint | cada endpoint | pendente | idem |
| V3 Validade técnica | cada endpoint | pendente (ver observações acima) | idem |
| V4 Adequação editorial | fonte | pendente | idem |
| V5 Autorização de recolha (termos, robots.txt) | cada endpoint | pendente | idem |
