# Grafo GitPolítica

Gera o site de relações (galeria de políticos que vira rede ao passar o
mouse) a partir do repositório de dados `gitpolitica-data`.

**Ligação = dois itens citados na mesma notícia.** Não indica
envolvimento nem culpa; cada ligação mostra as notícias que a sustentam.

## Rodar com dados reais

```bash
cd grafo
python3 build_graph.py --repo ../data/repo --out site_grafo
# abra site_grafo/index.html no navegador
```

Opções: `--min-news 3` (notícias para um item virar bloco),
`--min-link 2` (notícias em comum para uma ligação), `--max-part 10`
(ignora notícias que citam mais participantes que isso, como pesquisas),
`--top 100` (máximo de políticos), `--fotos pasta` (miniaturas
`<slug>.jpg`).

## Página: interação

- **Clique** em um político para ver as ligações (passar o mouse só inclina
  o card, sem abrir nada). Os demais cards somem em ~0,2 s e os traços
  se desenham em ~0,5 s.
- As ligações são traços de circuito (horizontais/verticais com chanfro de
  45°), terminando em pinos na borda de cada bloco, com pulsos animados.
- A rede abre e **fica aberta** até você clicar no fundo, apertar Esc ou
  usar "← Voltar".
- Clique em um bloco da rede para ver as notícias que sustentam a ligação.

## Página: busca e lista

- A galeria mostra 24 políticos por vez (botão "Mostrar mais"), ordenados
  pelo número de notícias.
- A barra de busca procura **políticos e também os itens das ligações**
  (empresas, casos, órgãos, partidos, pessoas). Digitar filtra a galeria;
  escolher um resultado abre a rede daquele item no centro da tela.
- Só aparecem políticos com pelo menos uma ligação que passou nos limites:
  para listar mais gente, use `--top 500` e/ou `--min-link 1`.

## Quantas fotos gerar

Só as dos políticos que o site exibe (os do grafo). Cada miniatura de
240 px tem em torno de 10 a 15 KB (estimativa): mil políticos ≈ 10 a 15 MB,
já as ~21 mil fotos do TSE seriam ≈ 250 MB, pesado demais para o Pages.
Se mudar `--top`, rode `prepare_fotos.py` de novo.

## Curar o ruído

A extração de empresas/pessoas/casos é por regras sobre o TÍTULO, então
haverá itens errados. Rode, leia a lista "itens mais frequentes" que o
script imprime e edite `entidades_curadas.json`:

- `ignorar`: nomes que não devem virar bloco;
- `juntar`: nome canônico -> variantes (ex.: "Construtora Alfa" <- "Alfa S.A.");
- `tipos`: força o tipo de um item;
- `adicionar`: itens conhecidos, com apelidos.

## Testes

```bash
python3 -m unittest tests.test_build_graph
```

A pasta `amostra/` tem dados FICTÍCIOS no formato do repositório.

## Fotos

Fotos de candidatos: ZIPs por UF no portal de dados abertos do TSE
(licença CC BY — o site credita o TSE no cabeçalho). Gere miniaturas
quadradas (240 px) só dos políticos que estão no grafo:

```bash
py -m pip install pillow          # uma vez
py build_graph.py --repo ../data/repo --out site_grafo
py prepare_fotos.py --graph site_grafo/graph.json --repo ../data/repo --origem D:/Dev/"Git Politica Brasileira"/fotos/fotos --saida site_grafo/fotos
py build_graph.py --repo ../data/repo --out site_grafo --fotos site_grafo/fotos
```

`--origem` é a pasta onde você baixou os ZIPs (ou JPGs soltos); o script
procura em todas as subpastas e lê direto de dentro dos ZIPs.

**Como associa**: o nome do arquivo de foto deve conter o SQ_CANDIDATO
(número de ~12 dígitos), que está em `_meta/politicians_tse.json`
(`tse_sequencial`). Parlamentares em exercício que também são candidatos
não têm esse campo no próprio registro, então o script tenta casar pelo
nome + UF. Nomes ambíguos NÃO são adivinhados: aparecem no relatório.

O relatório final lista quem ficou sem foto, sem candidatura em 2026
(parlamentares que não concorrem não têm foto no TSE) e os ambíguos.
Quem não tem foto aparece com as iniciais.

Para conferir como os arquivos estão nomeados:

```bash
py -c "import zipfile;print(zipfile.ZipFile(r'foto_cand2026_SP_div.zip').namelist()[:5])"
```
