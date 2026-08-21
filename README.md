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

`config.py` mescla três fontes, nessa ordem de prioridade:
1. `MANUAL_POLITICIANS`: cargos que não vêm do Congresso (Presidente,
   ministros do STF, governadores). Mantidos à mão porque não existe
   uma API única que cubra todos os Poderes.
2. `data/politicians_camara.json`: gerado por `sync_politicians.py` a
   partir da API de Dados Abertos da Câmara (`dadosabertos.camara.leg.br`,
   JSON paginado). Cobre automaticamente ~513 deputados em exercício.
3. `data/politicians_senado.json`: gerado a partir da API do Senado
   (`legis.senado.leg.br/dadosabertos`, XML). Cobre ~81 parlamentares
   em exercício (titulares e suplentes atualmente exercendo o mandato).

Em caso de conflito de slug, a entrada de prioridade mais alta vence —
por exemplo, se um nome aparecer tanto na lista manual quanto na da
Câmara, a manual prevalece; um nome que aparecesse tanto na Câmara
quanto no Senado (caso raro) ficaria com a versão da Câmara.

Isso vai:
1. Criar (ou reaproveitar) o repositório Git em `data/repo/`
2. Ler as notícias das fontes RSS
3. Identificar quais políticos monitorados (config.py) são citados
4. Criar um commit real por notícia relevante, no arquivo `<slug>.md` do político
5. Gerar o site estático em `data/site/` (abra `data/site/index.html` no navegador)

## Explorar o repositório Git gerado como um repo de verdade

```bash
cd data/repo
git log --oneline                    # todos os commits
git log --oneline -- lula.md         # só os commits sobre um político
git show <hash>                      # ver o diff de um commit específico
```

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

## Estrutura do projeto

- `config.py` — mescla políticos manuais + Câmara + Senado, e as fontes RSS
- `camara_api.py` — integração com a API de Dados Abertos da Câmara (JSON)
- `senado_api.py` — integração com a API de Dados Abertos do Senado (XML)
- `sync_politicians.py` — sincroniza deputados e senadores a partir das APIs
- `matcher.py` — identifica políticos citados (casamento exato + fuzzy, sem dependências)
- `disambiguation.py` — resolve aliases/sobrenomes ambíguos usando contexto ao redor da menção
- `text_utils.py` — normalização de texto (remoção de acentos, extração de sobrenome) compartilhada
- `ner_spacy.py` — backend opcional de NER via spaCy (requer instalação à parte)
- `summarizer.py` — resumo automático de commit message via LLM (requer instalação à parte)
- `scraper.py` — busca e faz parse de feeds RSS (sem dependências externas)
- `repo_writer.py` — grava as notícias como commits reais no Git
- `site_generator.py` — gera o site estático HTML a partir do histórico Git
- `main.py` — orquestra o pipeline completo de notícias (`--backend alias|spacy`, `--summarize`)
- `git_events.py` — merge real para troca de partido + tags anotadas para marcos formais
- `record_event.py` — CLI manual/curada para registrar esses eventos com confirmação
- `.github/workflows/update.yml` — workflow do GitHub Actions para agendamento + deploy
- `sample_feed.xml` — feed de notícias de exemplo para testar offline
- `sample_deputados.json` — amostra real da API da Câmara para testar offline
- `sample_senadores.xml` — amostra real da API do Senado para testar offline
- `real_sample_feed_camara.xml` — amostra real do feed de Política da Câmara

## Próximos passos sugeridos

1. **Outros Poderes**: STF, governadores e prefeitos não têm uma API
   central única — dá pra criar módulos parecidos com `camara_api.py`
   caso surjam fontes de dados abertos específicas para cada um.
2. **Crescimento automático da base**: usar `ner_spacy.py` em modo de
   auditoria (`resolve_entities()`) para listar pessoas mencionadas com
   frequência nas notícias que ainda não estão em `config.py`, e
   revisar periodicamente quem deveria virar um novo político monitorado.
3. **Testar o workflow de ponta a ponta**: como explicado na seção de
   deploy, o `.github/workflows/update.yml` não pôde ser validado com
   um `git push` real nesta sessão — vale rodá-lo manualmente
   (`workflow_dispatch`) assim que configurar os dois repositórios,
   antes de deixá-lo rodando sem supervisão no agendamento automático.
