# Addon-RufSas

Add-on de otimização de dieta para o [RuFaS](https://github.com/RuminantFarmSystems/RuFaS). Ele traz três
otimizadores para o mesmo problema de formulação:

| Otimizador | O que é |
|---|---|
| **SLSQP** | O original do RuFaS (`RationOptimizer`), a linha de base. |
| **SLP** | `addon_rufas/linear_ration_optimizer.py`: programação linear sequencial com HiGHS sobre as próprias restrições do RuFaS. Substitui o SLSQP dentro da simulação. É determinístico, nunca ficou mais caro e é 2 a 3 vezes mais rápido. |
| **NRC clássico (PuLP)** | `addon_rufas/nrc_lp.py`: PL linear do NRC 2001 com energia, PDR, PNDR, proteína metabolizável, FDN, minerais e vitaminas, e preços-sombra. |

O RuFaS **não é editado**: o add-on se liga a ele por subclasse e troca do
otimizador em tempo de execução.

- **Documentação da implementação** (modelo, integração, sensibilidade, análise
  econômica, CEPEA, testes, limitações): [`docs/DOCUMENTACAO.md`](docs/DOCUMENTACAO.md)
- Escopo e plano de entregas: [`addon-rufas-otimizacao-dieta.md`](addon-rufas-otimizacao-dieta.md)
- Notas dos livros NRC 2001 e NASEM 2021: [`docs/notas-livros.md`](docs/notas-livros.md)

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
.venv\Scripts\python -m addon_rufas.web
```

```bash
# Linux/macOS
python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m addon_rufas.web
```

Abra `http://127.0.0.1:5000`. Testes: `.venv\Scripts\python -m pytest`.

## Simulação da fazenda (SLSQP × SLP)

```powershell
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\smoke\task_manager_metadata.json
.venv\Scripts\python -m addon_rufas.summarize results\compare
```

`--optimizer slsqp | lp | compare`. No modo `compare`, o SLP conduz a simulação
e o SLSQP resolve o mesmo problema em sombra a cada formulação, o que dá pares
comparáveis. Para usar outra fazenda, troque o `-p`. Preços reais: veja a seção 7
da [documentação](docs/DOCUMENTACAO.md#7-preços-reais-cepea).

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

Prefira o SLP ou o modelo NRC para essa análise. O SLSQP do RuFaS parte de um
ponto aleatório, e parte da diferença entre as duas formulações pode ser ruído.
No modelo NRC, a tabela de margens também mostra o **preço-sombra** de cada
restrição: quanto o custo sobe se a exigência subir 1 unidade.

### Cenários em JSON

**Exportar** baixa a página inteira em `cenario.json`: categoria, alojamento,
dados da vaca, exigências, alimentos marcados (`selected_feeds`), preços
(`cost_<id>`) e limites (`min_<id>`, `max_<id>`). **Importar** carrega um arquivo
desses. O arquivo pode ter só parte dos campos; o resto fica no padrão. Exemplo:

```json
{"category": "seca", "housing": "Grazing", "cow_body_weight": 700, "selected_feeds": [44, 104]}
```

Campos desconhecidos são recusados, para que um erro de digitação não passe em
silêncio.

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

### Programação linear sequencial (SLP)

Seleciona `Programação linear sequencial (SLP)` e usa:

```text
addon_rufas.linear_ration_optimizer.LinearRationOptimizer
scipy.optimize.linprog (HiGHS)
```

O add-on lineariza as restrições do RuFaS em cada passo, resolve um problema
linear e repete os passos até obter uma ração viável. Esse é o otimizador
criado pelo projeto do add-on.

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

O SLP é determinístico porque o add-on define um ponto inicial determinístico.
O `RationOptimizer` original do RuFaS usa um ponto inicial aleatório quando não
existe uma ração anterior. Por isso, pequenas diferenças entre execuções do
SLSQP podem ocorrer e fazem parte do comportamento original.

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
  -> RationOptimizer / LinearRationOptimizer
  -> restrições da dieta
```

## Origem e linearidade das restrições

As restrições abaixo são as que o método original do RuFaS (`RationOptimizer`)
monta para a formulação. A coluna **Linearidade no RuFaS** descreve a função
original, antes da substituição do SLSQP pelo SLP.

| Restrição | Função de origem no RuFaS | Linearidade no RuFaS | Explicação |
|---|---|---|---|
| Energia total | `NE_total_constraint` | Não linear | Calcula energia de manutenção, crescimento e lactação e aplica `max`; a oferta depende de energia digestível/metabolizável. |
| Energia de manutenção e atividade | `NE_maintenance_and_activity_constraint` | Não linear | A exigência é fixa, mas a oferta passa pelas taxas de desconto e conversão de energia do RuFaS. |
| Energia de lactação | `NE_lactation_constraint` | Não linear | Usa energia digestível e metabolizável, com conversões dependentes da composição e da ingestão. |
| Energia de crescimento | `NE_growth_constraint` | Não linear | Usa a conversão de energia para crescimento sobre a energia metabolizável calculada para a ração. |
| Energia líquida NASEM | `NASEM_net_energy_constraint` | Não linear | O desconto de ingestão e a energia metabolizável NASEM dependem da ração, do peso, do amido, do metano e do nitrogênio urinário. |
| Cálcio | `calcium_constraint` | Linear | Soma, alimento a alimento, quantidade, teor de cálcio e digestibilidade fixa por tipo de alimento. |
| Fósforo | `phosphorus_constraint` | Linear | Soma o fósforo digestível de cada alimento e compara com o maior requisito NASEM ou do processo. |
| Proteína metabolizável mínima | `protein_constraint_lower` | Não linear | A produção de proteína microbiana usa `min` entre duas fontes e as taxas de passagem dependem da ingestão e da composição. |
| Proteína metabolizável máxima | `protein_constraint_upper` | Não linear | Usa a mesma oferta não linear da proteína metabolizável, limitada por um fator do requisito inicial. |
| FDN mínima | `NDF_constraint_lower` | Linear equivalente | A origem calcula uma proporção dividindo FDN pela matéria seca; como o limite é constante, é equivalente a `soma(FDN_i*x_i) - limite*soma(x_i) >= 0`. |
| FDN máxima | `NDF_constraint_upper` | Linear equivalente | A proporção original pode ser multiplicada pela matéria seca positiva, resultando em uma desigualdade linear. |
| FDN de forragem mínima | `forage_NDF_constraint` | Linear equivalente | Também é uma proporção da ração; o numerador é uma soma linear de FDN de forragem e o denominador é a matéria seca. |
| Gordura máxima | `fat_constraint` | Linear equivalente | A porcentagem de gordura é uma razão entre duas somas; multiplicar pelo DMI transforma a condição em soma linear. |
| Matéria seca mínima | `DMI_constraint_lower` | Linear | É diretamente a soma das quantidades dos alimentos menos o requisito mínimo ajustado. |
| Matéria seca máxima | `DMI_constraint_upper` | Linear | É diretamente o limite máximo menos a soma das quantidades dos alimentos. |

### Como o SLP lineariza as restrições não lineares

O `LinearRationOptimizer` não reimplementa as equações NASEM/NRC nem troca as
funções do RuFaS. Em cada iteração, ele avalia cada restrição original
`g(x)` no ponto atual `x` e calcula numericamente o jacobiano por diferenças
finitas, usando `h = 1e-4 * max(1, x_i)`:

```text
g(x + h*e_i) - g(x)
J_i = --------------------
           h
g_linear(z) = g(x) + J * (z - x)
```

O HiGHS resolve essa aproximação como um LP dentro de uma região de confiança.
O ponto candidato é aceito somente quando reduz o custo com penalidade pelas
violações; então a região pode ser reduzida e o processo se repete. Assim, as
funções não lineares (`NE_*`, NASEM e proteína metabolizável) são aproximadas
localmente, enquanto a avaliação final continua usando as funções originais do
RuFaS. Há ainda uma etapa de restauração que reaplica as linearizações até que
as restrições não lineares originais sejam satisfeitas.

## Exemplo final: executar o código

Na raiz do repositório, com o RuFaS disponível em `RufSas/RuFaS`:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m addon_rufas.web
```

No Windows PowerShell, use:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m addon_rufas.web
```

Depois, abra `http://127.0.0.1:5000`. Para executar a comparação da simulação:

```bash
.venv/bin/python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios/smoke/task_manager_metadata.json
.venv/bin/python -m addon_rufas.summarize results/compare
```
