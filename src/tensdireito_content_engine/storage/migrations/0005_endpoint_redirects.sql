-- 0005_endpoint_redirects — política de redirects e excepção do Bing por endpoint
-- (fase 2c; especificação das fases 2–4, §5 e §7; DEC-065, DEC-066, DEC-070).
--
-- `redirect_hosts`: lista JSON dos anfitriões exactos para onde se aceita um redirect
-- (`[]` = nenhum). `redirect_is_throttle`: 1 só para as pesquisas do Bing, onde um
-- 302/307 é limitação. Projectados do YAML por `tde sources sync`, como os restantes
-- campos do endpoint; a validação no domínio mantém-se. Sem `DEFAULT` (convenção das
-- migrações): as linhas anteriores ficam com NULL até à sincronização seguinte, e NULL
-- lê-se como "nenhum redirect" e "não é limitação" — o comportamento mais restrito.
-- Uma migração aplicada nunca é editada: qualquer alteração é uma migração nova.

ALTER TABLE source_endpoint ADD COLUMN redirect_hosts TEXT;
ALTER TABLE source_endpoint ADD COLUMN redirect_is_throttle INTEGER
    CHECK (redirect_is_throttle IN (0, 1));
