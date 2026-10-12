# Validação de fontes — executive_digest

> Criado em 2026-10-12 (DEC-069, fase 2b) com as observações técnicas que levaram à proposta deste endpoint. As verificações V1–V5 continuam **pendentes**: só uma pessoa as pode registar (`checked_by`), seguindo [README.md](README.md). A passagem a `ACTIVE` produz efeito com o merge do pull request da fase 2b. Este ficheiro é só acrescentado.

## Identificação

- `source_id`: executive_digest
- Nome: Executive Digest
- Tier registado: T3
- `domains`: `executivedigest.sapo.pt`
- `endpoint_id` abrangidos: executivedigest-news-sitemap

## Observações técnicas automáticas (não substituem V1–V5)

- `executivedigest-news-sitemap` (ACTIVE) — https://executivedigest.sapo.pt/news-sitemap.xml — news sitemap declarado no robots.txt (linha `Sitemap:`, a par de `wp-sitemap.xml`), lido em 2026-10-12; o robots.txt só proíbe `/wp-admin/` e `/wp-login.php`. O sitemap foi lido em 2026-10-12: cerca de 180 entradas, todas com `news:publication_date` e `news:title`, das últimas 48 horas (incluía "IEFP abre hoje candidaturas a estágios profissionais").

## Registos de verificação

| Verificação | Âmbito | Estado | A preencher |
|---|---|---|---|
| V1 Existência da fonte | fonte | pendente | `checked_at`, `checked_by`, `method`, `observation`, `result` |
| V2 Existência do endpoint | cada endpoint | pendente | idem |
| V3 Validade técnica | cada endpoint | pendente (ver observações acima) | idem |
| V4 Adequação editorial | fonte | pendente | idem |
| V5 Autorização de recolha (termos, robots.txt) | cada endpoint | pendente | idem |
