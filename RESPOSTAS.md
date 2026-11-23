# Respostas sobre o projeto Add-on RuFaS

Este documento explica o projeto a partir do código atual. Os comandos assumem a raiz deste repositório.

## Leitura rápida

- **RuFaS original:** fornece a integração, os dados dos alimentos, as exigências NASEM, o SLSQP e as restrições originais.
- **SLP:** usa os dados e as restrições originais do RuFaS, mas troca o SLSQP por programação linear sequencial com HiGHS.
- **NRC clássico em PuLP:** é um modelo linear próprio do projeto, separado do SLP. Ele usa dados da biblioteca NASEM/RuFaS e equações clássicas NRC 2001.
- **Não modificar:** [RufSas/RuFaS](RufSas/RuFaS). Todo o código novo está em [addon_rufas](addon_rufas).

---

## 1. O que é a biblioteca NASEM e onde ela está

A biblioteca está em:

- [RufSas/RuFaS/input/data/feed/NASEM_Comp_with_TDN.csv](RufSas/RuFaS/input/data/feed/NASEM_Comp_with_TDN.csv)

Ela contém **175 linhas de alimentos** e dezenas de colunas de composição. Cada linha tem um `rufas_id`, o nome (`Name`), a categoria (`Fd_Category`), o tipo usado pelo RuFaS (`feed_type`) e dados como:

- matéria seca (`DM`);
- proteína, RUP, PDR, digestibilidade;
- fibras e amido;
- TDN;
- cálcio, fósforo e minerais;
- vitaminas;
- aminoácidos;
- limites mínimo e máximo;
- indicadores como `is_fat` e `is_wetforage`.

O projeto usa essa biblioteca para:

1. listar os nomes e os alimentos disponíveis;
2. fornecer a composição nutricional;
3. fornecer a categoria do alimento: forragem, concentrado ou mineral;
4. fornecer limites originais;
5. fornecer TDN, proteína, FDN, gordura, cálcio, fósforo, minerais e vitaminas;
6. carregar objetos `Feed` pelo RuFaS.

O arquivo CSV contém dados e coeficientes, não as equações das exigências. As equações estão no código original do RuFaS.

Responsabilidades principais:

- leitura do CSV: [addon_rufas/web.py](addon_rufas/web.py), funções `_feed_config`, `load_feeds`;
- nomeação dos 175 alimentos: constantes `FEED_NAMES` e `LIBRARY_ROWS`;
- construção dos objetos `Feed`: `AvailableFeedsBuilder.setup_available_feeds`;
- seleção dos 10 alimentos fictícios inicialmente marcados: [RufSas/RuFaS/input/data/feed/example_Midwest_feed.json](RufSas/RuFaS/input/data/feed/example_Midwest_feed.json).

O prefixo **NASEM** significa `National Academies of Sciences, Engineering, and Medicine`, cuja oitava edição das exigências de vacas leiteiras foi publicada em 2021. Neste projeto, ele é usado principalmente para calcular exigências e suprimento no fluxo original do RuFaS.

Relacionados:

- item **8**: diferença entre NRC e NASEM;
- item **16**: explicação mais detalhada da biblioteca;
- item **1**: já respondeu a pergunta sobre dados da biblioteca.

---

## 2. O que existe em `scenarios` e quais arquivos são usados

### Cenário rápido de execução

Pasta [scenarios/smoke](scenarios/smoke):

- [config.json](scenarios/smoke/config.json): período, sementes e padrão nutricional da simulação;
- [animal.json](scenarios/smoke/animal.json): rebanho, manejo, reprodução e dados dos animais;
- [metadata.json](scenarios/smoke/metadata.json): informa ao RuFaS quais arquivos JSON usar;
- [tasks.json](scenarios/smoke/tasks.json): tarefas e quantidade de trabalhadores paralelos;
- [task_manager_metadata.json](scenarios/smoke/task_manager_metadata.json): aponta para `tasks.json`.

Esses arquivos executam uma simulação curta pelo RuFaS. O arquivo principal para o runner é `task_manager_metadata.json`.

### Fazendas usadas na comparação econômica

Pasta [scenarios/fazendas](scenarios/fazendas).

- [gerar.py](scenarios/fazendas/gerar.py) cria as fazendas;
- existem dois rebanhos: free-stall com 100 vacas e open lot com 1.000 vacas;
- existem quatro regiões: Midwest, Intermountain, Northeast e Southwest;
- o total é 8 fazendas.

Para cada fazenda, são gerados:

- `animal.json`: características do rebanho;
- `config.json`: parâmetros gerais;
- `feed.json`: alimentos disponíveis e preços;
- `metadata.json`: associa os arquivos da fazenda;
- `tasks.json`: define a tarefa de simulação;
- `task_manager_metadata.json`: entrada usada pelo runner.

Eles são usados na execução completa/benchmark comparando SLP e SLSQP.

### Cenários de preços

Pasta [scenarios/precos](scenarios/precos):

- [goias-2026-11.json](scenarios/precos/goias-2026-11.json): alimento selecionado e preços do estado de Goiás;
- [planilha-2026.json](scenarios/precos/planilha-2026.json): preços de 127 dos 175 alimentos;
- [converter_planilha.py](scenarios/precos/converter_planilha.py): converte a planilha da turma de matéria natural para matéria seca;
- [sensibilidade.py](scenarios/precos/sensibilidade.py): gera re-soluções com os preços alterados;
- [sensibilidade.md](scenarios/precos/sensibilidade.md): resultado da sensibilidade;
- [README.md](scenarios/precos/README.md): origem e ressalvas dos preços.

Esses JSON de preços são usados principalmente pela **interface web**, através do botão Importar.

Um arquivo de preços não é uma fazenda. Ele não cria automaticamente o rebanho nem a exigência nutricional; ele substitui o conjunto selecionado, os custos e, às vezes, limites de alimentos no formulário.

Resumo:

- interface/dieta manual: JSON exportado/importado pela própria página;
- interface com dados de outra ferramenta: formato `dietopt-scenario`;
- simulação completa: `scenarios/smoke` ou `scenarios/fazendas`;
- análise econômica: `scenarios/precos`.

---

## 3. Qual é a função objetivo

Em todos os métodos, o objetivo econômico é minimizar:

```text
custo = soma(preço_i × quantidade_i)
```

onde `quantidade_i` está em kg de matéria seca por animal por dia.

No SLSQP e no SLP, o método objetivo herdado do RuFaS está em:

- [RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py](RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py), função `objective`;
- [addon_rufas/linear_ration_optimizer.py](addon_rufas/linear_ration_optimizer.py), usada sem reimplementação no SLP.

No NRC em PuLP, a mesma função objetivo é criada diretamente em [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py), em `solve`.

Mudanças importantes:

- a expressão matemática é a mesma;
- o custo usa R$/kg de matéria seca;
- todos devem retornar uma dieta viável;
- os modelos podem produzir resultados diferentes porque suas variáveis e restrições não são idênticas;
- o modelo NRC pode exigir minerais e vitaminas que não existem no modelo NASEM/SLP/SLSQP da interface.

O IOFC não faz parte da otimização. Ele é calculado depois:

```text
IOFC = receita de leite - custo da dieta
receita de leite = produção de leite × preço do leite
```

A implementação está em [addon_rufas/web.py](addon_rufas/web.py), em `simulate` e `_simulate_nrc`.

---

## 4. Variáveis de decisão e origem

A variável principal já existia no RuFaS:

```text
x_i = quantidade do alimento i na dieta, em kg de matéria seca por dia
```

Ela não é criada a partir da equação de um animal individual. Ela vem da lista de alimentos selecionados pelo usuário ou pela fazenda.

Origem dos valores:

- seleção dos alimentos: campo `selected_feeds`;
- preço: campo `cost_<id>`;
- limite mínimo: campo `min_<id>`;
- limite máximo: campo `max_<id>`;
- composição: biblioteca NASEM;
- exigências: calculadora NASEM do RuFaS;
- alimentos da fazenda: arquivos `feed.json`;
- custo: JSON de preços ou edição manual.

Onde configurar na interface:

- [addon_rufas/web.py](addon_rufas/web.py): `_selected_ids`, `_configured_feeds`, `_requirements`;
- [addon_rufas/templates/index.html](addon_rufas/templates/index.html): formulário dos alimentos;
- [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py): conversão das variáveis para o PuLP.

O SLSQP e o SLP recebem uma variável por alimento. Se há 10 alimentos selecionados, existem até 10 valores `x_i`.

A adição ou remoção de um alimento não altera a equação automaticamente: ela altera a dimensão do vetor de decisão e a composição disponível.

---

## 5. Restrições e origem

### SLSQP e SLP

O SLSQP e o SLP usam as restrições já implementadas no RuFaS.

O conjunto é selecionado em:

- [RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py](RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py), em `set_constraints`;
- `NASEM_constraint_functions`: vacas e novilhas no padrão NASEM;
- `NRC_constraint_functions`: disponível no RuFaS quando o padrão é NRC.

As restrições principais são:

- energia líquida;
- manutenção e atividade;
- lactação;
- crescimento;
- proteína metabolizável mínima e máxima;
- cálcio;
- fósforo;
- FDN mínima e máxima;
- FDN de forragem mínima;
- gordura máxima;
- matéria seca mínima e máxima;
- limites mínimo e máximo de cada alimento.

As funções originais estão no mesmo `ration_optimizer.py`:

- `NE_total_constraint`;
- `NE_maintenance_and_activity_constraint`;
- `NE_lactation_constraint`;
- `NE_growth_constraint`;
- `NASEM_net_energy_constraint`;
- `calcium_constraint`;
- `phosphorus_constraint`;
- `protein_constraint_lower`;
- `protein_constraint_upper`;
- `NDF_constraint_lower`;
- `NDF_constraint_upper`;
- `forage_NDF_constraint`;
- `fat_constraint`;
- `DMI_constraint_lower`;
- `DMI_constraint_upper`.

O modelo não reimplementa as equações no SLP. O SLP chama cada função original e calcula uma aproximação por diferenças finitas.

### Modelo NRC em PuLP

As restrições próprias estão em [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py), em `solve`:

- matéria seca;
- energia líquida de lactação;
- balanço de PDR;
- proteína metabolizável;
- cálcio absorvível;
- fósforo absorvível;
- FDN mínima e máxima;
- FDN de forragem mínima;
- gordura máxima;
- magnésio, potássio, sódio, cloro e enxofre;
- cobalto, cobre, iodo, ferro, manganês, selênio e zinco;
- vitaminas A, D e E;
- limites mínimos e máximos dos alimentos.

As exigências básicas são recebidas em `_simulate_nrc`:

- energia;
- proteína metabolizável;
- cálcio;
- fósforo;
- DMI;
- peso corporal.

Elas vieram da calculadora NASEM da interface, mas o modelo NRC resolve suas próprias restrições adicionais lineares.

---

## 6. Onde adicionar ou remover variáveis e restrições

### Adicionar/remover alimentos

No modelo da interface:

- adicionar um novo alimento marcado: [addon_rufas/web.py](addon_rufas/web.py), `_selected_ids` e `_configured_feeds`;
- alterar preços e limites: campos `cost_<id>`, `min_<id>` e `max_<id>`;
- listar todos os alimentos: biblioteca NASEM.

No modelo NRC:

- o vetor `x` é criado em `nrc_lp.solve`;
- alterar cada variável ou limite exige mudar `solve` e também a tabela da interface.

Não é suficiente editar só o HTML. Os objetos `Feed` são construídos a partir do código Python.

### Adicionar/remover restrições no SLP ou SLSQP

Para usar uma restrição já criada pelo RuFaS:

- adicionar/remover em `set_constraints` no RuFaS;
- porém isso mudaria a cópia referencial do RuFaS.

Neste projeto, a recomendação é manter o RuFaS original e mudar apenas os códigos de seleção específicos do add-on, mas o novo conjunto de restrições do RuFaS precisaria ser integrado pela subclasse.

No SLP, a restrição adicional precisa aparecer em:

- `self.set_constraints`;
- `_select_constraints`;
- uma função `fun(decision_vector, ration_config)`;
- uma caixa de tolerância/normalização para sensibilidade.

Para adicionar uma restrição totalmente nova ao modelo NRC:

- definir o limite padrão em `NRC_DEFAULTS`;
- adicionar o campo em `NRC_FIELDS`;
- calcular os coeficientes por alimento em `solve`;
- adicionar a linha em `rows`;
- testar viabilidade, dual e faixa de validade;
- adicionar o diagnóstico e o nome da coluna em `NRC_SOURCE_COLUMNS`, se necessário.

O melhor arquivo de referência para restrições adicionais é [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py).

### Remover exigências da interface

Os campos exibidos vêm de `REQUIREMENT_FIELDS` em [addon_rufas/web.py](addon_rufas/web.py). Remover apenas da lista não remove a exigência do modelo; ela continuará existindo em `_requirements` ou em `NASEMRequirementsCalculator`.

---

## 7. Como funciona a sensibilidade

Existem dois tipos de sensibilidade no projeto.

### A. Re-solução com variação percentual

Implementação:

- opção disponível na interface em [addon_rufas/web.py](addon_rufas/web.py), função `sensitivity`;
- itens que podem ser alterados em `_sensitivity_options`;
- endpoint em `index`, ação `sensitivity`;
- interface em [addon_rufas/templates/index.html](addon_rufas/templates/index.html).

O cálculo é:

```text
valor_novo = valor_atual × (1 + percentual/100)
```

Depois o código resolve o cenário original e resolve novamente com o novo valor. Não existe derivada matemática implementada pelo add-on nessa análise: são duas formulações reais.

A análise apresenta:

- ração antes;
- ração depois;
- diferença de kg de matéria seca;
- custo antes e depois;
- custo marginal aproximado:

```text
custo_marginal = (custo_novo - custo_antigo) / (valor_novo - valor_antigo)
```

- IOFC antes e depois;
- restrições no limite;
- alimento que entrou, saiu, aumentou ou diminuiu.

Bibliotecas utilizadas:

- SciPy: SLP e SLSQP;
- PuLP + HiGHS: NRC;
- Flask: recebe os dados e chama a função;
- NumPy: vetores e cálculos auxiliares.

### B. Análise clássica do modelo NRC

Implementação em [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py):

- `model.solverModel.getRanging()` lê as informações do HiGHS;
- duais das restrições fornecem os preços-sombra;
- `ranging.row_bound_*` fornece as faixas de validade das exigências;
- `ranging.col_cost_*` fornece faixas de custo dos alimentos;
- `xi.dj` fornece custo reduzido.

Isso é análise fornecida pela teoria da PL e pelo solver. Ela não executa sensibilidade por re-solução em cada intervalo. Ela usa os resultados da solução ótima atual.

Testes:

- preço-sombra: [tests/test_nrc_lp.py](tests/test_nrc_lp.py), `test_shadow_price_is_the_marginal_cost`;
- faixa de exigência e custo dos alimentos: `test_ranging_matches_resolving`;
- botão da página: [tests/test_web.py](tests/test_web.py), `test_sensitivity_explains_the_new_decision`.

---

## 8. NRC: o que é e o que usamos

NRC 2001 é o *Nutrient Requirements of Dairy Cattle* de 2001. Ele traz exigências e modelos tradicionais para vacas leiteiras.

Neste projeto existem dois usos com nomes parecidos:

1. `RationOptimizer` do RuFaS pode selecionar um padrão NRC ou NASEM;
2. o projeto implementou um modelo linear clássico próprio chamado “modelo NRC (PuLP)”.

Eles não são o mesmo código.

### O que usamos do NASEM

- calculadora de exigências em [RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py](RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py);
- biblioteca NASEM;
- restrições originais do RuFaS;
- cálculo de DMI, manutenção, crescimento, gestação, lactação, proteína, cálcio, fósforo e atividade.

### O que usamos do NRC

- equações lineares próprias em [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py);
- NEL aproximada por `0,0245 × TDN - 0,12`;
- PDR, PNDR, proteína metabolizável;
- Tabela 14-7 do NRC 2001 para minerais;
- capítulo 7 para vitaminas;
- coeficientes de absorção usados pela biblioteca do RuFaS.

Há uma simplificação importante:

```text
TDN = valor da biblioteca
```

O modelo não aplica o desconto completo de TDN por nível de consumo usado em algumas equações NRC mais complexas.

---

## 9. Fluxo completo das informações

### Entrada pela interface

O fluxo é:

```text
JSON ou campos do formulário
  -> estado da página
  -> seleção de alimentos e preços
  -> dados biológicos da vaca
  -> cálculo de exigências NASEM ou uso manual
  -> criação de NutritionRequirements
  -> escolha do método
  -> dieta ótima
  -> custo, IOFC e restrições
```

Os pontos de entrada estão em [addon_rufas/web.py](addon_rufas/web.py):

- `GET/POST` em `index`;
- importação em `_imported_form`;
- cálculo em `_calculate_nasem_requirements`;
- solução em `simulate`;
- NRC em `_simulate_nrc`;
- sensibilidade em `sensitivity`.

### Importar dados

O botão Importar aceita:

1. o JSON que a própria página exportou;
2. o mesmo JSON dentro de `{"data": {...}}`;
3. um cenário no formato `dietopt-scenario`.

A conversão `dietopt-scenario` está em `_from_dietopt`.

Campos da página podem ser preenchidos manualmente ou carregados por JSON. Eles não são combinados automaticamente em uma única restrição: o código cria:

- valores numéricos;
- categoria animal;
- alojamento;
- exigências;
- vetores de alimentos;
- limites e custos.

### Escolher SLP

O fluxo é:

```text
dados da página
 -> objetos Feed
 -> NutritionRequirements
 -> RationConfig do RuFaS
 -> restrições e limites originais
 -> linearização local das funções originais
 -> LP com HiGHS
 -> restauração da viabilidade
 -> resultado SLP
```

Implementação: [addon_rufas/linear_ration_optimizer.py](addon_rufas/linear_ration_optimizer.py).

### Escolher SLSQP

O fluxo é:

```text
dados da página
 -> objetos Feed
 -> NutritionRequirements
 -> RationConfig do RuFaS
 -> minimize(method="SLSQP")
 -> solução não linear
```

Implementação original: [RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py](RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py).

### Escolher PuLP NRC

O fluxo é diferente:

```text
dados da página
 -> leitura da composição da biblioteca NASEM
 -> cálculo das exigências básicas pelo NASEM
 -> adição dos limites específicos NRC da aba
 -> transformação em coeficientes lineares
 -> PuLP/HiGHS
 -> dieta ótima clássica NRC
 -> preços-sombra e faixas
```

Por isso o NRC pode não ficar parecido com SLP/SLSQP:

- o SLP/SLSQP usam as restrições e o suprimento do RuFaS;
- o PuLP usa outra formulação;
- o PuLP exige fibra, minerais e vitaminas adicionais;
- o PuLP usa fórmulas NRC simplificadas;
- o conjunto de dados pode ser inviável mesmo quando o SLP e o SLSQP são viáveis.

Isso não atrapalha a comparação econômica se a comparação estiver bem definida. Os objetivos devem ser separados:

- comparar SLP × SLSQP: mesmos dados, mesmas exigências e mesmas restrições RuFaS;
- avaliar NRC: modelo diferente, destacar que é uma formulação alternativa;
- não dizer que os dois são iguais apenas porque usam os mesmos alimentos.

---

## 10. Os três otimizadores devem dar resultados parecidos

Eles podem ser parecidos, mas não devem ser tratados como obrigatoriamente iguais.

Espera-se equivalência mais próxima entre SLSQP e SLP, porque ambos usam as próprias funções de restrição do RuFaS.

O NRC deve ser esperado como uma formulação diferente. Ele pode:

- incluir minerais e vitaminas;
- simplificar energia e proteína;
- impor outros limites;
- produzir outra ração e outro custo.

### Comparar SLP e SLSQP na interface

Selecione o mesmo cenário e execute:

1. `SLSQP`;
2. `SLP`;
3. compare custo, dieta, viabilidade e restrições.

Não altere preços, alimentos ou exigências entre as execuções.

### Comparar SLP e SLSQP em uma fazenda

Gerar a pasta:

```powershell
.venv\Scripts\python scenarios\fazendas\gerar.py
```

Modo pareado:

```powershell
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\fazendas\freestall-midwest\task_manager_metadata.json -o results/fazendas/freestall-midwest
```

Resumir:

```powershell
.venv\Scripts\python -m addon_rufas.summarize results/fazendas/freestall-midwest
```

O modo `compare` usa o SLP para conduzir a simulação e executa o SLSQP como solução sombra para a mesma formulação.

Implementação:

- troca de otimizadores: [addon_rufas/run.py](addon_rufas/run.py);
- pares SLP/SLSQP e tempos: [addon_rufas/instrument.py](addon_rufas/instrument.py);
- criação das fazendas: [scenarios/fazendas/gerar.py](scenarios/fazendas/gerar.py).

Para executar separadamente:

```powershell
.venv\Scripts\python -m addon_rufas.run --optimizer slsqp -g -v errors -p scenarios/smoke/task_manager_metadata.json
.venv\Scripts\python -m addon_rufas.run --optimizer lp -g -v errors -p scenarios/smoke/task_manager_metadata.json
```

### Comparar o NRC

Não existe no runner de simulação atual uma execução automática do NRC junto de SLP e SLSQP. O NRC é executado pela interface em [addon_rufas/web.py](addon_rufas/web.py), com `nrc_lp.solve`.

Para verificações automatizadas:

```powershell
.venv\Scripts\python -m pytest tests/test_linear_ration_optimizer.py tests/test_nrc_lp.py tests/test_web.py
```

Testes específicos:

- viabilidade e custo SLP/SLSQP: [tests/test_linear_ration_optimizer.py](tests/test_linear_ration_optimizer.py);
- modelo NRC e preço-sombra: [tests/test_nrc_lp.py](tests/test_nrc_lp.py);
- integração da página: [tests/test_web.py](tests/test_web.py).

---

## 11. Diferenças entre lactação, seca e novilha

A classificação está em [addon_rufas/web.py](addon_rufas/web.py), constante `CATEGORIES`:

| Categoria | `AnimalType`/`AnimalCombination` | Produção de leite |
|---|---|---|
| Lactação | `LAC_COW` / `LAC_COW` | ativa |
| Seca | `DRY_COW` / `CLOSE_UP` | zero |
| Novilha | `HEIFER_I` ou `HEIFER_II` / `GROWING` | zero |

O código de lactação usa:

- produção de leite;
- gordura e proteína do leite;
- lactose;
- dias em lactação;
- ordem de parto;
- intervalo de parto;
- gestação;
- restrições específicas da vaca.

A vaca seca não usa produção de leite; ela usa:

- gestação quando `day_of_pregnancy`;
- manutenção;
- crescimento, conforme os dados;
- DMI;
- cálcio e fósforo;
- combinações `CLOSE_UP`.

A novilha usa:

- peso corporal;
- peso adulto;
- ganho diário;
- gestação, dependendo do tipo;
- combinação `GROWING`;
- produção de leite zero.

O bloco que escolhe essas alterações está em `_calculate_nasem_requirements` em [addon_rufas/web.py](addon_rufas/web.py).

As equações vêm do original:

- [RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py](RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py);
- métodos como `_calculate_maintenance_energy_requirements`, `_calculate_growth_energy_requirements`, `_calculate_pregnancy_energy_requirements`, `_calculate_lactation_energy_requirements`;
- [RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py](RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py), que remove restrições de lactação para novilhas em determinados padrões NRC.

---

## 12. Confinamento ou pasto

A opção está em [addon_rufas/web.py](addon_rufas/web.py), constante `HOUSING`:

- `"Barn"`: confinamento;
- `"Grazing"`: pasto.

Essa escolha altera a energia de atividade calculada pela NASEM. Ela está em:

- [RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py](RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py);
- método `_calculate_activity_energy_requirements`.

Com confinamento:

```text
atividade = distância_km × 0,00035 × peso corporal
```

Com pasto:

```text
atividade = distância_km × peso × 0,75 × (600 - 12 × DMI_fora_do_pasto) / 600
```

O código usa `DMI_fora_do_pasto = 1.0`.

A atividade entra em:

- exigência de manutenção/atividade;
- restrições energéticas;
- DMI;
- possível troca dos alimentos.

O campo `walking_distance` é usado em metros na interface e convertido para km pelo RuFaS.

No modelo NRC clássico, o valor energético de atividade é somado à exigência geral de energia em `_simulate_nrc`.

---

## 13. De onde vêm as exigências nutricionais

As exigências podem vir de três fontes:

1. calculadora NASEM original do RuFaS;
2. entrada manual da tabela “Exigências nutricionais”;
3. arquivo de cenário, inclusive `dietopt-scenario`.

A calculadora está em:

- [RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py](RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py).

Ela calcula:

- manutenção;
- crescimento;
- gestação;
- lactação;
- DMI;
- proteína metabolizável;
- cálcio;
- fósforo;
- aminoácidos essenciais;
- atividade.

O botão **Calcular exigências NASEM** chama `_calculate_nasem_requirements` em [addon_rufas/web.py](addon_rufas/web.py).

As exigências manuais ficam em `DEFAULTS` e `REQUIREMENT_FIELDS`.

O campo de fósforo tem duas versões:

- fósforo calculado pela calculadora NASEM;
- fósforo baseado em processo, calculado pelo módulo `Nutrients` do RuFaS.

A implementação usa o maior dos dois para a restrição de fósforo no SLP/SLSQP:

```python
max(requirements.phosphorus, requirements.process_based_phosphorus)
```

Isso está em `phosphorus_constraint` no RuFaS e em `_simulate_nrc`.

Essa integração é a razão principal de o projeto não modificar o RuFaS:

- o add-on chama a calculadora original;
- chama os objetos e restrições originais;
- cria o `RationConfig`;
- troca apenas o método de solução.

---

## 14. Por que existe uma aba separada para NRC (PuLP)

Ela existe porque o projeto implementou um modelo clássico NRC além do otimizador SLP.

A aba apresenta dados que não fazem parte do SLSQP/SLP da interface:

- FDN mínimo e máximo;
- FDN de forragem;
- gordura máxima;
- tolerância do DMI;
- minerais;
- vitaminas;
- PDR;
- PNDR;
- balanço de proteína;
- NEL calculada com TDN.

Esses dados vêm de:

- [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py): equações, limites e padrões;
- biblioteca NASEM/RuFaS: composição dos alimentos;
- NRC 2001: tabela e capítulos usados como referências;
- interface: [addon_rufas/web.py](addon_rufas/web.py), constantes `NRC_FIELDS` e `_simulate_nrc`.

O modelo não é chamado “somente NRC” porque a interface usa exigências básicas NASEM para energia, proteína, cálcio, fósforo e DMI, e usa NRC clássico para as restrições adicionais.

**Correção importante sobre o valor zero:** na aba NRC, `0` desativa a restrição correspondente de FDN mínima, FDN máxima, FDN de forragem mínima e gordura máxima. Os minerais e vitaminas já eram desativados por `0` no código anterior. Foi corrigido em [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py) para que os limites máximos de FDN e gordura não sejam interpretados como exigir NDF/EE menor ou igual a zero. Essa correção está coberta por [tests/test_nrc_lp.py](tests/test_nrc_lp.py).

---

## 15. Fluxo de cada modelo

### SLSQP original

1. cria o vetor `x_i`;
2. cria os limites dos alimentos;
3. monta `RationConfig`;
4. seleciona as funções de restrição;
5. chama `scipy.optimize.minimize(method="SLSQP")`;
6. usa ponto inicial aleatório se não houver ração anterior;
7. avalia restrições e solução;
8. retorna a dieta.

Arquivos:

- [RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py](RufSas/RuFaS/RUFAS/biophysical/animal/ration/ration_optimizer.py);
- [addon_rufas/web.py](addon_rufas/web.py), em `simulate`.

### SLP

1. usa o mesmo vetor `x_i`, limites e exigências do SLSQP;
2. herdado do `RationOptimizer`;
3. calcula o valor das funções de restrição originais;
4. calcula o jacobiano por diferenças finitas;
5. monta uma aproximação linear;
6. resolve com `scipy.optimize.linprog(method="highs")`;
7. aceita passos por função de mérito;
8. restaura viabilidade nas restrições originais;
9. repete a partir de três pontos iniciais determinísticos.

Arquivo:

- [addon_rufas/linear_ration_optimizer.py](addon_rufas/linear_ration_optimizer.py).

Restrições lineares, como cálcio, fósforo e DMI, entram diretamente. FDN e gordura podem ser reescritas como razões lineares quando o DMI é conhecido. Energia e proteína são linearizadas localmente.

### NRC clássico PuLP

1. cria uma variável `x_i` por alimento;
2. soma o custo;
3. converte TDN em NEL;
4. calcula PDR e PNDR;
5. calcula proteína metabolizável;
6. calcula cálcio e fósforo absorvíveis;
7. cria restrições percentuais de DMI;
8. adiciona minerais e vitaminas;
9. resolve o modelo com PuLP/HiGHS;
10. se inviável, usa um modelo elástico para dizer o que falta;
11. calcula duais e rangings.

Arquivo:

- [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py).

---

## 16. Biblioteca NASEM, significado e localização

Esta pergunta já foi respondida no item **1**, mas o caminho completo é:

- [RufSas/RuFaS/input/data/feed/NASEM_Comp_with_TDN.csv](RufSas/RuFaS/input/data/feed/NASEM_Comp_with_TDN.csv)

Ela contém:

- composição dos alimentos;
- nomes;
- categorias;
- limitações;
- dados para cálculo de energia, proteína, fibra, minerais e vitaminas.

Os alimentos selecionados inicialmente vêm de:

- [RufSas/RuFaS/input/data/feed/example_Midwest_feed.json](RufSas/RuFaS/input/data/feed/example_Midwest_feed.json).

As equações da exigência NASEM não estão no CSV. Elas estão em:

- [RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py](RufSas/RuFaS/RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py).

O modelo clássico NRC usa o mesmo CSV para obter TDN, proteína, FDN, gordura, Ca, P e minerais. Ele não usa uma biblioteca NRC separada para a dieta da interface.

Há também uma cópia específica NRC em:

- [RufSas/RuFaS/input/data/feed/NRC_comp.csv](RufSas/RuFaS/input/data/feed/NRC_comp.csv).

Essa cópia é usada em testes de integração do RuFaS, mas o modelo NRC do projeto da interface lê principalmente a NASEM com TDN.

---

## 17. O que o botão “Analisar sensibilidade” faz

O botão chama `action == "sensitivity"` em [addon_rufas/web.py](addon_rufas/web.py).

Fluxo:

```text
usuário escolhe um item
 -> identifica o campo
 -> lê o percentual
 -> cria valor antigo e novo
 -> muda apenas esse campo no formulário
 -> resolve o cenário original
 -> resolve o cenário alterado
 -> compara rações e custos
 -> gera conclusões
```

Ele pode variar:

- peso corporal;
- todas as exigências;
- DMI;
- preço do leite;
- preço de cada alimento selecionado;
- tolerância de DMI;
- limites NRC;
- FDN, gordura e minerais.

O botão usa re-solução real, não só multiplicação. Assim ele não pressupõe que o preço-sombra continuará válido.

As restrições no limite são detectadas quando a margem for menor que `BINDING_TOLERANCE * scale`.

A constante está em [addon_rufas/web.py](addon_rufas/web.py):

```text
BINDING_TOLERANCE = 5e-4
NEGLIGIBLE = 1e-3 kg MS
```

Para o PuLP, o código ainda pode usar as faixas internas do HiGHS retornadas por `nrc_lp.solve`.

---

## 18. Diferença entre SLP e PuLP/NRC

### SLP

- usa as restrições originais do RuFaS;
- é uma extensão da formulação NASEM/NRC do próprio RuFaS;
- lineariza energia e proteína por diferenças finitas;
- é sequencial;
- usa até três partidas;
- usa SciPy `linprog`/HiGHS;
- valida a viabilidade nas funções originais não lineares;
- não fornece uma análise clássica completa de duais para todos os casos.

Arquivo: [addon_rufas/linear_ration_optimizer.py](addon_rufas/linear_ration_optimizer.py).

### PuLP/NRC

- é uma formulação linear independente;
- não lineariza o SLP;
- todas as variáveis e restrições são lineares;
- usa fórmulas clássicas NRC;
- usa PDR/PNDR, minerais e vitaminas;
- usa PuLP e HiGHS;
- fornece preços-sombra, custos reduzidos e rangings.

Arquivo: [addon_rufas/nrc_lp.py](addon_rufas/nrc_lp.py).

### Tratamento das restrições

No SLP:

- cálcio e fósforo já são lineares;
- DMI já é linear;
- limites dos alimentos já são lineares;
- FDN, FDN de forragem e gordura têm proporções transformáveis exatamente em restrições lineares;
- energia e proteína precisam ser linearizadas localmente;
- o resultado é verificado de novo nas funções originais.

No PuLP/NRC:

- não há aproximação sequencial;
- energia é linear por meio de NEL = `0,0245 × TDN - 0,12`;
- PDR/PNDR são combinações lineares;
- minerais e vitaminas são somas lineares;
- proporções de matéria seca são transformadas em coeficientes `valor - requisito`;
- o ótimo é linear global dentro daquele modelo.

Não é correto dizer que um é mais eficiente sem dizer o critério:

- eficiência econômica;
- viabilidade;
- tempo;
- determinismo;
- similaridade ao RuFaS;
- cobertura nutricional.

---

## Comandos úteis

### Iniciar a interface

Linux/macOS:

```bash
PYTHONPATH=RufSas/RuFaS .venv/bin/python -m addon_rufas.web
```

Windows:

```powershell
$env:PYTHONPATH="RufSas/RuFaS"
.venv\Scripts\python -m addon_rufas.web
```

Abrir:

```text
http://127.0.0.1:5000
```

### Executar comparação pareada

```bash
PYTHONPATH=RufSas/RuFaS .venv/bin/python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios/smoke/task_manager_metadata.json
PYTHONPATH=RufSas/RuFaS .venv/bin/python -m addon_rufas.summarize results/compare
```

### Executar testes

```bash
.venv/bin/python -m pytest tests/test_linear_ration_optimizer.py tests/test_nrc_lp.py tests/test_web.py
```
