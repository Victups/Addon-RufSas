# Otimização linear da formulação de dietas no RuFaS: modelagem, integração, sensibilidade e análise econômica

*Relatório final. Os detalhes técnicos estão em [`DOCUMENTACAO.md`](DOCUMENTACAO.md).*

## Resumo

O RuFaS simula uma fazenda leiteira dia a dia e formula a dieta de cada lote com o otimizador não linear SLSQP, a partir de um ponto inicial aleatório. Este trabalho desenvolve um add-on que se liga ao RuFaS sem alterar o código dele e traz duas alternativas baseadas em programação linear, ambas em **PuLP**:

- **Simplex sobre as restrições NASEM do RuFaS:** as mesmas restrições do SLSQP, resolvidas pelo método simplex. Os números que dependem da ração inteira (consumo, amido, % de concentrado e desconto do NDT) são fixados a cada rodada, o que torna cada restrição linear; depois são recalculados até a ração parar de mudar. Roda dentro da simulação.
- **Modelo NRC 2001 clássico:** cobre energia, PDR, PNDR, proteína metabolizável, fibra, minerais e vitaminas.

**Casos de teste.** Contra o SLSQP repetido 100 vezes com sementes diferentes, o simplex empata com o **melhor** SLSQP em 2 casos e é 0,65% mais barato do que **todas** as execuções no terceiro, com metade do tempo de uma execução.

**Simulação de um ano.** Em 8 fazendas montadas com os exemplos do RuFaS e preços brasileiros de set–nov/2026 (312 formulações pareadas), o simplex formulou com sucesso em 100% dos casos (o SLSQP falhou em 2). Em 6 fazendas os dois chegaram à mesma ração. Nas 2 fazendas em que a escolha é entre milho grão e silagem, o simplex ficou 0,3% a 0,6% mais caro na lactação, porque os números fixados não mostram que mais grão reduz a digestibilidade da fibra.

**Sensibilidade.** O modelo NRC traz a análise clássica: preços-sombra, faixas de validade e custos reduzidos, todos conferidos por re-solução.

**Preços reais.** A dieta de uma vaca de 35 kg de leite custa R$ 19,74 por dia, com renda sobre o custo de alimentação (IOFC) de R$ 74,83. A silagem de milho é o preço que mais pesa: ±20% no preço dela muda o custo em ±10%.

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
- **Método simplex:** resolve um PL percorrendo os vértices da região viável até o de menor custo (Hillier e Lieberman, 2013). Quando não há vértice viável à vista, a **fase 1** minimiza a soma das folgas das restrições.
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

### 4.2 Otimizador simplex (restrições NASEM do RuFaS)
- **Decisão:** kg de matéria seca de cada alimento por vaca por dia.
- **Objetivo:** custo da dieta.
- **Restrições:** as NASEM do RuFaS (`RationOptimizer.set_constraints`): energia líquida, Ca, P, proteína metabolizável mínima e máxima, FDN, FDN de forragem, gordura e matéria seca.
- **Por que dá para usar PL:** toda oferta NASEM é uma soma de **quantidade × valor por kg**. O valor por kg depende de quatro números da ração inteira: consumo, amido total, % de concentrado e desconto do NDT. Com esses números fixos, cada restrição é linear. Os valores por kg vêm das funções de oferta do próprio RuFaS, avaliadas para 1 kg de cada alimento.
- **Casos especiais:**
  - o `min()` da proteína microbiana vira duas linhas (`min(a, b) ≥ R` ⇔ `a ≥ R` e `b ≥ R`);
  - as proporções da MS são multiplicadas pelo consumo, o que é exato.
- **Iteração:**
  1. fixa os quatro números com a ração atual;
  2. resolve o PL pelo simplex (PuLP + HiGHS, `solver="simplex"`); se não houver solução, usa a fase 1;
  3. recalcula os números com a ração nova e repete até a ração parar de mudar (3 a 11 rodadas; no máximo 20).
- **Níveis de consumo:** o procedimento roda com o consumo livre e com o consumo fixado em 5 níveis entre o mínimo e o máximo do RuFaS, e fica com a ração mais barata.
- **Verificação:** uma ração só conta como viável se passar nas funções originais do RuFaS (todas `≥ 0`).
- Não usa derivadas, e o resultado é determinístico.

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
- **Modo `compare`:** o simplex conduz a simulação, e o SLSQP resolve em sombra o mesmo problema, o que dá pares comparáveis.
- **Re-tentativas:** cada evento de reformulação registra as tentativas, os cortes de produção de leite e o uso de ração de fallback.

### 4.5 Análise de sensibilidade
1. **Re-solução com variação:** muda um item (exigência, preço do leite, preço de um alimento ou limite do modelo NRC) e compara as rações antes e depois. Mostra os alimentos que entram, saem, sobem ou descem, o custo marginal e as restrições no limite, com conclusões em texto.
2. **Sensibilidade de PL (modelo NRC):** preços-sombra, faixas de validade da exigência, custos reduzidos e faixas de preço dos alimentos, a partir da análise de faixas (*ranging*) do HiGHS.

### 4.6 Indicadores econômicos
- **Custo da dieta:** R$ por vaca por dia.
- **IOFC:** leite × preço do leite − custo da dieta.
- **Diferença simplex contra SLSQP:** em % e em R$ por vaca por dia, e anualizada pelo rebanho.

## 5. Resultados

### 5.1 Simplex contra o SLSQP repetido 100 vezes

Três casos de teste NASEM, com alimentos reais da biblioteca e preços de exemplo:

| Caso | Simplex | Melhor SLSQP | Média SLSQP | Pior SLSQP | Simplex × melhor | Simplex × média | ms simplex | ms SLSQP |
|---|---|---|---|---|---|---|---|---|
| NASEM ×0,8 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 33 | 112 |
| NASEM ×1,0 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 38 | 97 |
| NASEM ×1,2 | 0,3119 | 0,3139 | 0,3148 | 0,3157 | −0,65% | −0,92% | 58 | 109 |

- O simplex empata com o melhor de 100 SLSQPs em 2 casos e fica abaixo de todos no NASEM ×1,2, onde o SLSQP para num ótimo local qualquer que seja o ponto de partida.
- Uma execução do simplex leva de 33 a 58 ms, contra 97 a 112 ms de uma execução do SLSQP.

### 5.2 Simulação de um ano: 8 fazendas com preços brasileiros (312 formulações pareadas)

| Fazenda | Custo lactação simplex (R$/vaca/dia) | SLSQP | Simplex mais barato | Simplex mais caro | Diferença/ano |
|---|---|---|---|---|---|
| freestall-midwest (100 vacas) | 32,55 | 32,35 | 0 | 11 de 39 | R$ 7.048 a mais |
| freestall-intermountain | 23,66 | 23,66 | 0 | 0 | — |
| freestall-northeast | 23,52 | 23,52 | 0 | 0 | — |
| freestall-southwest | 23,66 | 23,66 | 0 | 0 | — |
| openlot-midwest (1.000 vacas) | 27,43 | 27,34 | 0 | 9 de 39 | R$ 31.392 a mais |
| openlot-intermountain | 19,84 | 19,84 | 0 | 0 | — |
| openlot-northeast | 19,73 | 19,73 | 0 | 0 | — |
| openlot-southwest | 19,84 | 19,84 | 0 | 0 | — |

- "Mais barato" e "mais caro" contam diferenças acima de 0,1%.
- A diferença por ano é a diferença média na lactação × número de vacas × 365.
- O simplex formulou com sucesso em 100% dos casos; o SLSQP falhou em 2 formulações da openlot-midwest.
- Nenhum evento precisou de nova tentativa, corte de leite ou ração de fallback.
- Na fazenda de exemplo com preços genéricos do RuFaS, o simplex foi mais barato em 6 de 39 formulações e nunca mais caro.
- Tempo por formulação: 23 a 52 ms no simplex e 10 a 73 ms no SLSQP.

**Por que o simplex perde nas fazendas Midwest.** Nessas listas, a escolha é entre milho grão e silagem de milho. O simplex escolheu grão e o SLSQP, silagem. Com os quatro números da ração fixos, o PL não vê que mais grão aumenta o amido e o concentrado e, com isso, reduz a digestibilidade da fibra e muda a passagem da proteína de **todos** os alimentos. Num caso analisado, o PL montado na própria ração ótima do SLSQP indicou uma ração com grão R$ 0,29 mais barata. Conferida no modelo real do RuFaS, ela ficou 103 g abaixo da exigência de proteína e também abaixo da de energia. Enxergar esse efeito cruzado exige as derivadas das funções do RuFaS. Os 5 níveis de consumo reduziram a diferença pela metade (de 0,9% para 0,6% na freestall), mas não a eliminaram.

### 5.3 Sensibilidade

Os exemplos usam os alimentos padrão e os preços de exemplo.

- **Proteína metabolizável +15%:**
  - o custo vai de 0,2918 para 0,2998 por vaca/dia (+2,7%); o SLSQP chega a 0,3017;
  - a mistura de capim e leguminosa sai, e a silagem de leguminosa sobe para 30 kg MS;
  - a proteína metabolizável fica no limite.
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

Só com esses 5 alimentos, a vaca padrão (35 kg de leite) recebe 17,3 kg de silagem de milho, 9,5 kg de casca de soja, 4,1 kg de farelo e 0,3 kg de caroço de algodão (kg de MS). O custo é de R$ 30,26 por dia, com IOFC de R$ 64,31. O simplex e o SLSQP chegam à mesma ração.

Com calcário e sal disponíveis (cenário `planilha-2026.json`), o cálcio deixa de vir de alimentos caros:

| Modelo | Custo (R$/vaca/dia) | IOFC (R$/vaca/dia) |
|---|---|---|
| Simplex | 19,74 | 74,83 |
| SLSQP | 19,72 | 74,85 |
| NRC (PuLP), que também exige minerais e vitaminas | 25,64 | 68,93 |

### 5.5 Sensibilidade a ±10% e ±20% nos preços

Re-solução com cada preço alterado, mantendo os outros; a tabela completa está em `scenarios/precos/sensibilidade.md`.

| Ingrediente | Custo com −20% / +20% (simplex) | Custo com −20% / +20% (NRC) | Ração muda? |
|---|---|---|---|
| Silagem de milho | −10,6% / +10,6% | −5,3% / +5,3% | simplex: com +20%, −1,4 kg de silagem e +0,4 kg de farelo |
| Farelo de soja | −4,7% / +4,4% | −7,8% / +7,8% | simplex: com −20%, troca 4,6 kg de silagem por 1,6 kg de farelo |
| Caroço de algodão | −5,3% / +5,0% | −5,6% / +5,6% | simplex: com −20%, +2,4 kg de caroço e −0,9 kg de farelo |
| Milho grão | 0 | −0,6% / +0,6% | não |
| Casca de soja | 0 | 0 | não |

- A **silagem** é o item que mais pesa no custo. É nela que vale negociar ou reduzir o custo de produção.
- No modelo NRC, a ração **não muda** em nenhum caso, o que confirma as faixas de preço da análise de PL.
- Os minerais só mudariam a ração com preços dezenas de vezes maiores que os de mercado: calcário acima de R$ 60/kg, sal acima de R$ 325/kg, premix acima de R$ 245/kg.

## 6. Discussão

- **Simplicidade contra custo:** o simplex resolve as restrições do RuFaS sem derivadas e é fácil de explicar: fixa os números da ração inteira, resolve um PL, recalcula e repete. Ele é determinístico, mais rápido que uma execução do SLSQP nos casos de teste e nunca falhou. O preço dessa simplicidade aparece quando a decisão é entre grão e silagem: ali o simplex fica 0,3% a 0,6% mais caro. Uma versão anterior deste trabalho, com programação linear sequencial (derivadas por diferenças finitas, branch `integracao-rufas`), não tinha essa perda e ficava 0,05% mais barata que o SLSQP, mas era bem mais difícil de explicar.
- **Confiabilidade:** o resultado do simplex é sempre o mesmo, e o do SLSQP varia até 3% conforme o ponto inicial sorteado.
- **Onde está o dinheiro:** o otimizador muda pouco o custo. O preço da silagem, que muda o custo em ±10% com ±20% de variação, e a disponibilidade de minerais baratos, que levou o custo de R$ 30,26 para R$ 19,74 por vaca/dia, pesam muito mais. A análise de sensibilidade é o que mostra isso ao produtor.
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
  - o simplex fixa os números da ração inteira em cada rodada e não enxerga o efeito cruzado entre alimentos; na troca entre grão e silagem, fica até ~1% mais caro que o SLSQP;
  - o simplex usa só o padrão NASEM do RuFaS;
  - o modelo PuLP usa o NDT sem desconto por consumo e ainda não roda dentro da simulação;
  - as fazendas são os exemplos do RuFaS, americanos, com preços brasileiros, e não fazendas reais de Goiás;
  - os preços de volumosos e minerais não vêm do CEPEA, e não há notas fiscais. O premix é provisório, e os minerais têm preço de grau agrícola.

## 7. Conclusão

O simplex em PuLP substitui o SLSQP do RuFaS usando as mesmas restrições NASEM:
- custa o mesmo ou menos do que o melhor de 100 execuções do otimizador original nos casos de teste;
- formulou com sucesso em todas as 312 formulações das 8 fazendas simuladas por um ano (o SLSQP falhou em 2);
- empatou em 6 das 8 fazendas e ficou 0,3% a 0,6% mais caro nas 2 em que a escolha é entre grão e silagem;
- é determinístico, mais simples de explicar e não usa derivadas.

Em termos econômicos, trocar o otimizador muda pouco o custo: menos de 1% do custo de alimentação da lactação, para mais ou para menos. O valor maior para o produtor está na informação de decisão. A ração de menor custo com preços reais sai a R$ 19,74 por vaca/dia, com IOFC de R$ 74,83. A silagem é o insumo que mais move esse custo. Os minerais, mesmo com preço incerto, não mudam a decisão.

## 8. Trabalhos futuros

- Rodar uma fazenda real de Goiás no modo `compare`, com notas fiscais.
- Levar o modelo NRC em PuLP para dentro da simulação.
- Formular por animal em vez de por lote, como fez Brito.
- Aplicar o desconto de NDT por nível de consumo.
- Levar em conta, no simplex, o efeito do amido e do concentrado sobre o valor dos outros alimentos.

## Referências

- Brito, D. B. S. *Formulação Nutricional Otimizada como Ferramenta para Aumento de Margem Econômica na Pecuária Leiteira.* TCC, IFG, 2026.
- CEPEA/Esalq-USP. Indicadores do leite ao produtor e do milho. Licença CC BY-NC 4.0.
- NASEM (2021). *Nutrient Requirements of Dairy Cattle*, 8ª ed. National Academies Press.
- NRC (2001). *Nutrient Requirements of Dairy Cattle*, 7ª ed. National Academy Press.
- RuFaS — Ruminant Farm Systems. https://github.com/RuminantFarmSystems/RuFaS
- Huangfu, Q.; Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. *Mathematical Programming Computation* (HiGHS).
- Hillier, F. S.; Lieberman, G. J. *Introdução à Pesquisa Operacional*, 9ª ed. Porto Alegre: AMGH, 2013. Método simplex, fase 1, dualidade e análise de sensibilidade.
- Petersen, W. E. (1932). A formula for evaluating feeds on the basis of digestible nutrients. *Journal of Dairy Science* 15(4): 293–297.
- Planilha de preços de ingredientes para nutrição de vacas (R$/kg), compilada pela turma, 2026 (`scenarios/precos/planilha-2026.csv`).
