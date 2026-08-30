# GitPolítica — MVP

Um "GitHub da política brasileira": cada político monitorado é um arquivo,
cada notícia sobre ele vira um commit real num repositório Git.

## Como rodar

```bash
# 0. (opcional, mas recomendado) sincronizar deputados + senadores com as
#    APIs reais da Câmara e do Senado, em vez de usar só a lista manual
python3 sync_politicians.py            # produção: ~513 deputados + ~81 senadores(as)
python3 sync_politicians.py --sample   # offline, usa os arquivos de amostra

# 1. Modo teste (offline, usa sample_feed.xml, não precisa de internet)
python3 main.py --sample

# 2. Modo produção (busca de verdade os RSS configurados em config.py)
python3 main.py
```

### Como funciona a lista de políticos agora

Ver a seção "Remoção do MANUAL_POLITICIANS" mais abaixo — hoje
`config.py` mescla só Câmara, Senado e TSE (sem lista manual
embutida no código).

Isso vai:
1. Criar (ou reaproveitar) o repositório Git em `data/repo/`
2. Ler as notícias das fontes RSS
3. Identificar quais políticos monitorados (config.py) são citados
4. Criar um commit real por notícia relevante, no arquivo `<slug>.md` do político
5. Gerar o site estático em `data/site/` (abra `data/site/index.html` no navegador)

## Explorar o repositório Git gerado como um repo de verdade

Cada político fica em `<UF>/<slug>.md` (ex.: `SP/arthur-lira.md`), não
solto na raiz — necessário na escala do TSE (ver seção "Organização em
subpastas por UF" abaixo).

```bash
cd data/repo
git log --oneline                        # todos os commits
git log --oneline -- SP/arthur-lira.md   # só os commits sobre um político
git show <hash>                          # ver o diff de um commit específico
```

## Organização em subpastas por UF

**Problema real encontrado em produção**: com o dataset do TSE, o
repositório de dados chegou a quase 20 mil arquivos `.md`, todos soltos
na raiz — impossível de navegar pela interface do GitHub.

**Correção**: cada político agora fica em `<UF>/<slug>.md` (`SP/`,
`RJ/`, ..., `nacional/` para quem não tem UF — Presidente, ministros
do STF). Isso é feito por `text_utils.extract_uf()`, que lê a UF do
campo `role` do político, e `repo_writer.get_politician_relative_path()`,
usada em todo lugar que lê/escreve arquivos de político
(`ensure_repo()`, `commit_news()`, `get_log()`, `git_events.py`).

### Se você já tem um repositório de dados no formato antigo (achatado)

Atualizar o código sozinho **não move** os arquivos que já existem —
`ensure_repo()` só cria arquivos que ainda não existem no caminho
*novo*, então sem migração você acabaria com arquivos duplicados (a
versão antiga solta na raiz + uma versão nova vazia na subpasta).

Rode `migrate_to_uf_folders.py` **uma vez**, direto no seu repositório
de dados real, antes de rodar o pipeline com o código novo:

```bash
cd data/repo   # ou onde estiver seu repositório de dados
python3 ../../migrate_to_uf_folders.py . --dry-run   # confira o plano primeiro
python3 ../../migrate_to_uf_folders.py .             # migra de verdade
git push
```

O script usa `git mv` (preserva o histórico de cada arquivo — testado
com `git log --follow`, confirma que o log de antes da migração
continua acessível) e faz **um único commit** no final, não um por
arquivo. Arquivos cujo slug não existe mais na lista atual de
políticos vão para `_nao_reconhecidos/`, para revisão manual, em vez
de serem descartados.

Testado com 3.000 arquivos sintéticos: ~9 segundos — extrapolando
linearmente, um repositório com ~20 mil arquivos deve levar em torno
de 1 minuto.

## Como funciona a identificação de políticos nas notícias (NER)

`matcher.py` combina duas camadas, sem precisar de nenhuma dependência
externa:

1. **Exata**: casa o texto contra os aliases cadastrados em `config.py`
   (rápida, zero falso positivo, mas só pega variações já previstas).
2. **Fuzzy**: extrai candidatos a nome próprio do texto (sequências de
   palavras capitalizadas, com conectores como "de"/"da"/"dos") e casa
   cada candidato contra os nomes/aliases conhecidos por similaridade
   de string (após remover acentos). Isso pega erros de digitação,
   nomes sem acento e pequenas variações — por exemplo, "Artur Lira",
   "Tarcisio Freitas" (sem "de" e sem acento) e "Bia Kikis" (typo) são
   todos reconhecidos corretamente, enquanto frases como "Congresso
   Nacional", "Governo Federal" ou "A Silva Construções" continuam
   **não** casando com ninguém (testado em `matcher.py`, rode
   `python3 matcher.py` para ver os casos de teste, incluindo os de
   falso positivo).

Existe ainda um terceiro backend opcional, **spaCy** (`ner_spacy.py`),
para quando você tiver internet disponível:

```bash
pip install spacy
python -m spacy download pt_core_news_lg
python3 main.py --backend spacy
```

Esse backend usa um modelo de linguagem de verdade para reconhecer
entidades do tipo PESSOA, o que traz uma vantagem que o matcher por
alias/fuzzy não tem: ele consegue apontar **pessoas mencionadas nas
notícias que não batem com ninguém da lista monitorada** — candidatos
a novos políticos para adicionar em `config.py`, permitindo que a base
cresça sozinha com o tempo (veja `resolve_entities()` em
`ner_spacy.py`, que retorna os nomes não reconhecidos separadamente).
Se o spaCy não estiver instalado, `main.py --backend spacy` avisa e
cai de volta automaticamente pro matcher padrão, sem quebrar o
pipeline.

⚠️ O backend spaCy não pôde ser executado no ambiente onde este
projeto foi gerado (sem acesso à internet para instalar). O código
segue a documentação oficial e deve funcionar normalmente no seu
ambiente, mas rode os testes em `ner_spacy.py` antes de confiar nele
em produção.

## Fontes RSS reais confirmadas

As duas fontes em `config.py` foram testadas ao vivo nesta sessão — o XML
foi buscado de verdade e contém notícias reais e recentes sobre a Câmara,
o Senado e o Executivo:

- **Agência Brasil - Política** (`agenciabrasil.ebc.com.br`) — agência
  pública federal (EBC), cobertura ampla de Executivo, Legislativo e
  Judiciário.
- **Agência Câmara - Política** (`camara.leg.br`) — cobertura oficial da
  Câmara, incluindo com frequência menções a decisões do Senado e do STF.

**Não confirmadas nesta sessão** (o ambiente que gerou este projeto não
tem acesso à internet para testar; o G1 e a Folha bloquearam o acesso
direto da ferramenta de busca usada aqui): os padrões de URL conhecidos
do G1 (`g1.globo.com/dynamo/politica/rss2.xml`) e da Folha
(`feeds.folha.uol.com.br/emcimadahora/rss091.xml`, que é geral, não
só política) estão comentados em `config.py` — teste antes de usar em
produção. Não foi encontrada uma URL de RSS atual para o Congresso em
Foco.

### Desambiguação de sobrenomes por contexto (resolvido)

Uma versão anterior deste projeto tinha uma limitação real, encontrada
ao testar contra manchetes de verdade: "Hugo Motta afirma que nova lei
fortalece..." era identificada corretamente, mas "**Motta** critica
novas tarifas dos EUA" (só o sobrenome) não era, porque o único alias
gerado pela API da Câmara era o nome completo.

Agora `camara_api.py` e `senado_api.py` adicionam automaticamente o
sobrenome como um alias extra para cada político sincronizado. Isso
por si só reintroduziria o problema clássico de falso positivo com
sobrenomes ambíguos — por exemplo, "Bolsonaro" corresponde tanto a
**Jair Bolsonaro** (ex-presidente) quanto a **Flávio Bolsonaro**
(senador pelo RJ), ambos monitorados.

A solução é `disambiguation.py`: quando uma menção (exata ou fuzzy)
casa com mais de um político — porque compartilham um alias, como um
sobrenome —, o sistema olha para o texto ao redor da menção em busca
de pistas de cargo ("senador", "ex-presidente", "ministro"...) e UF.
Testado com o caso real Bolsonaro/Bolsonaro:

```
"O ex-presidente Bolsonaro comentou o julgamento"  -> jair-bolsonaro
"O senador Bolsonaro criticou a proposta"          -> flavio-bolsonaro
"Bolsonaro se reuniu com aliados nesta tarde"      -> []  (sem pista, não arrisca)
```

Sem pista suficiente (ou com pistas empatadas entre os candidatos), a
menção é descartada em vez de adivinhada — o princípio geral do
projeto é sempre preferir precisão a cobertura. Rode
`python3 disambiguation.py` para ver mais exemplos.

## Resumo automático de commit message via LLM

Por padrão, a "commit message" de cada notícia é o título cru vindo do
RSS. Com `python3 main.py --summarize`, cada commit message passa a ser
gerada por um LLM (API da Anthropic) a partir do título + resumo da
notícia — mais parecida com o estilo de uma mensagem de commit real:
curta, no presente, focada no fato, sem clickbait.

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sua-chave-aqui"
python3 main.py --summarize
```

Exemplo do que muda:
- Sem `--summarize`: `"Hugo Motta afirma que nova lei fortalece atuação do STJ em recursos especiais"` (título cru, às vezes longo)
- Com `--summarize`: algo como `"sanciona lei que regulamenta filtro de relevância no STJ"` (mais parecido com uma mensagem de commit real)

Assim como o backend spaCy, este módulo (`summarizer.py`) não pôde ser
testado de ponta a ponta no ambiente onde este projeto foi gerado — sem
internet nem API key disponíveis aqui. O que **foi** testado e
confirmado funcionando é o **fallback**: se o pacote `anthropic` não
estiver instalado, a `ANTHROPIC_API_KEY` não estiver configurada, ou a
chamada falhar por qualquer motivo, o pipeline avisa no terminal e usa
automaticamente o título original — o comando nunca quebra por causa
disso. Rode `python3 summarizer.py` no seu ambiente (com SDK + API key
configurados) para validar a geração de verdade antes de confiar nela
em produção.

## Troca de partido (merge real) e marcos formais (tags)

Além do commit simples que cada notícia gera, dois tipos de evento têm
tratamento especial em `git_events.py`, usando mecanismos de verdade do
Git — não é só uma metáfora na mensagem do commit:

**Troca de partido → `git merge --no-ff` de verdade.** Cria uma branch,
registra a mudança nela (atualiza o campo "Partido" no arquivo do
político + adiciona uma entrada no histórico), e faz merge de volta
pra branch principal. O resultado é um commit de merge real, com dois
pais no grafo do Git — testado e confirmado:

```
*   ba1ca84 merge: Arthur Lira migra de PP para PARTIDO-TESTE
|\
| * be96468 chore: atualiza partido de Arthur Lira para PARTIDO-TESTE
|/
* 59e2a82 notícia: ...
```

**Marco formal (posse, cassação, condenação, eleição...) → tag anotada.**
Cria um commit dedicado ao evento e aplica uma tag anotada (`git tag -a`)
apontando pra ele — testado e confirmado com `git show <tag>`.

### Por que isso não roda automaticamente sobre as notícias do RSS

Decidir "esta notícia é uma troca de partido, de X pra Y" ou "esta
notícia é uma cassação" a partir de texto livre é um problema de
classificação bem mais difícil do que reconhecer que um político foi
citado (que é o que `matcher.py` faz). Errar aqui tem um custo alto:
reescreveria incorretamente um fato central sobre o político na "fonte
de verdade" do repositório.

Por isso, `record_event.py` oferece uma interface de linha de comando
para uso **manual e curado** — você (ou um humano revisando uma
sugestão) confirma os detalhes antes de qualquer coisa ser commitada:

```bash
# Troca de partido
python3 record_event.py partido \
    --slug arthur-lira \
    --de PP --para PSD \
    --manchete "Anuncia filiação ao PSD em coletiva de imprensa" \
    --fonte "Agência Câmara - Política" \
    --url "https://exemplo.com/noticia/123"

# Marco formal
python3 record_event.py marco \
    --slug arthur-lira \
    --tag "v2027.01-posse" \
    --tag-mensagem "Toma posse para novo mandato" \
    --manchete "Arthur Lira toma posse como deputado federal" \
    --fonte "Agência Câmara - Política" \
    --url "https://exemplo.com/noticia/456"
```

Ambos os comandos pedem confirmação (`[s/N]`) antes de escrever
qualquer coisa no repositório — testei o fluxo de cancelamento também,
e confirmei que nada é commitado se a resposta não for "s".

Uma evolução futura natural é usar um LLM para **sugerir** esses
comandos a partir de uma notícia (extrair político, partido antigo,
partido novo), mas sempre deixando a confirmação final com um humano
antes do commit — nunca automatizando esse passo sozinho.

## Agendamento e deploy (o "GitHub da política" publicado de verdade)

Até aqui, tudo rodou contra um repositório Git local descartável
(`data/repo/`, recriado a cada teste). Para publicar de verdade, a
peça que muda é: **`data/repo` deixa de ser local e passa a ser um
repositório GitHub de verdade**, clonado a cada execução do pipeline,
atualizado, e enviado (`git push`) de volta — assim o histórico de
commits se acumula publicamente ao longo do tempo, navegável como
qualquer repositório no GitHub.

### Arquitetura recomendada: dois repositórios

1. **Repositório de código** (este projeto) — contém os scripts.
   Ele é quem roda o workflow agendado.
2. **Repositório de dados** (`gitpolitica-data`, por exemplo) — começa
   vazio. É nele que os commits de notícias, os merges de troca de
   partido e as tags de marcos formais se acumulam. Esse é o
   repositório que as pessoas de fato visitam para "navegar pela
   história" de um político.

### Configuração (GitHub Actions — `.github/workflows/update.yml`)

O workflow já está neste projeto, pronto pra usar. Passos de setup:

1. Crie um repositório novo no GitHub (pode ficar vazio) para os
   dados — ex.: `gitpolitica-data`.
2. Gere um **fine-grained personal access token** com permissão de
   leitura/escrita de conteúdo (Contents: Read and write) restrita a
   esse repositório de dados.
3. No repositório de código, vá em *Settings → Secrets and variables →
   Actions* e crie um secret chamado `DATA_REPO_TOKEN` com esse token.
4. Edite `.github/workflows/update.yml` e troque
   `SEU-USUARIO/gitpolitica-data` pelo caminho real do seu repositório
   de dados.
5. Em *Settings → Pages* do repositório de código, configure a origem
   como a branch `gh-pages` (o workflow já publica o site lá
   automaticamente via `peaceiris/actions-gh-pages`).
6. Rode o workflow manualmente uma vez (aba *Actions* → *Atualiza
   GitPolítica* → *Run workflow*) pra validar a configuração antes de
   esperar pelo agendamento.

O workflow tem dois cron triggers: a cada 30 minutos ele busca
notícias novas e commita; uma vez por dia (03:00 UTC) ele também
resincroniza a lista de deputados/senadores (não faz sentido rodar
isso a cada 30 min, já que muda raramente e cada sync faz dezenas de
chamadas às APIs da Câmara/Senado).

⚠️ Este workflow não pôde ser executado de ponta a ponta no ambiente
onde este projeto foi gerado — não há como testar um `git push` real
sem uma conta/repositório GitHub de verdade e acesso à internet aqui.
O que **foi** validado nesta sessão: a correção em `ensure_repo()` que
garante que a identidade do commit (`user.name`/`user.email`) seja
sempre reconfigurada mesmo quando o repositório já existe (o caso de
um `actions/checkout` — antes dessa correção, o pipeline quebraria na
segunda execução do workflow em diante, já que o `.git` já existiria e
a configuração de identidade seria pulada). Teste o workflow completo
no seu ambiente antes de confiar nele para rodar sem supervisão.

### Alternativa mais simples: cron num servidor próprio

Se você preferir não usar GitHub Actions (ou já tem um servidor
rodando), a mesma ideia funciona com um cron comum — só que aí
`data/repo` pode continuar sendo local, sem precisar do padrão de dois
repositórios:

```bash
# crontab -e
*/30 * * * * cd /caminho/para/gitpolitica && /usr/bin/python3 main.py >> logs/pipeline.log 2>&1
0 3 * * *    cd /caminho/para/gitpolitica && /usr/bin/python3 sync_politicians.py >> logs/sync.log 2>&1
```

Nesse caso, servir `data/site/` publicamente é só apontar um
servidor de arquivos estáticos (nginx, Caddy, `python3 -m http.server`
atrás de um proxy, etc.) para esse diretório. Se quiser manter o
histórico de commits público também, basta configurar um remote
`origin` em `data/repo` apontando pro seu repositório de dados no
GitHub e adicionar `git -C data/repo push` no fim do cron.

## Bugs reais encontrados em produção (e corrigidos)

Estas três correções vieram de rodar o projeto de verdade no GitHub
Actions e comparar o comportamento esperado com o observado — vale
documentar o raciocínio, porque são o tipo de problema que só aparece
com uso real, não em teste local com dados de amostra.

### 1. Bug de persistência: lista de políticos "esquecida" a cada execução

**Sintoma**: o site publicado só mostrava uma fração dos políticos
(os "últimos buscados"), e o matcher parecia não reconhecer a maioria
das ~600 pessoas monitoradas na maior parte do dia.

**Causa raiz**: `sync_politicians.py` salvava os JSONs gerados
(`politicians_camara.json`, `politicians_senado.json`) num caminho
(`data/`) que faz parte do checkout do repositório de **código** — que
é recriado do zero a cada execução do CI. Como o step de sync só roda
1x por dia (o resto do dia só roda `main.py`), em 47 das 48 execuções
diárias esses arquivos simplesmente não existiam, e `config.py` caía
de volta pros ~5 políticos manuais — inclusive regenerando o site
inteiro com essa lista reduzida a cada vez.

**Correção**: os arquivos gerados agora moram dentro de `REPO_DIR`
(`<repo-de-dados>/_meta/`) — o único lugar que de fato persiste entre
execuções (é clonado + tem `git push` a cada run) — e `sync_politicians.py`
agora também commita essas mudanças ali. Testado: rodar `main.py` numa
execução separada, sem chamar `sync_politicians.py` antes, continua
enxergando a lista completa.

### 2. Falso positivo: sobrenome de uma pessoa não monitorada

**Sintoma**: a notícia "Confira a agenda dos candidatos à Presidência"
gerou commits em `glauber-braga.md` e `humberto-costa.md`, mas nenhum
dos dois é citado nela.

**Causa raiz**: o texto completo da notícia (RSS costuma trazer mais
que só o título) cita, entre outros, o candidato presidencial
**Edmilson Costa (PCB)** — uma pessoa sem nenhuma relação com Humberto
Costa (senador monitorado), mas que compartilha o sobrenome. Como
"Costa" foi adicionado como alias automático pro Humberto Costa (pra
resolver um bug anterior, de menções só pelo sobrenome), o sistema
capturou o "Costa" de "Edmilson Costa" e atribuiu errado — mesmo sem
nenhuma ambiguidade entre políticos monitorados (só existe 1 "Costa"
na lista).

**Correção**: `disambiguation.py` agora checa a palavra imediatamente
antes de qualquer menção de uma palavra só (sobrenome/apelido). Se essa
palavra for um nome capitalizado que não bate com o primeiro nome de
nenhum candidato monitorado, a menção é descartada — é sobrenome de
outra pessoa. Essa checagem só se aplica a aliases de uma palavra só;
nomes completos (ex.: "Arthur Lira") nunca são descartados por causa
disso, senão frases como "Ontem, Arthur Lira se reuniu..." perderiam a
menção só por causa da palavra "Ontem" antes.

### 3. Bloqueio silencioso por User-Agent

**Sintoma**: `main.py` sempre reportava "0 notícias coletadas", sem
erro visível no workflow (✓ verde mesmo assim).

**Causa raiz**: alguns servidores (comum em sites de governo) recusam
o User-Agent padrão do `urllib` (`Python-urllib/3.x`), e a exceção era
capturada silenciosamente por `fetch_all_feeds()`.

**Correção**: `scraper.py` agora envia um User-Agent de navegador em
toda requisição HTTP.

## Candidatos à eleição de 2026 (TSE) e deputados estaduais

### Candidatos 2026 — implementado

`tse_api.py` integra o dataset "Candidatos - 2026" do Portal de Dados
Abertos do TSE (`dadosabertos.tse.jus.br`) — não é uma API JSON/XML
como Câmara/Senado, é um ZIP com um CSV de todos os candidatos
registrados. Cobre Presidente, Governador, Senador, Deputado Federal e
**Deputado Estadual/Distrital** — ou seja, mesmo sem uma integração
dedicada às Assembleias Legislativas (veja abaixo), já dá pra cobrir
quem está concorrendo a uma vaga de deputado estadual em 2026.

Candidatos cujo nome já existe nas outras três fontes (por exemplo, um
deputado em exercício concorrendo à reeleição) são automaticamente
deduplicados — mantém-se o perfil de mandato, não um perfil duplicado
de candidatura (testado).

⚠️ Não pôde ser testado contra o arquivo real nesta sessão (sem acesso
à internet no ambiente onde este projeto foi gerado) — o parser segue
o layout de colunas documentado publicamente pelo TSE, estável há
vários ciclos eleitorais, mas rode `python3 sync_politicians.py` no
seu ambiente antes de confiar nele em produção. Se alguma coluna tiver
mudado de nome, o erro vai apontar exatamente qual.

```bash
python3 sync_politicians.py               # inclui TSE por padrão
python3 sync_politicians.py --skip-tse    # pula o TSE (mais rápido p/ testes locais)
python3 sync_politicians.py --skip-camara --skip-senado  # só o TSE
python3 sync_politicians.py --sample      # offline, com sample_tse_candidatos.csv
python3 sync_politicians.py --tse-arquivo-local=caminho/para/consulta_cand_2026.zip
```

#### Se o download automático do TSE der erro 403

Dois cenários distintos, encontrados os dois em produção nesta sessão:

**Bloqueio local (a partir de qualquer computador/rede)**: o CDN do
TSE (provavelmente Akamai ou Cloudflare) pode recusar requisições sem
cabeçalhos de navegador. Um conjunto mais completo de headers já foi
adicionado, mas sem garantia de que resolve sempre (fingerprinting de
TLS não dá pra contornar só com cabeçalhos HTTP).

**Bloqueio específico do GitHub Actions**: mesmo com o download
funcionando localmente, rodar dentro do GitHub Actions pode continuar
dando 403 — o CDN provavelmente bloqueia especificamente os IPs dos
runners do GitHub (conhecidos publicamente, e um alvo comum de
bloqueio por WAFs de sites de governo, independente de qualquer
cabeçalho). Esse é o caso mais provável se funcionou no seu
computador mas não no workflow.

Em qualquer um dos dois casos, uma falha no TSE **não derruba mais o
resto do sync** — Câmara e Senado continuam sendo sincronizados e
commitados normalmente, com um aviso no log em vez de erro fatal
(testado). Pra manter os dados do TSE atualizados apesar do bloqueio,
duas opções:

1. **Sincronizar o TSE só localmente, periodicamente**: baixe o zip
   pelo navegador, rode
   `python3 sync_politicians.py --tse-arquivo-local=caminho/do/arquivo.zip --skip-camara --skip-senado`
   no seu computador, e dê `git push` no repositório de dados
   manualmente (fora do GitHub Actions). O TSE muda pouco depois do
   prazo de registro de candidaturas, então rodar isso uma vez por
   semana (ou até só uma vez, pertinho da eleição) provavelmente basta.
2. **Commitar o zip do TSE no repositório**: baixe o arquivo, suba ele
   pro repositório de código (ex.: `tse_data/consulta_cand_2026.zip`),
   e mude o step do workflow que roda `sync_politicians.py` para usar
   `--tse-arquivo-local=tse_data/consulta_cand_2026.zip` em vez de
   tentar baixar toda execução. Assim o download nunca roda dentro do
   GitHub Actions.

### Deputados estaduais EM EXERCÍCIO — plano, não implementação

Diferente da Câmara/Senado, não existe uma API federal única para os
deputados atualmente em mandato nas 27 Assembleias Legislativas — cada
estado tem seu próprio site e (às vezes) seu próprio portal de dados
abertos, sem padronização entre eles. Uma pesquisa real (não uma
suposição) identificou:

- 🟢 **Minas Gerais (ALMG)**: API REST moderna e documentada em
  `dadosabertos.almg.gov.br/api/v2/` — o caso mais forte encontrado.
- 🟡 **São Paulo (ALESP)**: portal de dados abertos confirmado, com
  categoria "Deputados Estaduais", mas o formato exato ainda não foi
  verificado.
- 🟡 **Rio de Janeiro (ALERJ)**: tem Portal da Transparência robusto,
  mas nenhuma API estruturada equivalente foi encontrada nesta
  pesquisa.
- ❌ Os outros 23 estados ainda não foram pesquisados.

O plano completo (por que não tentar os 27 de uma vez, estratégia de
fases, e o próximo passo concreto) está em
[`plano-deputados-estaduais.md`](./plano-deputados-estaduais.md).

## Performance em escala (por causa do TSE)

O dataset de candidatos do TSE é MUITO maior que Câmara+Senado juntos
(dezenas de milhares de registros, contra ~600) — isso expôs dois
gargalos reais que precisaram de correção:

1. **Criação de arquivos em lote**: `ensure_repo()` fazia um `git
   commit` por político na primeira vez que via cada um. Medido: ~9.5ms
   por commit — aceitável com 600 políticos, mas ~6 minutos só nisso
   com 40.000. Corrigido para um único commit em lote (todos os
   arquivos novos de uma vez) — o mesmo teste ficou em ~2.5 segundos.

2. **Índice por prefixo no matcher fuzzy**: comparar cada candidato de
   nome extraído de uma notícia contra a lista inteira de políticos
   (via `difflib`) ficava em ~925ms por candidato com 40.000 políticos
   sintéticos — um único run processando ~15 notícias (~8 candidatos
   cada) levaria mais de 100 segundos só nessa etapa. Com um índice
   que agrupa os alvos por primeira letra normalizada (sem acento) e
   só compara dentro do mesmo grupo, o mesmo teste caiu pra ~5
   segundos (~22x mais rápido). Contrapartida: um erro de digitação
   bem na primeira letra do nome não seria pego por essa camada — uma
   troca aceitável dado o ganho de performance, e a camada exata
   continua funcionando normalmente independente disso.

Ambas as otimizações foram medidas com benchmarks reais neste
ambiente (não são estimativas) — os números exatos estão nos testes
que geraram esta seção.

### 4. TSE: só o primeiro estado do zip era processado

**Sintoma**: o sync do TSE completava sem erro, mas retornava só 558
candidatos — bem abaixo do esperado (dezenas de milhares, considerando
Deputado Federal + Estadual em todo o país).

**Causa raiz**: o zip de candidatos do TSE não tem um único CSV
nacional combinado — ele traz um arquivo por UF (27 arquivos). O
código lia só `csv_names[0]`, o primeiro da lista (tipicamente "AC",
por ordem alfabética), e processava exclusivamente aquele estado.

**Correção**: `tse_api.py` agora abre e processa **todos** os arquivos
`.csv` encontrados dentro do zip, agregando os resultados. Testado com
um zip sintético de 3 "estados" — confirmado que os candidatos de
todos os arquivos aparecem no resultado final, com cargo e UF
corretos.

### 5. Fuzzy de uma palavra colidindo com palavras comuns (escala do TSE)

**Sintoma**: notícias sobre o técnico de futebol "Jair Ventura" e sobre
o artigo "Cores não estão na luz..." geraram commits errados em
`adriana-ventura.md` e `altineu-cortes.md`.

**Causa raiz**: dois problemas diferentes no mesmo bug relatado.
"Jair Ventura" já devia ter sido descartado pela checagem de nome
precedente (bug #2 acima) — sinal de que a correção anterior não
tinha sido aplicada ainda quando esse caso ocorreu. Já "Cores" vs
"Côrtes" é um problema novo: a similaridade entre a palavra comum
"cores" e o sobrenome "Côrtes" (sem acento: "cortes") é 0.909 —
passa por pouco do limiar de 0.90 do fuzzy matching de uma palavra
só. Com a escala do TSE (~40 mil sobrenomes), esse tipo de colisão
acidental com palavras comuns do português deixa de ser raro.

**Correção**: fuzzy matching para candidatos de uma palavra só foi
**desativado**. Só a camada exata (que já cobre virtualmente todo
sobrenome real registrado nessa escala, com a proteção de nome
precedente do bug #2) trata menções de uma palavra. A perda é pequena
(erro de digitação bem numa menção de sobrenome sozinho não é mais
tolerado) frente ao ganho real de precisão.

### 6. Alias de sobrenome gerado errado para nomes de urna com título/patente

**Sintoma**: notícias sobre as atrizes "Maria Fernanda Cândido" e
"Fernanda Montenegro" geraram commits em `coronel-fernanda.md`.

**Causa raiz**: candidatos que usam nome de urna no padrão "Título/
Patente + Primeiro Nome" (comum entre candidatos ligados à segurança
pública — "Coronel Fernanda", "Delegado Fulano", etc.) quebram a
heurística de `extract_surname()`, que assume que a última palavra do
nome é sempre um sobrenome. Para "Coronel Fernanda", a última palavra
é "Fernanda" — um primeiro nome comum, não um sobrenome distintivo —
e virou alias automático, colidindo com qualquer "Fernanda" não
política. Diferente do bug #2 (Edmilson Costa), a checagem de nome
precedente não ajuda aqui: "Fernanda Montenegro" tem "Fernanda" como
primeira palavra da frase, sem nada antes pra checar.

**Correção**: `text_utils.has_title_prefix()` reconhece uma lista de
títulos/patentes comuns (Coronel, Delegado, Sargento, Major, Doutor,
Pastor, etc.) e `camara_api.py`/`senado_api.py`/`tse_api.py` não geram
mais o alias automático de sobrenome quando o nome começa com um
desses. Testado: `to_politician_dict()` para "Coronel Fernanda" não
inclui mais "Fernanda" nos aliases, e o nome completo continua
reconhecido normalmente.

### 7. Falha do TSE derrubava o sync inteiro

**Sintoma**: `sync_politicians.py` rodando no GitHub Actions terminava
com `HTTPError: HTTP Error 403: Forbidden` e `Process completed with
exit code 1` — mesmo Câmara e Senado, que não têm nada a ver com o
TSE, ficavam sem sincronizar.

**Causa raiz**: o CDN do TSE aparentemente bloqueia especificamente
os IPs dos runners do GitHub Actions (funcionava localmente, no
computador do usuário, mas não dentro do workflow) — e a exceção não
era capturada, propagando e derrubando o script inteiro no meio da
execução, antes mesmo de chegar no commit.

**Correção**: a chamada ao sync do TSE agora está dentro de um
`try/except` em `run()` — uma falha ali vira um aviso no log, não um
erro fatal, e o script segue para commitar o que já foi sincronizado
com sucesso (Câmara/Senado). Testado com um mock forçando o mesmo erro
403: o script terminou com sucesso, e os arquivos de Câmara/Senado
foram commitados normalmente, só o do TSE ficou de fora.

### 8. Explosão de falsos positivos com nomes de urna genéricos (incidente grave)

**Sintoma**: o workflow ficou rodando por mais de 4 horas, criando
mais de 1.700 commits, repetindo a mesma notícia (uma pesquisa
Datafolha) atribuída a dezenas de políticos sem relação nenhuma entre
si. Como o cron dispara a cada 30 min sem esperar a execução anterior
terminar, novas execuções foram se empilhando por cima, todas
escrevendo no mesmo repositório de dados ao mesmo tempo.

**Causa raiz**: é muito comum um candidato registrar como nome de
urna uma única palavra genérica ("Ana", "Duda", "Superman"...) pra
chamar atenção na cédula. Cada nome desses vira um alias de
correspondência exata de uma palavra só — e numa base de ~40 mil
candidatos do TSE, é praticamente garantido que algum desses nomes
genéricos apareça, sem relação nenhuma, dentro de outro texto
qualquer (ex.: o alias "Ana" batendo dentro de "Ana Luiza", uma
pessoa completamente diferente, citada como parte de uma lista de
resultados de pesquisa eleitoral). Diferente dos bugs de sobrenome
anteriores, aqui não existe um "nome que precede" pra checar — o
problema é o nome inteiro do candidato ser uma palavra comum demais.

Um segundo problema nos dados, encontrado no meio da investigação:
`tse_api.py` não removia acentos antes de gerar o slug, produzindo
slugs corrompidos como `mar-lia-campos` (deveria ser
`marilia-campos`) e `s-o`.

**Correção** (três partes):

1. Nomes de urna de **uma palavra só** não viram mais alias
   automático — só nomes com 2+ palavras (o nome civil, se diferente,
   ainda serve de alias). O preço: um candidato cujo nome de urna
   inteiro é uma palavra genérica só é encontrado pelo nome civil, se
   for diferente — não existe solução geral sem uma lista de nomes
   comuns do português pra saber quais palavras seriam "seguras".
2. `tse_api.py` agora reaproveita a função `slugify()` já testada de
   `camara_api.py`, que remove acentos corretamente.
3. **Trava de segurança em `main.py`**: se uma notícia bater em mais
   de 5 políticos ao mesmo tempo, é tratado como sinal de erro de
   correspondência — a notícia é pulada (com aviso no log) em vez de
   gerar commits pra todo mundo. Defesa em profundidade contra
   qualquer outro caso parecido que ainda não foi identificado.

Testado: a mesma manchete real do Datafolha, reproduzida com
candidatos sintéticos de nome de urna genérico, não gera mais nenhum
falso positivo.

### 9. Execuções do workflow se empilhando (sem controle de concorrência)

**Sintoma**: enquanto uma execução travada rodava por horas, novas
execuções continuavam dispar sendo a cada 30 minutos, todas tentando
escrever no mesmo repositório de dados ao mesmo tempo.

**Causa raiz**: o workflow não tinha nenhum controle de concorrência
— o comportamento padrão do GitHub Actions permite execuções
paralelas de um mesmo workflow, mesmo agendado.

**Correção**: adicionado um bloco `concurrency` no
`.github/workflows/update.yml` — agora, se uma execução ainda estiver
rodando quando o próximo agendamento disparar, a nova fica **na
fila** em vez de rodar em paralelo. Isso não substitui a correção do
bug #8 (que é a causa raiz de qualquer execução ficar lenta o
suficiente pra isso importar), mas evita que qualquer problema futuro
do tipo vire uma pilha de execuções conflitantes.

### 10. Falsos positivos persistindo mesmo após as correções anteriores

**Sintoma**: mesmo depois dos bugs #8 e #9, novas fontes RSS adicionadas
(G1, Folha, Gazeta do Povo, BBC) continuaram gerando commits errados —
ex.: uma notícia sobre "Caso Lulinha" batendo em candidatos como
"Mario Concreto" e "Milena do Reforço", sem relação nenhuma.

**Causa raiz**: medi a similaridade real entre os candidatos extraídos
do título ("Caso Lulinha", "Mendonça") e os nomes que bateram errado —
os scores ficaram entre 0.18 e 0.48, bem abaixo do limiar de 0.85. Ou
seja, **não era fuzzy matching** — era correspondência **exata**. A
explicação: o matcher rodava contra `título + descrição` da notícia, e
a descrição do RSS de fontes mais genéricas (diferente das duas fontes
curadas originais, Agência Brasil e Agência Câmara) pode trazer
conteúdo bem mais solto — incluindo, aparentemente, menções incidentais
a candidatos em algum lugar do corpo do texto, sem relação real com a
matéria principal.

**Correção** (três partes):

1. A correspondência agora usa **só o título** da notícia, não mais
   título+descrição. A descrição continua disponível pro resumo via
   `--summarize`, só não participa mais da decisão de "quem foi
   citado".
2. Políticos do TSE (fonte `"tse"`) são **excluídos da camada de
   fuzzy matching** inteiramente — só correspondência exata. O fuzzy
   multi-palavra, validado e seguro na escala pequena de Câmara/Senado
   (~600 pessoas), tem uma chance alta demais de colidir por acaso com
   algum nome entre 40 mil candidatos do TSE. Cada político agora
   carrega um campo `"source"` (manual/camara/senado/tse) pra viabilizar
   esse filtro.
3. O limite da trava de segurança (bug #8) caiu de 5 para 3 — um
   incidente anterior teve exatamente 5 correspondências, que não
   disparavam a trava antiga (`> 5`, não `>= 5`).

**Nota sobre dados antigos**: parte dos falsos positivos reportados
(ex.: "Flávio" batendo em 24 políticos) é esperada se o
`_meta/politicians_tse.json` do seu repositório de dados ainda não foi
regenerado com o `tse_api.py` corrigido do bug #8 — corrigir o código
não limpa retroativamente dados já sincronizados com a versão antiga.
Confirmado com um teste sintético: com aliases corretos (só "Flávio
Bolsonaro" e "Bolsonaro", nunca "Flávio" sozinho), essa notícia não
bate em ninguém.

### 11. `ensure_repo()` usava lista de políticos "congelada"

**Sintoma**: `sync_politicians.py` salvou 39.688 candidatos em
`politicians_tse.json`, mas só 19.477 arquivos `.md` existiam no
repositório de dados — quase 20 mil faltando.

**Causa raiz**: `repo_writer.py` importava `POLITICIANS` de `config.py`
uma única vez, no topo do arquivo (`from config import REPO_DIR,
POLITICIANS`). Esse valor só é calculado quando o módulo `config` é
importado pela primeira vez — o que acontece bem no início da
execução de `sync_politicians.py`, **antes** de `sync_tse()` escrever
o JSON atualizado com os 39.688 candidatos. Como `run()` chama
`ensure_repo()` **antes** de sincronizar as fontes, ela sempre criava
arquivos só para quem já existia antes daquela execução começar —
qualquer candidato novo (ou com dados corrigidos, como no bug #8)
nunca ganhava um arquivo próprio, silenciosamente.

Reproduzido e confirmado: um teste isolado mostrou exatamente esse
comportamento — só o candidato que já existia no JSON no momento do
import ganhou arquivo; dois candidatos escritos no JSON *depois*
(simulando o que `sync_tse()` faz de verdade) ficaram de fora.

**Correção**: `ensure_repo()` agora recarrega a lista de políticos na
hora (`config.load_politicians()`), a cada chamada, em vez de depender
de um valor importado uma única vez. Testado com o mesmo cenário exato
do bug: os candidatos novos passaram a ganhar arquivo normalmente.

### 12. Slugs continuavam com hífen no lugar de acentos

Se isso ainda estiver acontecendo depois de aplicar as correções
anteriores, quase certamente `tse_api.py` no seu ambiente ainda é uma
versão anterior à correção do bug #8 (que trocou a geração de slug
manual por `slugify()`, importada de `camara_api.py`, com remoção
correta de acentos via `unicodedata`). Confirme rodando:

```bash
grep "from camara_api import slugify" tse_api.py
```

Se não retornar nada, o arquivo está desatualizado — substitua pela
versão mais recente.

### 13. Arquivo `BRASIL.csv` redundante contando candidatos em dobro

**Sintoma**: `politicians_tse.json` tinha 39.688 candidatos, quase o
dobro dos ~20.713 esperados pra 2026 (número informado pelo usuário,
que abriu o zip manualmente e contou).

**Causa raiz**: o zip do TSE tem 29 CSVs — 27 por UF, mais
`..._BR.csv` (só Presidente/Vice, arquivo legítimo e não-redundante),
mais `..._BRASIL.csv`, que é a **soma de todos os outros 28 arquivos
num só**. A correção do bug #4 (que passou a ler todos os CSVs do
zip, não só o primeiro) processava esse arquivo redundante também,
contando cada candidato duas vezes.

**Correção**: `_open_all_csvs_from_zip()` agora ignora especificamente
qualquer arquivo terminado em `_BRASIL.csv` (mantendo o `_BR.csv`,
que não é redundante). Testado com um zip sintético reproduzindo a
estrutura real (2 estados + presidente + um "BRASIL" redundante
somando os três): o resultado final tem 3 candidatos, não 6.

### 14. Arquivos duplicados: slug antigo (corrompido) ao lado do novo (correto)

**Sintoma**: depois de aplicar a correção de acentos (bug #12) e
resincronizar, o total de arquivos `.md` só cresceu — candidatos que
já tinham arquivo com o slug antigo (ex.: `alyne-vit-ria.md`) ganharam
um SEGUNDO arquivo com o slug novo e correto (`alyne-vitoria.md`), sem
o antigo ser removido.

**Causa raiz**: `ensure_repo()` só *cria* arquivos que não existem —
ela nunca soube que `alyne-vit-ria.md` e `alyne-vitoria.md` eram, na
verdade, a mesma pessoa antes e depois da correção do slug.

**Correção**: script novo, `cleanup_duplicate_slugs.py`. Para cada
político atual, reconstrói qual seria o slug ANTIGO (reproduzindo a
lógica quebrada de antes) a partir do nome; se existir um arquivo
nesse caminho antigo, ele é removido — mas não antes de copiar
qualquer notícia real já registrada nele pro arquivo novo (evitando
perder histórico). Testado nos dois cenários: arquivo antigo só com o
commit "init" (removido direto) e arquivo antigo com notícia real
registrada (mesclada no arquivo novo antes da remoção).

```bash
cd data/repo
python3 ../../cleanup_duplicate_slugs.py . --dry-run   # confira antes
python3 ../../cleanup_duplicate_slugs.py .             # de verdade
git push
```

**Nota de campo**: em produção, o `git rm` do script acima falhou com
`"did not match any files"` para todos os arquivos antigos — sinal de
que existiam no disco mas nunca tinham sido rastreados pelo Git (ex.:
sobras de uma etapa anterior que criou o arquivo fisicamente sem
consolidar num commit). Nesse caso, `git clean -fd` (rodado dentro de
`data/repo`) remove esses arquivos não rastreados de uma vez — foi o
que resolveu na prática. `cleanup_duplicate_slugs.py` também foi
atualizado para reportar o erro real do Git em vez de assumir sucesso
silenciosamente.

## Remoção do MANUAL_POLITICIANS

O projeto não tem mais nenhuma lista de políticos embutida no código.
Câmara, Senado e TSE já cobrem todo mundo que é candidato ou está em
exercício — quem não é nenhum dos dois (um ex-presidente inelegível,
um ministro do STF sem candidatura) simplesmente deixa de ser
monitorado, sem precisar de uma lista de exclusão manual.

**O que isso quebraria sem tratamento**: nomes de urna de uma palavra
só (ex.: "Lula") não geram alias automático (ver bugs #8/#10) — então
tirar a lista manual faria o sistema parar de reconhecer menções pelo
apelido curto de quem só tinha esse alias curado à mão, restando só o
nome civil completo.

**Correção**: `extra_aliases.py`, um arquivo pequeno que só
**enriquece** aliases de quem já existe via alguma fonte — não recria
a pessoa do zero, não define papel/partido/nada. Cada regra é uma
palavra distintiva (`name_contains`) que precisa aparecer no nome da
pessoa. Testado: com Lula e Tarcísio vindos do TSE (sample sintético),
os aliases curtos ("Lula", "Tarcísio") voltam a funcionar no matcher.

**Migração pro repositório de dados já existente**: rode
`remove_orphaned_politicians.py` pra apagar os arquivos de quem não
corresponde mais a ninguém na lista atual (ex.: `jair-bolsonaro.md`,
`flavio-dino.md`) — testado nos dois casos reais já encontrados em
produção (arquivo rastreado pelo Git normalmente, e arquivo existente
no disco mas nunca commitado).

```bash
cd data/repo
python3 ../../remove_orphaned_politicians.py . --dry-run   # confira antes
python3 ../../remove_orphaned_politicians.py .             # de verdade
git push
```

A categoria "Outros cargos" do site foi removida (ficaria sempre
vazia sem fonte manual) — agora só existem "Em exercício" e
"Candidatos à Eleição 2026".

## Candidatos com mandato aparecem em duas categorias

Quem já tem mandato (deputado, senador, ou um cargo especial como
governador) e também está concorrendo em 2026 — pra reeleição ou pra
outro cargo — aparece nos **dois** cards que se aplicam: o de mandato
("Em exercício" ou "Outros cargos") e o de "Candidatos à Eleição
2026". Continua existindo **um arquivo só** por pessoa no repositório
de dados — não duplica o histórico Git dela.

Como funciona: `config.load_politicians()` não descarta mais a
informação de candidatura de quem já tem mandato — em vez disso,
marca a entrada existente com `is_2026_candidate = True` e
`candidacy_role` (o cargo específico da candidatura, ex.: "Candidato(a)
a Senador (AL)"). `site_generator.py` usa essa marcação pra listar a
pessoa em ambas as categorias, mostrando o cargo/UF **da candidatura**
na página de candidatos e o cargo/UF **do mandato atual** nas outras
páginas — mesma pessoa, informação certa em cada contexto.

Bug real corrigido no caminho: a marcação só funcionava quando a
pessoa era encontrada por *nome* — quando o *slug* já batia (o caso
mais comum, já que o slug vem do mesmo nome), o código pulava antes de
aplicar a marcação. Testado com um cenário controlado (Arthur Lira
como deputado + candidato a Senador): ele aparece corretamente nas
duas páginas, cada uma mostrando o cargo certo pro contexto.

### 15. Site reorganizado por categoria + paginação (escala do TSE)

**Problema**: com mais de 20 mil políticos, a página inicial listando
todo mundo de uma vez ficava enorme e lenta pra carregar/navegar.

**Correção**: `index.html` agora só mostra 3 cards de categoria (Em
exercício — Câmara/Senado, Candidatos 2026, Outros cargos), sem listar
ninguém diretamente. Cada categoria abre sua própria página
(`eleitos.html`, `candidatos.html`, `outros.html`) com busca, filtros
por **nome, partido, cargo e UF** (novo), e **paginação client-side**
em JavaScript puro — os dados de todos os políticos daquela categoria
vêm embutidos como um array JSON na página, mas só uma página de
resultados (50 por vez) é de fato renderizada no navegador a cada
momento, então o tamanho da lista nunca deixa a página pesada.

Como as páginas de categoria não chamam `get_log()` (isso exigiria um
processo `git log` por político — inviável em massa), elas mostram só
nome/partido/cargo/UF; o histórico completo de commits continua
disponível na página individual de cada político, como antes.

Testado: geração de página com 5.000 políticos sintéticos levou 0.03s
(arquivo final de ~530 KB, ~2 MB extrapolando pra 20 mil). A lógica de
filtro/paginação em si foi testada rodando o JavaScript gerado de
verdade em Node.js (com um DOM simulado) — filtro por UF, navegação
entre páginas, busca sem resultado, e o limite no fim da paginação
funcionaram como esperado.

## Estrutura do projeto

- `config.py` — mescla Câmara + Senado + TSE (sem lista manual), e as fontes RSS
- `extra_aliases.py` — apelidos extras curados pra quem tem nome de urna de uma palavra só
- `camara_api.py` — integração com a API de Dados Abertos da Câmara (JSON)
- `senado_api.py` — integração com a API de Dados Abertos do Senado (XML)
- `sync_politicians.py` — sincroniza deputados e senadores a partir das APIs
- `matcher.py` — identifica políticos citados (casamento exato + fuzzy, sem dependências)
- `disambiguation.py` — resolve aliases/sobrenomes ambíguos usando contexto ao redor da menção
- `text_utils.py` — normalização de texto (remoção de acentos, extração de sobrenome) compartilhada
- `ner_spacy.py` — backend opcional de NER via spaCy (requer instalação à parte)
- `summarizer.py` — resumo automático de commit message via LLM (requer instalação à parte)
- `scraper.py` — busca e faz parse de feeds RSS (sem dependências externas)
- `repo_writer.py` — grava as notícias como commits reais no Git (organizados em subpastas por UF)
- `migrate_to_uf_folders.py` — migração única para reorganizar um repositório de dados existente (achatado) em subpastas por UF
- `cleanup_duplicate_slugs.py` — remove arquivos duplicados deixados pelo bug de slug com acento corrompido
- `remove_orphaned_politicians.py` — remove arquivos de quem não corresponde mais a ninguém na lista atual
- `site_generator.py` — gera o site estático HTML: index com 2 categorias + páginas com busca/filtro (nome/partido/cargo/UF) e paginação client-side
- `main.py` — orquestra o pipeline completo de notícias (`--backend alias|spacy`, `--summarize`)
- `git_events.py` — merge real para troca de partido + tags anotadas para marcos formais
- `record_event.py` — CLI manual/curada para registrar esses eventos com confirmação
- `.github/workflows/update.yml` — workflow do GitHub Actions para agendamento + deploy
- `sample_feed.xml` — feed de notícias de exemplo para testar offline
- `sample_deputados.json` — amostra real da API da Câmara para testar offline
- `sample_senadores.xml` — amostra real da API do Senado para testar offline
- `real_sample_feed_camara.xml` — amostra real do feed de Política da Câmara
- `tse_api.py` — integração com o dataset de candidatos 2026 do TSE
- `sample_tse_candidatos.csv` — amostra sintética do CSV do TSE para testar offline
- `plano-deputados-estaduais.md` — plano de pesquisa/implementação para as 27 Assembleias Legislativas

## Próximos passos sugeridos

1. **Fase 1 do plano de deputados estaduais**: construir `almg_api.py`
   (Minas Gerais) seguindo o padrão de `camara_api.py` — é a integração
   estadual mais viável encontrada até agora. Ver
   `plano-deputados-estaduais.md`.
2. **Validar o TSE contra o arquivo real**: `tse_api.py` foi construído
   a partir do layout documentado, mas nunca rodou contra o ZIP de
   verdade — primeira coisa a testar antes de confiar nele em produção.
3. **Crescimento automático da base**: usar `ner_spacy.py` em modo de
   auditoria (`resolve_entities()`) para listar pessoas mencionadas com
   frequência nas notícias que ainda não estão em `config.py`.
4. **Monitorar o tamanho do repositório de dados**: com TSE + Câmara +
   Senado, o `gitpolitica-data` pode chegar a dezenas de milhares de
   arquivos — vale acompanhar o tempo de clone/checkout do workflow ao
   longo do tempo, e considerar arquivar candidaturas de eleições
   passadas se isso virar um problema.
