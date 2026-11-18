# Otimização linear da formulação de dietas no RuFaS: modelagem, integração, sensibilidade e análise econômica

*Relatório final. Os detalhes técnicos estão em [`DOCUMENTACAO.md`](DOCUMENTACAO.md).*

## Resumo

O RuFaS simula uma fazenda leiteira dia a dia e formula a dieta de cada lote com o otimizador não linear SLSQP, a partir de um ponto inicial aleatório. Este trabalho desenvolve um add-on que se liga ao RuFaS sem alterar o código dele e traz duas alternativas baseadas em programação linear:

- **SLP (programação linear sequencial):** resolve o mesmo modelo do RuFaS com o solver HiGHS e roda dentro da simulação.
- **Modelo NRC 2001 clássico em PuLP:** cobre energia, PDR, PNDR, proteína metabolizável, fibra, minerais e vitaminas.

O SLP foi comparado com o SLSQP repetido 100 vezes com sementes diferentes, em seis casos de teste:
- empata com o **melhor** SLSQP em 5 casos;
- é 0,65% mais barato do que **todas** as execuções no sexto;
- é de 0 a 1,3% mais barato do que uma execução típica;
- é determinístico, com tempo por formulação parecido com o de uma execução do SLSQP.

**Simulação de um ano.** Foram 8 fazendas montadas com os exemplos do RuFaS e preços brasileiros de set–nov/2026, com 312 formulações pareadas. Nelas o SLP nunca ficou mais caro. Nas listas de alimentos com mais ótimos locais, ficou 0,05% mais barato na lactação, o que dá de R$ 577 a R$ 5.326 por ano conforme o rebanho.

**Ótimos locais.** Com uma única partida, o SLP chegou a ficar 10% mais caro numa formulação. O problema não é convexo, e por isso o SLP passou a usar 3 partidas com semente fixa.

**Sensibilidade.** O modelo PuLP traz a análise clássica: preços-sombra, faixas de validade e custos reduzidos, todos conferidos por re-solução.

**Preços reais.** A dieta de uma vaca de 35 kg de leite custa R$ 19,73 por dia, com renda sobre o custo de alimentação (IOFC) de R$ 74,84. A silagem de milho é o preço que mais pesa: ±20% no preço dela muda o custo em ±10%.

## 1. Introdução

A alimentação é o maior custo variável da pecuária leiteira, chegando a mais de 50% dos custos operacionais em sistemas intensivos (NRC, 2001). Formular a dieta é, por isso, um problema clássico de otimização: combinar alimentos para atender às exigências do animal ao menor custo.

O RuFaS (Ruminant Farm Systems) é um simulador de fazendas leiteiras que formula a dieta de cada lote ao longo da simulação. A formulação dele usa SLSQP sobre restrições não lineares do NASEM 2021 ou do NRC 2001, partindo de um ponto aleatório. Isso tem três consequências:
- o resultado muda de uma execução para outra;
- o resultado pode parar num ótimo local;
- o resultado não traz as informações de sensibilidade que a programação linear dá de graça.

Este trabalho investiga se uma formulação linear pode substituir a do RuFaS sem perder fidelidade ao modelo, e que ganho isso traz em custo, estabilidade, tempo e informação para a decisão.

## 2. Objetivos

1. **Modelagem:** formular o problema de dieta como programação linear, preservando as restrições do RuFaS e as recomendações do NRC.
2. **Artefato:** implementar o otimizador e integrá-lo ao RuFaS sem editar o código do RuFaS.
3. **Análise de sensibilidade:** mostrar como a decisão muda quando mudam as exigências e os preços.
4. **Desempenho econômico:** comparar com o otimizador original do RuFaS, usando preços reais do CEPEA.
5. **Interface e documentação** para uso e reprodução.

## 3. Fundamentação

- **Exigências:** o NRC (2001) e o NASEM (2021) definem as exigências de energia líquida de lactação, proteína metabolizável (formada pela proteína microbiana, que vem da PDR, e pela PNDR digestível), fibra, minerais e vitaminas, em função do peso, da produção e da composição do leite e da fase da lactação.
- **Programação linear:** minimiza `Σ cᵢxᵢ` sujeito a restrições lineares. A teoria de dualidade dá:
  - o **preço-sombra** de cada restrição, isto é, quanto custa uma unidade a mais de exigência;
  - a **faixa de validade** desse preço-sombra;
  - o **custo reduzido** de cada alimento fora da solução, isto é, quanto o preço precisa cair para o alimento entrar.
- **Programação linear sequencial (SLP):** resolve um problema não linear por uma sequência de PLs, linearizando as restrições em volta do ponto atual dentro de uma região de confiança.
- **Trabalho relacionado:** Brito (IFG, 2026), com o mesmo orientador, aplicou PL do NRC a uma fazenda de Goiás e mediu um aumento médio de 9,14% no IOFC. A seção 6 discute três pontos daquele modelo que este trabalho corrige.

## 4. Materiais e métodos

### 4.1 Dados
- **Alimentos:** biblioteca do RuFaS (`NASEM_Comp_with_TDN.csv`, 175 alimentos), com composição, frações de proteína, minerais e vitaminas.
- **Exigências:** as calculadoras do próprio RuFaS (NASEM) e o módulo de fósforo dele.
- **Preços** (set–nov/2026, R$/kg de matéria seca):
  - leite (Goiás, set/2026) e milho do CEPEA/Esalq;
  - farelo de soja da praça de Rio Verde (GO);
  - silagem, caroço de algodão e casca de soja de uma fazenda de Goiás;
  - os demais 120 alimentos da planilha de preços montada pela turma (174 itens, com fonte e status de verificação). A planilha foi convertida de matéria natural para MS; o premix foi corrigido para R$ 5/kg (provisório), porque o proxy dela era um núcleo probiótico.

  Calcário, sal e premix receberam teto de 0,3, 0,15 e 0,2 kg MS/dia. Sem esse teto, o modelo do RuFaS, que não limita minerais, usa o calcário barato como enchimento. As fontes estão em `scenarios/precos/README.md`.
- **Fazendas de teste:** o professor não enviou fazendas, então foram usadas as do próprio RuFaS:
  - 2 rebanhos: free-stall com 100 vacas e open lot com 1.000 vacas;
  - cada um com as 4 listas regionais de alimentos (Midwest, Intermountain, Northeast e Southwest), o que dá 8 fazendas;
  - um ano de simulação, formulação automática e preços brasileiros.

  Os alimentos sem preço (concentrado de bezerra e misturas de subprodutos) foram precificados pelo método de Petersen, isto é, pelo valor da energia e da proteína do milho e do farelo de soja (`scenarios/fazendas/`).

### 4.2 Otimizador SLP
- **Decisão:** kg de matéria seca de cada alimento por vaca por dia.
- **Objetivo:** custo da dieta.
- **Restrições:** as do RuFaS. Energia e proteína metabolizável são não lineares no RuFaS (desconto de NDT, taxas de passagem e `min()`).
- **Iteração:**
  1. lineariza as **funções do próprio RuFaS** por diferenças finitas;
  2. resolve o PL com HiGHS numa região de confiança;
  3. aceita o passo por uma função de mérito com penalidade tirada dos duais.
- **Casos difíceis e fim:** quando a linearização fica inviável, dá um passo de fase 1. No fim, uma restauração garante que a ração atende às restrições não lineares verdadeiras.
- **Pontos iniciais:** o ponto do RuFaS (a ração anterior, ou os limites escalados até o consumo) e mais 2 pontos sorteados com semente fixa. O SLP fica com a ração viável mais barata. O resultado é determinístico.

### 4.3 Modelo NRC em PuLP
É um PL linear com:
- matéria seca;
- energia líquida de lactação (NEL = 0,0245·NDT − 0,12);
- balanço de PDR (PDR ≥ 1,18 × proteína microbiana);
- proteína metabolizável (0,64 × proteína microbiana + PNDR digestível + endógena);
- Ca e P absorvíveis;
- FDN, FDN de forragem e gordura;
- Mg, K, Na, Cl e S;
- sete microminerais;
- vitaminas A, D e E.

As proporções da MS viram restrições lineares sem aproximação. O `min()` da proteína microbiana desaparece com o balanço de PDR, que o próprio NRC recomenda. O solver é o HiGHS. Quando não há ração possível, um PL elástico diz quanto falta de cada nutriente.

### 4.4 Integração com o RuFaS
- **Otimizador:** subclasse de `RationOptimizer`, trocando só o solver em tempo de execução.
- **Simulação:** o runner `addon_rufas/run.py` troca o otimizador dos lotes, inclusive nos processos paralelos do RuFaS.
- **Modo `compare`:** o SLP conduz a simulação, e o SLSQP resolve em sombra o mesmo problema, o que dá pares comparáveis.
- **Re-tentativas:** cada evento de reformulação registra as tentativas, os cortes de produção de leite e o uso de ração de fallback.

### 4.5 Análise de sensibilidade
1. **Re-solução com variação:** muda um item (exigência, preço do leite, preço de um alimento ou limite do modelo NRC) e compara as rações antes e depois. Mostra os alimentos que entram, saem, sobem ou descem, o custo marginal e as restrições no limite, com conclusões em texto.
2. **Sensibilidade de PL (modelo NRC):** preços-sombra, faixas de validade da exigência, custos reduzidos e faixas de preço dos alimentos, a partir da análise de faixas (*ranging*) do HiGHS.

### 4.6 Indicadores econômicos
- **Custo da dieta:** R$ por vaca por dia.
- **IOFC:** leite × preço do leite − custo da dieta.
- **Economia SLP contra SLSQP:** em % e em R$ por vaca por dia, e anualizada pelo rebanho.

## 5. Resultados

### 5.1 SLP contra o SLSQP repetido 100 vezes

Seis casos de teste, com alimentos reais da biblioteca e preços de exemplo:

| Caso | SLP | Melhor SLSQP | Média SLSQP | Pior SLSQP | SLP × melhor | SLP × média | ms SLP | ms SLSQP |
|---|---|---|---|---|---|---|---|---|
| NASEM ×0,8 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 53 | 91 |
| NASEM ×1,0 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 48 | 96 |
| NASEM ×1,2 | 0,3119 | 0,3139 | 0,3148 | 0,3157 | −0,65% | −0,92% | 113 | 97 |
| NRC ×0,8 | 0,2696 | 0,2696 | 0,2696 | 0,2696 | 0,00% | 0,00% | 27 | 70 |
| NRC ×1,0 | 0,2911 | 0,2911 | 0,2949 | 0,2978 | 0,00% | −1,28% | 113 | 59 |
| NRC ×1,2 | 0,3546 | 0,3546 | 0,3581 | 0,3652 | 0,00% | −0,97% | 46 | 83 |

- O SLP empata com o melhor de 100 SLSQPs em 5 casos e fica abaixo de todos no NASEM ×1,2, onde o SLSQP para num ótimo local qualquer que seja o ponto de partida.
- O próprio SLSQP varia até 3% conforme a semente.
- Uma execução do SLP (3 partidas) leva de 27 a 113 ms, parecido com uma execução do SLSQP. Para chegar ao mesmo custo, o SLSQP precisaria de várias execuções.

### 5.2 Simulação de um ano: 8 fazendas com preços brasileiros (312 formulações pareadas)

| Fazenda | Custo lactação SLP (R$/vaca/dia) | SLSQP | SLP mais barato | SLP mais caro | Economia/ano |
|---|---|---|---|---|---|
| freestall-midwest (100 vacas) | 32,56 | 32,58 | 2 de 39 | 0 | R$ 577 |
| freestall-intermountain | 23,66 | 23,66 | 0 | 0 | — |
| freestall-northeast | 23,52 | 23,52 | 0 | 0 | — |
| freestall-southwest | 23,66 | 23,66 | 0 | 0 | — |
| openlot-midwest (1.000 vacas) | 27,59 | 27,61 | 4 de 39 | 0 | R$ 5.326 |
| openlot-intermountain | 19,84 | 19,84 | 0 | 0 | — |
| openlot-northeast | 19,73 | 19,73 | 0 | 0 | — |
| openlot-southwest | 19,84 | 19,84 | 0 | 0 | — |

- "Mais barato" e "mais caro" contam diferenças acima de 0,1%.
- A economia por ano é a diferença média na lactação × número de vacas × 365.
- Os dois otimizadores formularam com sucesso em 100% dos casos.
- Nenhum evento precisou de nova tentativa, corte de leite ou ração de fallback.
- Na fazenda de exemplo com preços genéricos do RuFaS, o SLP foi mais barato em 4 de 13 formulações na lactação (0,08%) e em 3 de 13 no pré-parto (0,43%), e empatou nas novilhas.

**Ótimo local.** A primeira rodada usava uma única partida. Nela, o SLP ficou 1,1% mais caro na lactação da freestall-midwest, com uma formulação 10% acima do SLSQP. O problema não é convexo: energia e proteína metabolizável dependem do consumo de forma não linear. Com 3 partidas de semente fixa, a diferença sumiu, e o SLP passou a ficar 0,05% mais barato. O custo foi deixar cada formulação 2 a 3 vezes mais lenta, de 30 a 110 ms, o que não pesa numa simulação que reformula a dieta 13 vezes por ano.

### 5.3 Sensibilidade

Os exemplos usam os alimentos padrão e os preços de exemplo.

- **Proteína metabolizável +15%:**
  - o custo vai de 0,2918 para 0,5421 por vaca/dia, com custo marginal de 0,00073 por grama;
  - entram silagem de milho, feno, farinha de sangue e mineral, e a silagem de leguminosa diminui;
  - ficam no limite cálcio, proteína metabolizável e FDN máximo.
- **Cálcio −10%:** o custo cai 9,8%, trocando silagem de mistura de capim e leguminosa por silagem de leguminosa.
- **Modelo NRC (caso de teste do NRC, vaca de 680 kg com 35 kg de leite):**
  - a energia tem preço-sombra de 0,239 por Mcal, válido entre 33,1 e 35,7 Mcal. Dentro dessa faixa, o custo previsto pelo preço-sombra é igual ao da re-solução; acima dela, o custo sobe mais;
  - o feno tem custo reduzido de 0,56: o preço teria de ficar negativo para ele entrar, ou seja, ele não entraria nem de graça.

### 5.4 Preços reais (Goiás, novembro de 2026)

| Ingrediente | Preço | R$/kg MS |
|---|---|---|
| Milho (CEPEA) | R$ 67,14/saca | 1,29 |
| Farelo de soja (Rio Verde) | R$ 2.020/t | 2,26 |
| Silagem de milho | R$ 201/t | 0,57 |
| Caroço de algodão | R$ 1.000/t | 1,09 |
| Casca de soja | R$ 1.030/t | 1,14 |
| Leite (CEPEA, Goiás) | R$ 2,79/litro | 2,70/kg |

Só com esses 5 alimentos, a vaca padrão (35 kg de leite) recebe 17,3 kg de silagem de milho, 9,5 kg de casca de soja, 4,1 kg de farelo e 0,3 kg de caroço de algodão (kg de MS). O custo é de R$ 30,26 por dia, com IOFC de R$ 64,31. O SLP e o SLSQP chegam à mesma ração.

Com calcário e sal disponíveis (cenário `planilha-2026.json`), o cálcio deixa de vir de alimentos caros:

| Modelo | Custo (R$/vaca/dia) | IOFC (R$/vaca/dia) |
|---|---|---|
| SLP | 19,73 | 74,84 |
| SLSQP | 19,72 | 74,85 |
| NRC (PuLP), que também exige minerais e vitaminas | 25,64 | 68,93 |

### 5.5 Sensibilidade a ±10% e ±20% nos preços

Re-solução com cada preço alterado, mantendo os outros; a tabela completa está em `scenarios/precos/sensibilidade.md`.

| Ingrediente | Custo com −20% / +20% (SLP) | Custo com −20% / +20% (NRC) | Ração muda? |
|---|---|---|---|
| Silagem de milho | −10,4% / +10,4% | −5,3% / +5,3% | pouco (até 0,3 kg) |
| Farelo de soja | −4,8% / +4,4% | −7,8% / +7,8% | SLP: com −20%, troca 3,8 kg de silagem por 1,4 kg de farelo |
| Caroço de algodão | −5,4% / +5,1% | −5,6% / +5,6% | SLP: com −20%, +2,4 kg de caroço e −0,9 kg de farelo |
| Milho grão | 0 | −0,6% / +0,6% | não |
| Casca de soja | 0 | 0 | não |

- A **silagem** é o item que mais pesa no custo. É nela que vale negociar ou reduzir o custo de produção.
- No modelo NRC, a ração **não muda** em nenhum caso, o que confirma as faixas de preço da análise de PL.
- Os minerais só mudariam a ração com preços dezenas de vezes maiores que os de mercado: calcário acima de R$ 60/kg, sal acima de R$ 325/kg, premix acima de R$ 245/kg.

## 6. Discussão

- **Ganho principal:** o ganho de custo do SLP contra o SLSQP é pequeno, mas nunca contra o SLP:
  - de 0 a 1,3% contra uma execução típica nos casos de teste;
  - 0,05% na lactação das fazendas com mais alimentos, que é de R$ 577 a R$ 5.326 por ano.

  O ganho maior é de **confiabilidade**: o resultado é sempre o mesmo e não depende da sorte do ponto inicial, cuja variação chega a 3%.
- **Ótimos locais:** o problema do RuFaS não é convexo. Uma única partida, do SLP ou do SLSQP, pode parar num ótimo pior, e com preços brasileiros a diferença chegou a 10% numa formulação. Várias partidas determinísticas resolvem o problema na prática, ao custo de um tempo parecido com o do SLSQP.
- **Onde está o dinheiro:** o otimizador muda pouco o custo. O preço da silagem, que muda o custo em ±10% com ±20% de variação, e a disponibilidade de minerais baratos, que levou o custo de R$ 30,26 para R$ 19,73 por vaca/dia, pesam muito mais. A análise de sensibilidade é o que mostra isso ao produtor.
- **Valor da sensibilidade:** os preços-sombra e as faixas dizem o que realmente limita o custo da dieta e até onde uma decisão de compra continua valendo. O RuFaS não dá essas informações.
- **Peculiaridades do RuFaS** encontradas e mantidas, para fidelidade ao simulador:
  - o teor de fósforo da dieta nunca é atualizado e fica 0;
  - o alojamento é comparado com o texto exato, então `"barn"` em minúsculas dá energia de atividade zero;
  - a unidade do ganho de peso diário está documentada errada;
  - o modelo não limita minerais, e com calcário barato o otimizador o usa como enchimento, de 4 a 7 kg/dia;
  - o exemplo de alimentos Northeast repete um alimento, e o próprio RuFaS recusa o arquivo.
- **Correções ao trabalho de Brito (2026):**
  - o fator de consumo usa (semana − 3,67) onde o NRC usa +3,67, o que dá consumo negativo no início da lactação;
  - a eficiência da proteína do leite aparece como 0,97 no código e 0,67 no texto;
  - a restrição de energia compara energia digestível com exigência de energia líquida.
- **Limitações:**
  - o SLP acha um ótimo local nas restrições não lineares; as 3 partidas reduzem esse risco, mas não garantem o ótimo global;
  - o modelo PuLP usa o NDT sem desconto por consumo e ainda não roda dentro da simulação;
  - as fazendas são os exemplos do RuFaS, americanos, com preços brasileiros, e não fazendas reais de Goiás;
  - os preços de volumosos e minerais não vêm do CEPEA, e não há notas fiscais. O premix é provisório, e os minerais têm preço de grau agrícola.

## 7. Conclusão

A formulação linear substitui a do RuFaS sem perder fidelidade ao modelo:
- custa o mesmo ou menos do que o melhor de 100 execuções do otimizador original;
- nunca ficou mais cara em 312 formulações de 8 fazendas simuladas por um ano com preços brasileiros;
- é determinística, com tempo parecido;
- acrescenta a análise de sensibilidade que o simulador não tinha.

Em termos econômicos, trocar o otimizador rende pouco: até 0,05% do custo de alimentação da lactação, ou R$ 5,3 mil por ano num rebanho de 1.000 vacas. O valor maior para o produtor está na informação de decisão. A ração de menor custo com preços reais sai a R$ 19,73 por vaca/dia, com IOFC de R$ 74,84. A silagem é o insumo que mais move esse custo. Os minerais, mesmo com preço incerto, não mudam a decisão.

## 8. Trabalhos futuros

- Rodar uma fazenda real de Goiás no modo `compare`, com notas fiscais.
- Levar o modelo NRC em PuLP para dentro da simulação.
- Formular por animal em vez de por lote, como fez Brito.
- Aplicar o desconto de NDT por nível de consumo.

## Referências

- Brito, D. B. S. *Formulação Nutricional Otimizada como Ferramenta para Aumento de Margem Econômica na Pecuária Leiteira.* TCC, IFG, 2026.
- CEPEA/Esalq-USP. Indicadores do leite ao produtor e do milho. Licença CC BY-NC 4.0.
- NASEM (2021). *Nutrient Requirements of Dairy Cattle*, 8ª ed. National Academies Press.
- NRC (2001). *Nutrient Requirements of Dairy Cattle*, 7ª ed. National Academy Press.
- RuFaS — Ruminant Farm Systems. https://github.com/RuminantFarmSystems/RuFaS
- Huangfu, Q.; Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. *Mathematical Programming Computation* (HiGHS).
- Hillier, F. S.; Lieberman, G. J. *Introdução à Pesquisa Operacional*, 9ª ed. Porto Alegre: AMGH, 2013. Dualidade e análise de sensibilidade.
- Nocedal, J.; Wright, S. J. *Numerical Optimization*, 2ª ed. Springer, 2006. Programação linear sequencial, regiões de confiança e funções de mérito.
- Petersen, W. E. (1932). A formula for evaluating feeds on the basis of digestible nutrients. *Journal of Dairy Science* 15(4): 293–297.
- Planilha de preços de ingredientes para nutrição de vacas (R$/kg), compilada pela turma, 2026 (`scenarios/precos/planilha-2026.csv`).
