# Validação de fontes — dre

## Identificação

- `source_id`: dre
- `endpoint_id` abrangidos: dre-serie1-rss

## Registos de verificação

### dre — V1 — 2026-10-09T11:17:10+01:00

- `source_id`: dre
- `endpoint_id`: —
- `check`: V1
- `checked_at`: 2026-10-09T11:17:10+01:00
- `checked_by`: João Silva
- `method`: Confirmar a identificação da entidade e o domínio institucional através do site do Diário da República e da página oficial de notificações RSS.
- `observation`: A entidade é a Imprensa Nacional-Casa da Moeda / Diário da República. A publicação oficial Diário da República é uma fonte T1. Foram confirmados os domínios diariodarepublica.pt e files.diariodarepublica.pt.
- `result`: ok

### dre-serie1-rss — V2 — 2026-10-09T11:17:10+01:00

- `source_id`: dre
- `endpoint_id`: dre-serie1-rss
- `check`: V2
- `checked_at`: 2026-10-09T11:17:10+01:00
- `checked_by`: João Silva
- `method`: Consultar a página oficial https://diariodarepublica.pt/dr/geral/notificacoes/rss e confirmar que anuncia o feed RSS da 1.ª Série; comparar com o endpoint registado.
- `observation`: A página oficial confirma que o feed RSS da 1.ª Série é disponibilizado pelo Diário da República. O endpoint confirmado é https://files.diariodarepublica.pt/rss/serie1-html.xml.
- `result`: ok

### dre-serie1-rss — V3 — 2026-10-09T11:17:10+01:00

- `source_id`: dre
- `endpoint_id`: dre-serie1-rss
- `check`: V3
- `checked_at`: 2026-10-09T11:17:10+01:00
- `checked_by`: João Silva
- `method`: Fazer dois pedidos GET espaçados aproximadamente 2 segundos, sem seguir redirects, e verificar status, cabeçalhos, tamanho, estrutura e estabilidade face ao contrato do collector RSS.
- `observation`: Dois pedidos reais devolveram HTTP 200 directamente, sem redirect e sem Content-Encoding; Content-Type text/xml aceite pelo collector; resposta com 1516 bytes, inferior ao limite de 5 MiB; sem DOCTYPE; RSS 2.0 com title, description e links absolutos nos itens; encoding UTF-8 declarado e consistente. Os dois pedidos, espaçados aproximadamente 2 segundos, devolveram o mesmo conteúdo, itens, links e ETag.
- `result`: ok

### dre — V4 — 2026-10-09T11:17:10+01:00

- `source_id`: dre
- `endpoint_id`: —
- `check`: V4
- `checked_at`: 2026-10-09T11:17:10+01:00
- `checked_by`: João Silva
- `method`: Consultar o título, a língua e o conteúdo dos itens do feed oficial da 1.ª Série e avaliar a sua adequação ao âmbito editorial.
- `observation`: O feed intitula-se "Diário do Dia - Série I", é em português (pt_PT) e contém legislação, incluindo decretos-leis, portarias e resoluções do Conselho de Ministros. A publicação oficial é adequada como fonte T1 para acompanhar diplomas; a classificação temática de cada item continua a ser feita individualmente.
- `result`: ok

### dre-serie1-rss — V5 — 2026-10-09T11:17:10+01:00

- `source_id`: dre
- `endpoint_id`: dre-serie1-rss
- `check`: V5
- `checked_at`: 2026-10-09T11:17:10+01:00
- `checked_by`: João Silva
- `method`: Consultar o robots.txt aplicável ao feed e os termos de utilização, procurando regras relevantes para recolha automática do feed público.
- `observation`: O robots.txt permite o caminho /rss/. Nos termos consultados não foi encontrada proibição da recolha do feed público; não foi identificada proibição de recolha aplicável ao endpoint.
- `result`: ok

## Limitações

- V5 — termos de utilização — não foi encontrada uma cláusula explícita que autorize a recolha automática; a verificação regista que não foi encontrada proibição e que o robots.txt permite /rss/. Rever os termos antes de pedir a passagem do endpoint para ACTIVE.

## Passagens de estado pedidas

| Entidade | Estado anterior → estado novo | `validated_at` | `validated_by` |
|----------|-------------------------------|----------------|----------------|
| dre | CANDIDATE → VALIDATED | 2026-10-09T11:17:10+01:00 | João Silva |
| dre-serie1-rss | CANDIDATE → VALIDATED | 2026-10-09T11:17:10+01:00 | João Silva |
