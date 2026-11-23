# Addon-RufSas

Add-on de otimização de dieta para o [RuFaS](https://github.com/RuminantFarmSystems/RuFaS). Ele traz três
otimizadores para o mesmo problema de formulação:

| Otimizador | O que é |
|---|---|
| **SLSQP** | O original do RuFaS (`RationOptimizer`), a linha de base. |
| **PuLP + simplex (NASEM)** | `addon_rufas/simplex_ration_optimizer.py`: as mesmas restrições NASEM do RuFaS, resolvidas pelo método simplex no PuLP. Substitui o SLSQP dentro da simulação. É determinístico e não usa derivadas. |
| **NRC clássico (PuLP)** | `addon_rufas/nrc_lp.py`: PL linear do NRC 2001 com energia, PDR, PNDR, proteína metabolizável, FDN, minerais e vitaminas, e preços-sombra. |

O RuFaS **não é editado**: o add-on se liga a ele por subclasse e troca do
otimizador em tempo de execução.

- **Documentação da implementação** (modelo, integração, sensibilidade, análise
  econômica, CEPEA, testes, limitações): [`docs/DOCUMENTACAO.md`](docs/DOCUMENTACAO.md)
- Escopo e plano de entregas: [`addon-rufas-otimizacao-dieta.md`](addon-rufas-otimizacao-dieta.md)
- Notas dos livros NRC 2001 e NASEM 2021: [`docs/notas-livros.md`](docs/notas-livros.md)
- Rascunho do relatório final: [`docs/RELATORIO.md`](docs/RELATORIO.md)
- Preços reais (R$/kg MS), em [`scenarios/precos/`](scenarios/precos/README.md), com fontes e ressalvas no README da pasta:
  - `goias-2026-11.json`: leite e milho do CEPEA e outros 4 alimentos de Goiás;
  - `planilha-2026.json`: 127 alimentos da planilha dos colegas, convertidos com `converter_planilha.py`, com o premix corrigido e teto nos minerais.

## Instalação

Pré-requisitos: Python 3.12 e uma cópia do RuFaS em `RufSas/RuFaS`. Essa pasta
não vai para o git. Os resultados foram obtidos com o commit `2114532`:

```powershell
git clone https://github.com/RuminantFarmSystems/RuFaS.git RufSas/RuFaS
git -C RufSas/RuFaS checkout 2114532
```

Na raiz deste repositório:

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONPATH="RufSas/RuFaS"
.venv\Scripts\python -m addon_rufas.web
```

```bash
# Linux/macOS
python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=RufSas/RuFaS .venv/bin/python -m addon_rufas.web
```

Abra `http://127.0.0.1:5000`. Testes: `.venv\Scripts\python -m pytest`.

## Simulação da fazenda (SLSQP × simplex)

```powershell
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\smoke\task_manager_metadata.json
.venv\Scripts\python -m addon_rufas.summarize results\compare
```

`--optimizer slsqp | lp | compare` (`lp` é o simplex). No modo `compare`, o simplex conduz a simulação
e o SLSQP resolve o mesmo problema em sombra a cada formulação, o que dá pares
comparáveis. Para usar outra fazenda, troque o `-p`. Preços reais: veja a seção 7
da [documentação](docs/DOCUMENTACAO.md#7-preços-reais-cepea).

**Fazendas de teste com preços brasileiros:** [`scenarios/fazendas/`](scenarios/fazendas/README.md).
São 8 fazendas montadas com os exemplos do RuFaS: rebanhos free-stall (100 vacas)
e open lot (1.000 vacas), cada um com as 4 listas regionais de alimentos.
`gerar.py` monta as pastas com os preços da planilha. O README da pasta tem os
comandos e os resultados das 312 formulações pareadas.

**Sensibilidade a ±10% e ±20% nos preços:** [`scenarios/precos/sensibilidade.md`](scenarios/precos/sensibilidade.md),
gerado por `scenarios/precos/sensibilidade.py`.

## Interface web

A interface carrega os 175 alimentos da biblioteca NASEM. Os 10 alimentos da
configuração fictícia Midwest começam selecionados, mas qualquer alimento pode
ser marcado, desmarcado (há um botão **Desmarcar todos**), pesquisado e
editado. O formulário permite alterar:

- a categoria animal: **vaca em lactação**, **vaca seca** ou **novilha em
  crescimento** (muda o cálculo das exigências e o conjunto de restrições);
- o alojamento: **confinamento** (`"Barn"`) ou **pasto** (`"Grazing"`), que muda
  só a energia de atividade (no pasto inclui o gasto de pastejar);
- peso corporal médio;
- exigências de energia, proteína metabolizável, cálcio, fósforo e matéria seca;
- metano entérico (g/dia) e nitrogênio urinário (kg/dia) médios do lote;
- preço do leite, para o **IOFC** (renda sobre o custo de alimentação):
  `produção de leite × preço − custo da dieta`, por vaca e por dia. Na vaca
  seca e na novilha a receita é zero, e o IOFC é só o custo com sinal negativo;
- custo de compra de cada alimento;
- limites mínimo e máximo de cada alimento.

Os alimentos aparecem com o nome da biblioteca NASEM (coluna `Name`), e a busca
procura por nome, ID ou categoria.

### Análise de sensibilidade

Escolha um item (qualquer exigência, o preço do leite, o preço de um alimento
marcado ou um limite do modelo NRC) e uma variação em %, e clique em **Analisar sensibilidade**. A página
formula duas vezes com o otimizador escolhido, antes e depois da mudança, e mostra:

- a ração antes e depois, alimento por alimento, com a diferença em kg MS;
- o custo e o IOFC antes e depois, e o **custo marginal** (variação do custo por
  unidade do item variado);
- conclusões em texto: o que entrou, saiu, aumentou ou diminuiu, e quais
  restrições ficaram **no limite** (margem menor que 0,05% do tamanho da
  restrição). São essas restrições que definem o custo. Se a ração não muda, o
  item não limita a decisão naquela faixa.

Para essa análise, prefira o simplex ou o modelo NRC. Isso não significa que o
SLSQP faça uma “conta errada”: o custo e as restrições continuam sendo
calculados pelas equações do RuFaS. A recomendação existe por dois motivos
verificáveis no código:

1. o `RationOptimizer._build_initial_value` do RuFaS usa `[1.0]` para o
   primeiro alimento e `random.random() * 10` para os demais quando não há uma
   ração anterior;
2. o SLSQP é um método iterativo para o problema não linear e depende desse
   ponto inicial, dos limites, das tolerâncias e do caminho de iterações para
   chegar a uma solução. O add-on não fixa a semente aleatória do RuFaS.

Por isso, duas execuções do SLSQP podem terminar em pontos viáveis diferentes,
parar por critérios numéricos diferentes ou encontrar custos ligeiramente
distintos. Essa parcela é chamada de **variação algorítmica** (ou ruído
numérico), não de erro da aritmética. Se o problema tiver uma solução ótima
única e o SLSQP convergir adequadamente nas duas execuções, a conta deve
reproduzir o mesmo resultado dentro da tolerância numérica. Se a diferença
persistir ou for grande, ela deve ser investigada como convergência, ponto
inicial, inviabilidade ou diferença de modelo — não simplesmente descartada
como ruído.

É importante também não misturar duas comparações:

- simplex e SLSQP usam as mesmas restrições NASEM do RuFaS. O simplex resolve
  PLs com os números da ração inteira fixados; portanto, diferenças pequenas
  entre eles podem vir dessa aproximação, das tolerâncias e da convergência do
  SLSQP.
- o modelo NRC clássico é outra formulação: ele usa as equações lineares do
  `addon_rufas/nrc_lp.py`, incluindo simplificações documentadas, como TDN da
  biblioteca sem o desconto de ingestão do NRC. Uma diferença entre NRC e simplex
  pode ser uma diferença real de modelo, e não ruído.

No modelo NRC, a tabela de margens também mostra o **preço-sombra** de cada
restrição. Ele é o multiplicador dual da restrição no LP e representa a
variação marginal do custo ótimo quando o lado direito da exigência aumenta
uma unidade, mantendo o restante do modelo e a base ótima inalterados. Assim,
para uma exigência `b` e preço-sombra `p`, a interpretação local é:

```text
custo_otimo(b + Δb) - custo_otimo(b) ≈ p * Δb
```

Essa interpretação é local, não uma promessa para qualquer aumento. Ela deixa
de valer exatamente quando muda a base ótima, outra restrição passa a ser
limitante, um alimento atinge ou deixa um limite, ou o problema fica
inviável. No código, o dual é lido do HiGHS através do PuLP. Para restrições
expressas como percentual da matéria seca, o dual é multiplicado pelo DMI
total, porque aumentar o limite em 1 ponto percentual altera o lado direito
em proporção à quantidade total de matéria seca. O teste
`tests/test_nrc_lp.py::test_shadow_price_is_the_marginal_cost` verifica essa
interpretação comparando o preço-sombra com uma nova solução após aumentar a
exigência.

### Cenários em JSON

**Exportar** baixa a página inteira em `cenario.json`: categoria, alojamento,
dados da vaca, exigências, alimentos marcados (`selected_feeds`), preços
(`cost_<id>`) e limites (`min_<id>`, `max_<id>`). **Importar** carrega um arquivo
desses. O arquivo pode ter só parte dos campos; o resto fica no padrão. Exemplo:

```json
{"category": "seca", "housing": "Grazing", "cow_body_weight": 700, "selected_feeds": [44, 104]}
```

Campos desconhecidos são recusados, para que um erro de digitação não passe em
silêncio. O mesmo conteúdo dentro de um envelope `{"data": {...}}` também é aceito.

O importador também lê arquivos **`dietopt-scenario`**, gerados por outra
ferramenta de dieta, e converte cada parte para os campos da página:

| No arquivo | Na página |
|---|---|
| `category` (`LAC_COW`, `DRY_COW`, `CLOSE_UP`, `GROWING`, `HEIFER_*`) | categoria: lactação, seca ou novilha |
| `cow.body_weight`, `parity`, `days_in_milk`, `milk_*`, `housing` etc. | dados da vaca |
| `cow.distance`, `cow.body_condition_score_5` | distância percorrida, escore de condição corporal |
| `cow.process_based_phosphorus_requirement` | fósforo do processo |
| `override` | exigências digitadas, quando o nome bate com um campo da página |
| `feeds` (`id`, `price`, `min`, `max`) | alimentos marcados, preço, mínimo e máximo |

Campos sem equivalente na página (`diets`, `tolerance`, `resolution`, `seeds`)
são ignorados, e a página avisa quais foram. Um `standard` diferente de NASEM
também é ignorado com aviso, porque a página calcula as exigências pelo NASEM.

O importador lê também o **`feed.json` de uma fazenda do RuFaS**, por exemplo
`scenarios/fazendas/freestall-midwest/feed.json`. É preciso distinguir o que
esse arquivo descreve do que a página precisa:

1. o cenário de simulação do RuFaS tem cinco arquivos (`config`, `animal`,
   `feed`, `metadata` e `tasks`) e descreve **o rebanho durante um ano**;
2. a página formula a dieta de **uma vaca**, num momento.

Por isso só o `feed.json` é aproveitado. O `animal.json` não tem "a vaca": o
peso, o leite e os dias em lactação de cada animal são gerados pela simulação,
dia a dia. A conversão (`web._from_rufas_feed`) faz:

| No `feed.json` | Na página |
|---|---|
| `feeds[].feed_type` e `purchased_feed_cost` | preço (`cost_<id>`) de cada alimento comprado |
| `rations[]` do lote da categoria (`lac_cow` para lactação) | alimentos marcados |
| `ration_percentage`, `intake_*`, `ration_formulation_parameters` | ignorados: a página formula a ração, não a recebe pronta |

A categoria importada é a lactação. Os alimentos marcados são os da ração do
lote `lac_cow`, os mesmos que o RuFaS oferece a esse lote na simulação. Assim,
o leite (202) e o concentrado inicial (216), que no arquivo pertencem só ao
lote de bezerras, não entram. Os dados da vaca continuam vindo do formulário ou
de **Calcular exigências**, e a página avisa isso ao importar. Com esse arquivo,
a página resolve a mesma lista de alimentos, com os mesmos preços, que a
simulação daquela fazenda usou.

### Os dois fósforos

- **Fósforo**: exigência da calculadora NASEM (manutenção, crescimento,
  gestação e leite).
- **Fósforo do processo**: exigência do módulo de fósforo do RuFaS
  (`Nutrients.perform_daily_phosphorus_update`), um balanço de perdas endógenas,
  urina, crescimento, gestação e leite dividido por uma eficiência de absorção.

A restrição usa o **maior** dos dois (`RationOptimizer.phosphorus_constraint`).
Os dois são preenchidos por **Calcular exigências NASEM** e podem ser editados.

Duas particularidades do RuFaS, mantidas aqui para os resultados baterem com a
simulação:

1. `Nutrients.ration_phosphorus_concentration` nunca é atualizado e fica 0, então
   a eficiência de absorção da vaca em lactação é sempre a constante 1,867.
2. As calculadoras comparam o alojamento com `"Barn"` e `"Grazing"` exatamente.
   Os arquivos de fazenda do RuFaS usam `"open air barn"` e `"barn"`, que caem no
   caso "outro" (energia de atividade 0 no NASEM). Uma fazenda a pasto precisa
   trazer exatamente `"Grazing"`.

A tabela de margens mostra cada restrição pelo nome (energia, cálcio, FDN etc.).
Pedidos simultâneos são atendidos um de cada vez, porque o otimizador troca
funções globais do RuFaS durante a formulação.

## Escolha do otimizador

Na seção **Otimizador**, selecione uma das opções:

### PuLP + simplex (NASEM)

Seleciona `PuLP + simplex (NASEM)` e usa:

```text
addon_rufas.simplex_ration_optimizer.SimplexRationOptimizer
pulp + HiGHS (solver="simplex")
```

O otimizador usa as mesmas restrições NASEM que o SLSQP do RuFaS. A cada
rodada, fixa os números que dependem da ração inteira (consumo, amido, % de
concentrado e desconto do NDT), monta um PL e o resolve pelo simplex; depois
recalcula esses números com a ração nova e resolve de novo, até a ração parar
de mudar. Não usa derivadas. O passo a passo está em
[Linearização usada pelo simplex](#linearização-usada-pelo-simplex-passo-a-passo).

Esse é o otimizador do add-on. Ele aceita só o padrão NASEM; um problema NRC é
recusado com erro.

### Otimizador original do RuFaS

Seleciona `RuFaS original (SLSQP)` e usa:

```text
RUFAS.biophysical.animal.ration.ration_optimizer.RationOptimizer
scipy.optimize.minimize(method="SLSQP")
```

Nesse modo, a formulação e as restrições são as originais do RuFaS. A
interface não reimplementa nem altera esse código; apenas chama a mesma classe
com os valores informados no formulário.

### Modelo NRC clássico (PuLP)

Seleciona `Modelo NRC clássico (PuLP)` e usa `addon_rufas.nrc_lp.solve` com PuLP
e o solver HiGHS (`highspy`). As exigências de energia, proteína metabolizável,
cálcio, fósforo e matéria seca vêm do mesmo painel dos outros otimizadores. O
painel **Modelo NRC (PuLP)** define o resto:

- FDN mínimo e máximo, FDN de forragem e gordura (padrão: os limites do RuFaS);
- Mg, K, Na, Cl e S (% MS) e Co, Cu, I, Fe, Mn, Se e Zn (mg/kg MS), com padrões
  da Tabela 14-7 do NRC 2001;
- vitaminas A, D e E (UI por kg de peso vivo), com padrões do cap. 7;
- a tolerância da matéria seca (0 = igual ao DMI).

O valor 0 desliga a restrição. Um nutriente que nenhum alimento marcado tem na
biblioteca é ignorado, com aviso. Se não houver ração possível, a página diz
quanto falta de cada nutriente e sugere fontes na biblioteca. Por exemplo, a
fazenda Midwest não tem premix vitamínico: marque o **VitTM Premix (300)**.

## Comparação justa

Para comparar os métodos, mantenha iguais:

1. os alimentos selecionados;
2. os preços;
3. os limites;
4. as exigências nutricionais;
5. o peso corporal.

Execute uma vez com cada opção e compare:

- status de viabilidade;
- custo por vaca/dia;
- ingredientes usados;
- quantidade de matéria seca;
- número de iterações;
- margem das restrições.

O simplex é determinístico: parte da ração anterior, ou dos limites dos
alimentos escalados até o DMI exigido, e os níveis de consumo testados são
fixos. Não há sorteio. O `RationOptimizer` original do RuFaS, ao contrário, usa
um ponto inicial aleatório sem semente fixa quando não existe uma ração
anterior. Isso explica por que duas execuções do SLSQP podem ter trajetórias e
resultados diferentes. Para comparar métodos, repita o SLSQP com várias
sementes/execuções e informe a variação observada.

## Preços reais e fazendas de teste

Esta seção descreve os dados usados na comparação econômica final. Ela separa
três etapas que podem ser conferidas de forma independente:

1. **a conversão dos preços** para a unidade usada pelo RuFaS;
2. **a montagem das fazendas** a partir dos exemplos do próprio RuFaS;
3. **a execução e a leitura dos resultados**.

### Unidade dos preços

O custo da ração no RuFaS é `soma(preco_i * x_i)`, e `x_i` está em kg de
**matéria seca** (MS). Portanto, `preco_i` precisa estar em R$ por kg de MS. As
fontes, porém, publicam o preço na **matéria natural** (o alimento como é
vendido, com água). A conversão usa a coluna `DM` da biblioteca
`NASEM_Comp_with_TDN.csv`:

```text
R$/kg MS = (R$/kg na matéria natural) / (MS% / 100)
```

Exemplo: silagem de milho a R$ 0,35/kg com 35,4% de MS custa
`0,35 / 0,354 = R$ 0,99/kg MS`. Sem essa conversão, os volumosos pareceriam
até três vezes mais baratos e o otimizador encheria a ração com eles. O leite
usa `R$/kg = R$/litro / 1,032`, a densidade do leite.

### Cenários de preço (`scenarios/precos/`)

| Arquivo | Conteúdo |
|---|---|
| `goias-2026-11.json` | leite e milho do CEPEA, farelo de Rio Verde (GO) e três alimentos de uma fazenda de Goiás |
| `planilha-2026.json` | 127 alimentos da planilha de preços montada pela turma, com os preços de Goiás onde existem |
| `planilha-2026.csv` | uma linha por item da planilha: preço, MS, R$/kg MS, fonte, status e o tratamento dado |
| `converter_planilha.py` | gera o CSV e o JSON a partir da planilha `.xlsx` |
| `sensibilidade.py` / `.md` | re-solução com ±10% e ±20% no preço dos ingredientes principais |

Os dois JSON podem ser importados na interface (**Importar**). O
`converter_planilha.py` faz, além da conversão de unidade, quatro ajustes, todos
registrados na coluna `tratamento` do CSV:

- usa os preços de Goiás no milho, farelo, silagem, caroço, casca de soja e
  leite, por serem regionais e mais recentes;
- corrige o premix (300) para R$ 5,00/kg, valor **provisório**, porque o proxy
  da planilha era um núcleo probiótico de R$ 149,99/kg;
- ignora o bagaço de maçã (3), porque o preço é do produto seco e a entrada da
  biblioteca é a úmida;
- põe um teto prático de 0,3, 0,15 e 0,2 kg MS/dia em calcário, sal e premix.

O teto existe porque o RuFaS não tem uma restrição de máximo para minerais. Com
o calcário a R$ 0,10/kg, os otimizadores chegaram a usar de 4 a 7 kg/dia,
como enchimento barato de matéria seca. Isso é uma propriedade do modelo, não
um erro de conta, e o teto é uma premissa que pode ser alterada na página.

Para refazer a conversão quando a planilha for atualizada:

```powershell
.venv\Scripts\python scenarios\precos\converter_planilha.py "caminho\Preços de ingredientes para nutrição de vacas (R$ kg).xlsx"
```

### Fazendas de teste (`scenarios/fazendas/`)

O professor não vai enviar fazendas. A comparação usa, então, os exemplos que
vêm com o próprio RuFaS, sem editar a pasta `RufSas/RuFaS`:
`scenarios/fazendas/gerar.py` lê os arquivos de exemplo e grava cópias
modificadas em `scenarios/fazendas/<rebanho>-<região>/`.

- **Rebanhos:** `example_freestall_animal.json` (100 vacas) e
  `example_open_lot_animal.json` (1.000 vacas).
- **Listas de alimentos:** `example_{Midwest,Intermountain,Northeast,Southwest}_feed.json`.
  São 2 rebanhos × 4 listas = 8 fazendas.
- **Mudanças em relação ao exemplo:**
  - só animais, um ano (2013), como `scenarios/smoke`;
  - `ration.user_input: false`, para a ração ser formulada pelo otimizador;
  - `purchased_feed_cost` com os preços de `planilha-2026.json`.

Cinco alimentos dessas listas não têm preço na planilha: o concentrado de
bezerra (216) e as misturas de subprodutos `Farm ES ... BP Blend` (302–305).
Para eles o gerador usa o **método de Petersen**: o preço é o valor da energia e
da proteína, calculado a partir do milho (44) e do farelo de soja (167), que
têm preço de mercado. Resolvendo o sistema 2 × 2:

```text
preco = a * NEL + b * PB
preco_milho  = a * NEL_milho  + b * PB_milho
preco_farelo = a * NEL_farelo + b * PB_farelo
NEL = 0,0245 * NDT - 0,12      (Mcal/kg MS)
```

O concentrado de bezerra vem com NDT = 0 na biblioteca; o gerador assume 80%,
valor típico de concentrado inicial. O exemplo Northeast do RuFaS também traz o
alimento 176 repetido, e o próprio RuFaS recusa o arquivo
(`ValueError: ... repeated feed_type entries`). O gerador mantém uma entrada só.

### Execução e resultado

```powershell
.venv\Scripts\python scenarios\fazendas\gerar.py
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\fazendas\freestall-midwest\task_manager_metadata.json -o results\fazendas\freestall-midwest\
.venv\Scripts\python -m addon_rufas.summarize results\fazendas\freestall-midwest
```

No modo `compare`, o simplex conduz a simulação e o SLSQP resolve em sombra o
mesmo problema, então cada linha do resultado é um par com entradas idênticas.
Nas 8 fazendas foram 312 pares (13 formulações por lote × 3 lotes × 8):

- o simplex formulou com sucesso em 100% dos casos; o SLSQP falhou em 2
  (openlot-midwest);
- nenhuma re-tentativa, corte de leite ou ração de fallback;
- nas seis fazendas não Midwest, os dois chegaram à mesma ração;
- nas duas fazendas Midwest, o simplex ficou mais caro na lactação: 0,60% na
  freestall (11 de 39 pares acima de 0,1%, o pior com 1,08%) e 0,31% na open
  lot (9 de 39). Isso dá cerca de R$ 7 mil/ano no rebanho de 100 vacas e
  R$ 31 mil/ano no de 1.000. A causa é a troca entre grão e silagem, descrita
  em [Limite do método](#limite-do-método).

Na fazenda de exemplo do RuFaS (preços genéricos), o simplex foi mais barato
em 6 de 39 pares. O tempo por formulação foi de 23 a 52 ms no simplex e de 10 a
73 ms no SLSQP.

A tabela por fazenda está em
[`scenarios/fazendas/README.md`](scenarios/fazendas/README.md), e a análise, no
[relatório](docs/RELATORIO.md).

## Preservação do RuFaS

Os arquivos em `RufSas/RuFaS` são usados como referência e continuam sem
alterações. O frontend está em `addon_rufas/web.py`, seus arquivos visuais
estão em `addon_rufas/templates/` e `addon_rufas/static/`, e a escolha do
otimizador ocorre apenas em tempo de execução.

## Dados da vaca e cálculo das exigências

A interface possui duas tabelas relacionadas:

1. **Dados da vaca**: valores biológicos editáveis, como peso, dias em
   lactação, produção de leite, composição do leite, gestação e distância
   percorrida.
2. **Exigências nutricionais usadas nas restrições**: valores efetivamente
   passados ao `NutritionRequirements` do otimizador. Eles podem ser editados
   manualmente.

Depois de editar os dados da vaca, use **Calcular exigências NASEM**. Essa ação
chama a calculadora original do RuFaS e copia o resultado para a segunda
tabela. Depois ainda é possível ajustar manualmente qualquer exigência antes
de executar a formulação.

O caminho da calculadora original é:

```text
RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py
NASEMRequirementsCalculator.calculate_requirements(...)
```

O método principal delega os cálculos para estas funções da mesma classe:

| Resultado mostrado na interface | Função original do RuFaS |
|---|---|
| Energia de manutenção | `_calculate_maintenance_energy_requirements` |
| Energia de crescimento | `_calculate_growth_energy_requirements` |
| Energia de gestação | `_calculate_pregnancy_energy_requirements` |
| Energia de lactação | `_calculate_lactation_energy_requirements` |
| Matéria seca/DMI | `_calculate_dry_matter_intake` |
| Proteína metabolizável | `_calculate_protein_requirement` |
| Cálcio | `_calculate_calcium_requirement` |
| Fósforo | `_calculate_phosphorus_requirement` |
| Energia de atividade | `_calculate_activity_energy_requirements` |
| Aminoácidos essenciais | `AminoAcidCalculator.calculate_essential_amino_acid_requirements` |

O RuFaS monta essa chamada em:

```text
RUFAS/biophysical/animal/animal.py
Animal.calculate_nutrient_requirements(...)
```

Na interface deste add-on, são usados os seguintes parâmetros para a
calculadora:

- `AnimalType` pela categoria: `LAC_COW` (lactação), `DRY_COW` (seca) ou
  `HEIFER_I`/`HEIFER_II` (novilha não gestante/gestante), e o lote
  `AnimalCombination` correspondente: `LAC_COW`, `CLOSE_UP` ou `GROWING`,
  como em `animal_grouping_scenarios.py`;
- `housing` escolhido na página (`"Barn"` ou `"Grazing"`);
- `lactating` verdadeiro só na lactação (nas outras, produção de leite 0);
- ganho médio diário em **kg/dia** (a docstring do RuFaS diz gramas, mas a
  equação usa kg/dia);
- FDN anterior informado pelo usuário;
- fósforo do processo calculado pelo módulo de fósforo do RuFaS;
- aminoácidos calculados pelo RuFaS, embora a formulação atual não exponha
  restrições individuais para cada aminoácido.

Assim, o fluxo verificável cálculo a cálculo é:

```text
dados da vaca
  -> NASEMRequirementsCalculator.calculate_requirements
  -> funções privadas de cada nutriente
  -> NutritionRequirements
  -> RationOptimizer / SimplexRationOptimizer
  -> restrições da dieta
```

## Origem e linearidade das restrições

Esta seção distingue duas coisas que são importantes para a avaliação:

1. **a expressão implementada pela função original do RuFaS**; e
2. **a forma que pode ser usada no LP**, depois de uma transformação algébrica
   exata ou de uma aproximação local.

A variável de decisão é `x_i`, a quantidade em kg de matéria seca do alimento
`i`. O RuFaS registra todas as restrições como desigualdades do SciPy no formato
`g(x) >= 0`: uma restrição é atendida quando sua margem é não negativa. A lista
exata de funções é montada em `RationOptimizer.set_constraints`, separada entre
as listas NRC e NASEM.

| Restrição | Função de origem no RuFaS | Expressão original | Classificação da função original | Forma usada no LP |
|---|---|---|---|---|
| Energia total | `NE_total_constraint` | `max(oferta_manutencao, oferta_crescimento, oferta_lactacao) - requisito_total` | **Não linear** | Não usada: só existe no padrão NRC. |
| Energia de manutenção e atividade | `NE_maintenance_and_activity_constraint` | `oferta_manutencao(x) - (requisito_manutencao + atividade)` | **Não linear** | Não usada: só existe no padrão NRC. |
| Energia de lactação | `NE_lactation_constraint` | `oferta_lactacao(x) - (requisito_lactacao + gestacao)` | **Não linear** | Não usada: só existe no padrão NRC. |
| Energia de crescimento | `NE_growth_constraint` | `oferta_crescimento(x) - requisito_crescimento` | **Não linear** | Não usada: só existe no padrão NRC. |
| Energia líquida NASEM | `NASEM_net_energy_constraint` | `eficiência * energia_metabolizável_NASEM(x) - requisito_total` | **Não linear** | Linear com DMI e amido fixados na ração atual; recalculados a cada rodada. |
| Cálcio | `calcium_constraint` | `soma(x_i * Ca_i * digestibilidade_i) - requisito_Ca` | **Linear** | Já é uma soma linear; entra diretamente no LP. |
| Fósforo | `phosphorus_constraint` | `soma(x_i * P_i * digestibilidade_i) - max(requisito_NASEM, requisito_processo)` | **Linear** | Já é uma soma linear; entra diretamente no LP. |
| Proteína metabolizável mínima | `protein_constraint_lower` | `oferta_proteina_metabolizavel(x) - requisito_proteina` | **Não linear** | Duas linhas (uma por ramo do `min()`), com DMI, % de concentrado e desconto do NDT fixados na ração atual. |
| Proteína metabolizável máxima | `protein_constraint_upper` | `fator_superior * requisito_inicial - oferta_proteina_metabolizavel(x)` | **Não linear** | Uma linha, com o ramo do `min()` que é o menor na ração atual. |
| FDN mínima | `NDF_constraint_lower` | `soma(x_i*NDF_i)/soma(x_i) - limite_minimo` | **Não linear como função escrita** | Transformação algébrica exata para `soma(x_i*NDF_i) - limite_minimo*soma(x_i) >= 0`, desde que DMI seja positivo. |
| FDN máxima | `NDF_constraint_upper` | `limite_maximo - soma(x_i*NDF_i)/soma(x_i)` | **Não linear como função escrita** | Transformação algébrica exata para `limite_maximo*soma(x_i) - soma(x_i*NDF_i) >= 0`, desde que DMI seja positivo. |
| FDN de forragem mínima | `forage_NDF_constraint` | `100*soma(x_i*FDN_foragem_i)/soma(x_i) - limite_minimo` | **Não linear como função escrita** | Transformação algébrica exata para uma soma linear, desde que DMI seja positivo. |
| Gordura máxima | `fat_constraint` | `limite_gordura - soma(x_i*EE_i)/soma(x_i)` | **Não linear como função escrita** | Transformação algébrica exata para `limite_gordura*soma(x_i) - soma(x_i*EE_i) >= 0`, desde que DMI seja positivo. |
| Matéria seca mínima | `DMI_constraint_lower` | `soma(x_i) - DMI_minimo` | **Linear** | Já é uma soma linear; entra diretamente no LP. |
| Matéria seca máxima | `DMI_constraint_upper` | `DMI_maximo - soma(x_i)` | **Linear** | Já é uma soma linear; entra diretamente no LP. |

### O que é realmente linear e o que não é

As restrições de cálcio, fósforo e DMI são lineares tanto na função original
quanto no LP. Para elas, cada alimento fornece um coeficiente fixo e a oferta é
simplesmente o produto desse coeficiente por `x_i`, somado entre os alimentos.
Os limites mínimo e máximo dos alimentos também são lineares e aparecem como
`lower_i <= x_i <= upper_i`.

FDN, FDN de forragem e gordura merecem uma observação mais cuidadosa. O código
do RuFaS calcula suas porcentagens dividindo uma soma pelo DMI; portanto, a
**função Python** contém uma divisão por `soma(x_i)` e não é linear. Entretanto,
os limites são constantes e o DMI é positivo em uma ração válida. Multiplicar
cada desigualdade pelo DMI não muda o seu sentido e elimina o denominador.
Assim, a região viável dessas quatro restrições é exatamente representável por
uma desigualdade linear. A tabela chama isso de “transformação algébrica
exata”, e não de aproximação numérica. É essa forma que o simplex usa.

O add-on usa só o padrão **NASEM**. As quatro restrições de energia do padrão
NRC aparecem na tabela por completude, mas o `SimplexRationOptimizer` recusa um
problema NRC. As fazendas de teste e a página usam NASEM.

As restrições de energia e proteína são não lineares de fato. Exemplos da
origem dessa não linearidade são:

- o desconto de TDN/DE depende do TDN percentual e do DMI;
- a energia de manutenção contém termos quadrático e cúbico da energia
  metabolizável de cada alimento;
- a energia de crescimento contém o quadrado da energia metabolizável;
- a energia NASEM depende do DMI, do peso corporal e do amido total; ao
  multiplicar esses valores pela quantidade dos alimentos aparecem produtos
  entre variáveis;
- a proteína metabolizável usa percentuais de concentrado, taxas de passagem
  dependentes do DMI e do peso e `min(proteina_microbial_por_TDN,
  proteina_microbial_por_RDP)`.

### Linearização usada pelo simplex, passo a passo

O `SimplexRationOptimizer` (`addon_rufas/simplex_ration_optimizer.py`) herda do
`RationOptimizer` a configuração, os limites, a lista de restrições NASEM e as
próprias funções `fun`. Ele só intercepta a chamada ao
`scipy.optimize.minimize`: em vez de executar o SLSQP, monta um problema linear
no PuLP e o resolve pelo **método simplex** do HiGHS
(`pulp.HiGHS(solver="simplex")`). Não usa derivada, gradiente nem diferença
finita.

A ideia parte de uma propriedade verificável no código do RuFaS: toda oferta
NASEM é uma soma, alimento por alimento, de **quantidade × valor por kg**. O
que torna a conta não linear são poucos números que dependem da ração inteira:

| Número da ração inteira | Onde o RuFaS usa |
|---|---|
| consumo de matéria seca (DMI) | digestibilidade da FDN e do amido, taxas de passagem, proteína endógena |
| amido total | digestibilidade da FDN (`calculate_NASEM_dNDF`) |
| % de concentrado | taxas de passagem da proteína (`_calculate_protein_passage_rates`) |
| desconto do NDT por consumo | proteína microbiana (`calculate_nutrient_intake_discount`) |

Se esses números forem **fixados** com os valores de uma ração conhecida, o
valor por kg de cada alimento vira uma constante, e cada restrição vira uma
desigualdade linear. O algoritmo é:

```text
1. ração = ponto inicial (ração anterior, ou limites escalados até o DMI)
2. calcula DMI, amido, % de concentrado e desconto do NDT com essa ração
3. monta o PL com esses números fixos e resolve pelo simplex
4. se a ração nova é igual à anterior (diferença < 1e-6 kg), terminou
5. senão, ração = ração nova e volta ao passo 2 (no máximo 20 rodadas)
```

Quando a ração para de mudar, os números fixados são exatamente os da ração
final. Nesse ponto o PL e o modelo não linear do RuFaS dão a mesma oferta. Nos
testes, isso acontece em 3 a 11 rodadas; quando chega ao limite de 20, vale a
melhor ração viável encontrada.

#### Níveis de consumo

O consumo de matéria seca muda o valor por kg de todos os alimentos (a
digestibilidade da fibra e do amido e as taxas de passagem caem quando a vaca
come mais). Com o consumo fixado em cada rodada, o simplex não enxerga esse
efeito e tende a parar sempre perto do consumo de partida. Por isso o
`_solve` repete o procedimento seis vezes e fica com a ração viável mais
barata:

```text
1 vez com o consumo livre (entre o mínimo e o máximo do RuFaS)
5 vezes com o consumo fixado (soma(x_i) = DMI_k), em 5 níveis igualmente
  espaçados entre o DMI mínimo e o máximo do RuFaS
```

#### Limite do método

Fixar os números da ração inteira deixa o método simples, mas tem um custo. O
PL não vê que **trocar um alimento muda o valor por kg dos outros**. Por
exemplo, trocar silagem de milho por milho grão aumenta o amido e a fração de
concentrado. Isso reduz a digestibilidade da fibra e muda a passagem da
proteína de todos os alimentos. Com os números fixos, o grão parece mais barato
do que é; ao recalcular os números, a ração não fecha a proteína e a energia, e
a iteração para num ponto em que o grão continua na ração.

Na prática, o simplex pode parar numa ração viável um pouco mais cara que a
do SLSQP quando a escolha é entre grão e silagem. Os números estão em
[Execução e resultado](#execução-e-resultado). Um método que enxerga essas
interações precisa das derivadas das funções do RuFaS (o SLP da branch
`integracao-rufas` fazia isso por diferenças finitas).

Os valores por kg não são reescritos à mão: o código chama as funções de oferta
do próprio RuFaS para 1 kg de cada alimento (`_rows`), por exemplo
`calculate_NASEM_digestible_energy([1 kg do alimento], DMI, peso, amido)`.

#### As linhas do PL

Cada linha corresponde a uma restrição de `RationOptimizer.set_constraints`:

| Restrição do RuFaS | Linha do PL (`soma(coef_i * x_i) >= limite`) |
|---|---|
| `calcium_constraint` | Ca absorvível por kg × `x_i` ≥ exigência de Ca |
| `phosphorus_constraint` | P absorvível por kg × `x_i` ≥ maior exigência de P |
| `protein_constraint_lower` | **duas linhas**, uma para cada ramo do `min()` (abaixo) |
| `protein_constraint_upper` | proteína pelo ramo que é o menor na ração atual ≤ limite superior |
| `NDF_constraint_lower` / `upper` | `soma(x_i * (FDN_i - mínimo)) >= 0` e `soma(x_i * (máximo - FDN_i)) >= 0` |
| `forage_NDF_constraint` | `soma(x_i * (FDN_forragem_i - mínimo)) >= 0` |
| `fat_constraint` | `soma(x_i * (máximo - EE_i)) >= 0` |
| `DMI_constraint_lower` / `upper` | `soma(x_i)` entre os dois limites |
| `NASEM_net_energy_constraint` | eficiência × (energia digestível por kg × `x_i` − perdas de gás e urina) ≥ exigência |

A proteína metabolizável do RuFaS é
`0,64 × min(microbiana_por_NDT, microbiana_por_PDR) + PNDR digestível + 4,72 g/kg MS`.
O `min()` parece não linear, mas `min(a, b) >= R` é o mesmo que `a >= R` **e**
`b >= R`. Por isso ele vira duas linhas lineares, sem aproximação.

As linhas de FDN, FDN de forragem e gordura são as restrições do RuFaS
multiplicadas pelo DMI, que é positivo. É uma transformação exata, como
explicado na seção anterior.

#### Quando o PL não tem solução

Com os números fixados numa ração ruim, por exemplo o ponto inicial, o PL pode
não ter solução mesmo que exista uma ração viável. Nesse caso o código usa a
**fase 1 do simplex**: acrescenta uma folga `s_j >= 0` a cada linha e minimiza
a soma das folgas relativas:

```text
minimizar soma(s_j / max(1, |limite_j|))
sujeito a soma(coef_ji * x_i) + s_j >= limite_j
```

O resultado é a ração que menos deixa de cumprir as exigências. Os números são
recalculados com ela, e a rodada seguinte volta ao PL de custo. Se nem assim
existe ração, o otimizador devolve `success=False`, e o RuFaS faz as
re-tentativas dele.

#### Verificação final

O sucesso não é deduzido do PL. Cada ração do simplex é avaliada pelas funções
originais do RuFaS, e só conta como viável se **todas** derem `>= 0`, a mesma
checagem que o RuFaS faz (`is_constraint_violated`). Para não falhar por
arredondamento, cada linha pede uma folga relativa de `1e-5` acima da
exigência. O otimizador devolve a ração viável mais barata encontrada.

## Origem dos nomes dos alimentos

Os nomes exibidos na interface não são inventados pelo add-on nem vêm do ID.
Eles são lidos da coluna `Name` da biblioteca NASEM do RuFaS:

```text
RufSas/RuFaS/input/data/feed/NASEM_Comp_with_TDN.csv
```

O carregamento ocorre em `addon_rufas.web._feed_config`:

1. `csv.DictReader` lê todas as linhas do CSV e usa a primeira linha como
   cabeçalho;
2. cada coluna vira uma lista, e a coluna `rufas_id` é convertida para
   inteiros;
3. a biblioteca é indexada pelo `rufas_id`;
4. o add-on passa essa biblioteca para o `AvailableFeedsBuilder` original do
   RuFaS, que cria os objetos `Feed`/`NASEMFeed` com composição, categoria,
   limites e custos;
5. separadamente, o add-on cria
   `FEED_NAMES = dict(zip(library["rufas_id"], library["Name"]))`;
6. ao preparar a página, cada alimento procura seu nome por ID:
   `FEED_NAMES.get(feed.rufas_id, f"Feed {feed.rufas_id}")`.

O arquivo `example_Midwest_feed.json` não fornece os nomes. Ele fornece quais
IDs estão inicialmente configurados na fazenda, além de custos e limites. Por
isso, a interface consegue mostrar a biblioteca completa de alimentos NASEM,
mas começa com os IDs configurados nesse JSON selecionados. A busca também
usa esse mesmo cadastro: procura pelo nome da coluna `Name`, pelo ID e pela
categoria carregada no objeto `Feed`.

## Exemplo final: executar o código

Na raiz do repositório, com o RuFaS disponível em `RufSas/RuFaS`:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=RufSas/RuFaS .venv/bin/python -m addon_rufas.web
```

No Windows PowerShell, use:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONPATH="RufSas/RuFaS"
.venv\Scripts\python -m addon_rufas.web
```

Depois, abra `http://127.0.0.1:5000`. Para executar a comparação da simulação:

```bash
.venv/bin/python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios/smoke/task_manager_metadata.json
.venv/bin/python -m addon_rufas.summarize results/compare
```
