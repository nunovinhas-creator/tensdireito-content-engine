# Segurança, Privacidade e Conformidade

> Estado: **especificação**. Requisitos a cumprir desde a primeira implementação.

## 1. Segredos

- Chaves de API (fornecedores de IA, futuros canais de publicação) **apenas** em variáveis de ambiente; nunca em ficheiros versionados, logs, relatórios ou na base de dados.
- Em GitHub Actions: *repository/environment secrets*; nunca imprimir valores em logs.
- `.env` local permitido para desenvolvimento, obrigatoriamente no `.gitignore` (já coberto pelo `.gitignore` actual); fornecer `.env.example` sem valores.
- Logs de chamadas a IA não registam cabeçalhos de autenticação.

## 2. Recolha responsável

- Respeitar `robots.txt` e termos de utilização de cada fonte; validação documentada em `sources.yaml` (`validated_at`, `notes`). Só endpoints validados e `ACTIVE` são recolhidos; URLs nunca são assumidos.
- `User-Agent` identificável do projecto, com contacto.
- Rate limiting por fonte (`rate_limit_seconds`); sem pedidos paralelos à mesma fonte.
- Preferir feeds RSS/Atom e páginas públicas; não contornar paywalls, autenticação ou medidas anti-bot.
- Conteúdo de terceiros é guardado para análise e prova (evidência); os textos publicados são originais e citam a fonte — não reproduzir artigos de imprensa integralmente.

## 3. Conteúdo externo como entrada não confiável

- Todo o texto recolhido é tratado como dados, nunca como instruções.
- Nos prompts, o conteúdo externo é delimitado e o sistema instrui o modelo a ignorar instruções nele contidas.
- As saídas da IA são validadas (esquema JSON, excertos literais, validações pós-geração) — uma injecção bem-sucedida não deve conseguir alterar estados de verificação, porque estes são calculados por regras.
- HTML recolhido nunca é renderizado nem executado; apenas analisado como texto.
- Nenhum conteúdo externo é passado a shell, `eval` ou SQL sem parametrização (queries sempre parametrizadas).

## 4. Protecção de dados (RGPD)

- O âmbito do sistema é informação institucional e noticiosa, não dados pessoais.
- Não recolher nem guardar dados pessoais de autores de publicações em redes sociais para além do URL da publicação.
- Não guardar dados de leitores/utilizadores do TensDireito.com neste sistema.
- Se documentos recolhidos contiverem dados pessoais incidentais (ex.: nomes em notícias), não são extraídos para campos estruturados nem usados em prompts além do necessário.
- Política de retenção: `raw_item` e `source_document` não associados a nenhum evento são apagados após `retention_days` (inicial 90); documentos usados como evidência são mantidos para rastreabilidade.
- Envio de texto a fornecedores de IA: avaliar os termos de tratamento de dados do fornecedor escolhido antes de activar (decisão pendente).

## 5. Integridade editorial e responsabilidade

- Nenhuma publicação automática e nenhuma aprovação sem decisão humana (V1). A IA nunca é registada como revisor.
- Todas as decisões humanas e overrides ficam em `editorial_decision` (quem, quando, decisão, nota).
- O override de verificação nunca produz `VERIFIED_OFFICIAL` (ver [DECISION_LOG.md](DECISION_LOG.md), DEC-004).
- Conteúdo publicado mantém ligação às claims e fontes, permitindo responder a pedidos de correcção.
- Correcções a conteúdo já exportado geram nova versão; a anterior fica substituída (`superseded_by`), nunca apagada.

## 6. Cadeia de fornecimento (dependências)

- Dependências mínimas, com versões fixadas (lockfile) a partir da Fase 1.
- Introdução de dependências justificada em PR (ver [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md#7-registo-de-dependências)).
- Activar alertas de segurança de dependências no repositório (ex.: Dependabot) — decisão de configuração do repositório.

## 7. GitHub Actions (fases posteriores)

- Permissões mínimas no `GITHUB_TOKEN` (`contents: read` por defeito).
- Actions de terceiros fixadas por SHA.
- Workflows agendados não fazem push para branches protegidos nem publicam conteúdo.
- A base de dados de produção não é guardada no repositório git.
- Nenhum workflow agendado é activado antes da decisão sobre persistência durável e estado partilhado (D8 em [ROADMAP.md](ROADMAP.md#decisões-pendentes)); um SQLite local num runner efémero não é solução de produção.

## 8. Acesso

- Na V1, o sistema é operado por uma ou poucas pessoas localmente; sem interface exposta à internet.
- Sem autenticação na V1: a identificação do revisor (`actor`) é declarativa. É suficiente para rastreabilidade interna, não para prova de identidade; qualquer uso multi-utilizador ou remoto exige autenticação.
- Qualquer futura interface web ou API exigirá autenticação e revisão de segurança própria antes de ser exposta.
