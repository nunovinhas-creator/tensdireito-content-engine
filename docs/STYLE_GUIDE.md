# Guia de Estilo

> Estado: **guia V1 (M1)**. Aplica-se a todo o conteúdo do TensDireito, seja escrito por pessoas, por templates ou com apoio de IA. O que se pode afirmar é definido pela [EDITORIAL_POLICY.md](EDITORIAL_POLICY.md); este guia define **como** se escreve.

## 1. Princípios

O texto do TensDireito é:

| Princípio | Na prática |
|-----------|-----------|
| **Português de Portugal** | Linguagem natural de Portugal: vocabulário, sintaxe e formatos ("receber", "pedir", "candidatura"; "telemóvel", não "celular"). Ortografia do conteúdo publicado: Acordo Ortográfico de 1990, variante europeia (secção 1.1). |
| **Claro** | Uma ideia por frase. Frases curtas. Palavras comuns. |
| **Directo** | O mais importante primeiro. Sem introduções genéricas. |
| **Acessível** | Escrito para quem não conhece a lei nem o vocabulário da Administração. Termos técnicos explicados na primeira utilização. |
| **Útil** | Cada texto responde a "o que muda", "aplica-se a mim?", "quanto/quando", "o que tenho de fazer" — dentro do que está confirmado. |
| **Rigoroso** | Valores, datas, prazos e referências legais exactamente como na fonte. |
| **Sem burocratês** | Evitar "no âmbito de", "proceder à", "nos termos do disposto". Usar "para", "fazer", "segundo a lei". |
| **Sem alarmismo** | Nada de "atenção urgente!", "vai perder tudo", pontos de exclamação em série. |
| **Sem clickbait enganador** | O título promete apenas o que o texto confirma. |
| **Proporcional à evidência** | Nenhuma frase é mais forte do que a evidência permite. |

### 1.1 Norma ortográfica e âmbito

Decisão D11 (fechada — [DECISION_LOG.md](DECISION_LOG.md), DEC-017).

**Conteúdo destinado ao público** segue:
- o **Acordo Ortográfico de 1990** (AO1990);
- na **variante portuguesa/europeia** (ex.: "atual", "ação", "direção", "objetivo", "projeto"; mantém-se "facto", "receção", "contacto", conforme a variante europeia);
- em **linguagem natural de português de Portugal**.

A regra aplica-se a: textos para WhatsApp, artigos, títulos, subtítulos, leads, metadados e textos SEO, CTAs, notas de responsabilidade e a todo o conteúdo gerado ou proposto por IA (os prompts de geração devem exigi-lo).

**Fora do âmbito da norma de publicação:**
- **Documentação técnica interna** (este repositório, incluindo este guia, especificações, configuração, comentários, relatórios internos): não está sujeita à norma editorial de publicação e pode manter a grafia actualmente utilizada. Não é necessário convertê-la.

**Excepções dentro do conteúdo publicado** (preserva-se o original):
- **Citações literais** mantêm a grafia original da fonte.
- **Excertos de legislação** apresentados como citação reproduzem exactamente o texto oficial, sem correcção ortográfica.
- **Nomes oficiais** de diplomas, entidades, documentos, programas ou obras mantêm a designação oficial, tal como publicada.

Fora destas excepções, o texto que rodeia a citação ou o nome oficial segue o AO1990.

Os exemplos de texto público entre aspas neste guia seguem o AO1990; o texto corrido do guia, sendo documentação interna, mantém a grafia actual do repositório.

## 2. Incerteza

Sempre que exista incerteza relevante, ela é **explícita** — no texto, não apenas numa nota de rodapé.

- Dizer o que está confirmado, o que não está, e o que se espera (se houver fonte para isso).
- Indicar a origem da informação não oficial: "segundo [fonte]".
- Não esconder a incerteza em formulações vagas ("poderá eventualmente vir a ser").
- Exemplo: "O Governo anunciou o aumento, mas o diploma ainda não foi publicado. Até lá, o valor em vigor continua a ser o atual."

## 3. Números, datas e referências

- Valores monetários: `1 234,56 €` (espaço como separador de milhares, vírgula decimal, símbolo depois do valor).
- Percentagens: `3,5 %`.
- Datas: por extenso, com o nome do mês em minúscula, conforme o AO1990 ("15 de março de 2027"), ou `dd/mm/aaaa`; nunca formatos ambíguos.
- Prazos: indicar sempre a data concreta, além de expressões relativas ("até 30 de junho", não só "nas próximas semanas").
- Referências legais: tal como publicadas (tipo de diploma, número, data). Na primeira menção, explicar o que é.
- Nunca arredondar ou "simplificar" um valor oficial sem dizer que é aproximado.

## 4. Fontes

- Indicar a fonte oficial sempre que exista.
- Distinguir na escrita fonte oficial ("segundo o diploma publicado em Diário da República") de fonte jornalística ("segundo o [órgão de comunicação]").
- O artigo termina com uma secção "Fontes".
- Não reproduzir textos de imprensa; resumir e citar.

## 5. Formulações por estágio e nível de verificação

O verbo acompanha o estágio legal (`legal_stage`) e o nível de verificação. Esta tabela é a referência para revisores e para as validações automáticas de linguagem.

| Situação | Usar | Nunca usar |
|----------|------|------------|
| `proposal` | "foi proposto", "está em discussão", "o projeto prevê" | "foi aprovado", "vai passar a", "já pode" |
| `announcement` | "o Governo anunciou", "está previsto", "ainda não foi publicado" | "nova lei", "novo direito", "passa a receber" |
| `approved` | "foi aprovado em [órgão]; aguarda publicação" | "está em vigor", "já pode pedir" |
| `published` | "foi publicado; entra em vigor a [data]" | "já está em vigor" (antes da data) |
| `in_force` + `VERIFIED_OFFICIAL` | "está em vigor", "tem direito se…", "pode pedir" | promessas incondicionais ("vai receber") |
| Qualquer claim `VERIFIED_EDITORIAL` | "segundo [fonte]", "de acordo com [fonte]; ainda sem confirmação oficial" | qualquer formulação de facto jurídico confirmado |
| Estimativas e previsões | "estima-se", "prevê-se", com a fonte | o valor como definitivo |

Sobre direitos condicionados: "pode ter direito se…", nunca "vai receber" quando o direito depende de condições.

## 6. Títulos

- Dizem o que mudou ou o que o leitor precisa de saber, com o verbo no estágio certo (secção 5).
- Concretos: incluem o tema e, se confirmados, o valor ou a data.
- Sem perguntas retóricas que escondem a resposta; sem "Saiba tudo", "Não vai acreditar", "URGENTE".
- Sem maiúsculas enfáticas nem pontos de exclamação.
- Orientação de extensão: curtos o suficiente para ler numa linha em telemóvel. Não é limite rígido.

Exemplos:

| Evitar | Preferir |
|--------|----------|
| "Boas notícias! Abono vai subir!" | "Governo anuncia aumento do abono de família; medida ainda não publicada" |
| "Nova lei dá mais dinheiro aos pensionistas" (com base em notícia) | "Aumento das pensões em 2027: o que já foi anunciado e o que falta confirmar" |
| "Prazo do IRS: atenção!" | "IRS: entrega da declaração termina a [data]" (data verificada) |

## 7. Subtítulos

- Acrescentam informação, não repetem o título: a quem se aplica, desde quando, ou o que falta confirmar.
- Uma frase.

## 8. Lead

- Primeiro parágrafo, até três frases.
- Responde a: o que muda (ou o que foi anunciado), quem é abrangido, e quando — com o que está confirmado.
- Se houver incerteza relevante, o lead menciona-a.

## 9. Textos para WhatsApp

Objectivo: alertar e ser útil num ecrã de telemóvel, levando a quem quiser saber mais para o artigo.

Estrutura recomendada:

1. Uma linha inicial com o essencial (o quê).
2. Quem é abrangido.
3. Valor, prazo ou data — só se confirmados.
4. O que fazer (se houver acção).
5. O que ainda não está confirmado (se aplicável).
6. Link para o artigo.

Regras:
- **Não existe limite rígido de caracteres.** A mensagem é tão curta quanto possível e tão longa quanto necessário para ser correcta e útil. A extensão nunca justifica cortar a incerteza ou as condições essenciais.
- Parágrafos curtos, separados por linha em branco; listas simples quando ajudam.
- Formatação mínima (negrito apenas para o essencial); nada de markdown complexo.
- Emojis: no máximo um ou dois, funcionais; nunca para dramatizar.
- Nunca enviar como confirmado o que está `VERIFIED_EDITORIAL`.

## 10. Artigos

Estrutura de referência (secções sem conteúdo confirmado são omitidas, não preenchidas com suposições):

1. Título e subtítulo.
2. Lead.
3. **O que muda** (ou **O que foi anunciado**).
4. **Quem tem direito / quem é abrangido.**
5. **Valores e prazos.**
6. **Como pedir / o que fazer.**
7. **O que ainda não se sabe** — obrigatório quando há claims não `VERIFIED_OFFICIAL` ou datas desconhecidas.
8. **Fontes.**
9. Data de actualização e, quando aplicável, nota de estado ("Artigo atualizado a [data] com a publicação do diploma").
10. Nota de responsabilidade, **apenas quando aplicável** (secção 13).

Parágrafos curtos; intertítulos frequentes; listas para condições e documentos.

## 11. SEO

- O título SEO e a meta description seguem as mesmas regras de rigor que o título: não prometem mais do que o artigo confirma.
- Palavras-chave: as que um cidadão usaria ("como pedir", nome comum da prestação), não jargão administrativo.
- `slug`: curto, descritivo, sem datas, salvo quando a data faz parte do assunto (ex.: um ano específico).
- Orientações de extensão (não limites rígidos): título SEO à volta de 60 caracteres e meta description à volta de 150–160, para não serem truncados nos resultados de pesquisa. Ultrapassar gera aviso, nunca bloqueio.
- Perguntas frequentes (FAQ) só com respostas suportadas por claims verificadas.
- Nunca usar keyword stuffing nem títulos SEO diferentes em substância do título editorial.

## 12. CTA (chamada à acção)

- Orientado para a utilidade: "Confirme se tem direito", "Veja como pedir", "Leia o artigo completo", "Consulte o diploma".
- Quando existe um serviço oficial para agir, o CTA indica-o pelo nome (o link concreto vem da fonte verificada, nunca inventado).
- Sem urgência falsa ("Garanta já!", "Últimas horas!") — a urgência só aparece se houver prazo verificado, e é dita com a data.
- Sem CTA de acção quando a medida ainda não está em vigor; nesse caso, "Acompanhe" ou "Vamos atualizar quando for publicado".

## 13. Nota de responsabilidade

A nota de responsabilidade é **proporcional ao risco**. **Não é obrigatória em todos os conteúdos** e não é acrescentada automaticamente a todos os posts.

### 13.1 Quando usar

Usa-se quando o conteúdo:
- pode induzir uma **decisão jurídica** (ex.: contestar uma decisão, fazer valer ou renunciar a um direito);
- pode induzir uma **decisão financeira relevante** (ex.: opções fiscais, crédito, reforma antecipada);
- pode levar o leitor a tomar uma **decisão administrativa importante** (ex.: pedir ou cancelar uma prestação, aceitar condições, cumprir ou deixar passar um prazo com consequências);
- envolve **interpretação normativa particularmente sensível** (ex.: regras ambíguas, casos-limite de elegibilidade, regimes transitórios).

Não se usa, em regra, em conteúdos meramente informativos de baixo risco (ex.: calendário de pagamentos, lembrete de um prazo simples, explicação geral de uma medida sem margem de interpretação).

### 13.2 Quem decide

- A pessoa que revê decide se a nota é necessária, segundo os critérios de 13.1.
- A geração (incluindo por IA) pode **propor** a nota quando identifica um destes critérios; a proposta não é obrigatória nem bloqueia a aprovação.
- Não existe validação automática que exija a nota.

### 13.3 Forma

- Curta (uma ou duas frases), clara, no fim do conteúdo (no WhatsApp, só quando o risco o justifica e em versão mínima).
- Não deve sugerir que o TensDireito presta ou substitui aconselhamento jurídico profissional — deve dizer o contrário, sem tom defensivo.
- Remete para quem pode avaliar o caso concreto.

Textos de referência V1 (AO1990), adaptáveis ao caso:

> "Este conteúdo explica as regras gerais e não substitui aconselhamento jurídico profissional. Para avaliar o seu caso, contacte os serviços competentes ou um profissional qualificado."

> Versão curta (WhatsApp): "Informação geral; confirme o seu caso junto dos serviços competentes."

Em nenhum caso se dá aconselhamento jurídico individual.

## 14. Checklist do revisor (estilo)

- [ ] Título e lead dizem o essencial, no estágio legal certo.
- [ ] Nenhuma frase é mais forte do que a evidência (secção 5).
- [ ] A incerteza relevante está explícita no texto.
- [ ] Valores, datas e referências estão exactamente como nas fontes.
- [ ] Sem burocratês, alarmismo ou clickbait.
- [ ] Fontes indicadas; fonte oficial citada quando existe.
- [ ] CTA útil e sem urgência falsa.
- [ ] Conteúdo público em AO1990 (variante europeia), com citações, excertos legais e nomes oficiais preservados.
- [ ] Nota de responsabilidade incluída se, e só se, os critérios da secção 13.1 se aplicam.
