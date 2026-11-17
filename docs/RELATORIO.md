# Otimização linear da formulação de dietas no RuFaS: modelagem, integração, sensibilidade e análise econômica

*Rascunho do relatório final. Os trechos marcados **[PENDENTE]** dependem das fazendas do professor e dos preços finais. Os detalhes técnicos estão em [`DOCUMENTACAO.md`](DOCUMENTACAO.md).*

## Resumo

O RuFaS simula uma fazenda leiteira dia a dia e formula a dieta de cada lote com o otimizador não linear SLSQP, a partir de um ponto inicial aleatório. Este trabalho desenvolve um add-on que se liga ao RuFaS sem alterar o código dele e traz duas alternativas baseadas em programação linear:

- **SLP (programação linear sequencial):** resolve o mesmo modelo do RuFaS com o solver HiGHS e roda dentro da simulação.
- **Modelo NRC 2001 clássico em PuLP:** cobre energia, PDR, PNDR, proteína metabolizável, fibra, minerais e vitaminas.

O SLP foi comparado com o SLSQP repetido 100 vezes com sementes diferentes, em seis casos de teste:
- empata com o **melhor** SLSQP em 5 casos;
- é 0,65% mais barato do que **todas** as execuções no sexto;
- é de 0 a 1,3% mais barato do que uma execução típica;
- é determinístico e até 9 vezes mais rápido por formulação (empata no caso mais difícil).

Na simulação de um ano de uma fazenda de exemplo, com 39 formulações pareadas, o SLP nunca ficou mais caro e foi de 1,8 a 2,8 vezes mais rápido. O modelo PuLP traz a análise de sensibilidade clássica: preços-sombra, faixas de validade e custos reduzidos, todos conferidos por re-solução. Com preços reais de Goiás (novembro de 2026), a dieta de uma vaca de 35 kg de leite custa R$ 30,26 por dia, com renda sobre o custo de alimentação (IOFC) de R$ 64,31. **[PENDENTE: economia em R$ nas fazendas do professor.]**

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
- **Preços:**
  - leite e milho do CEPEA/Esalq;
  - farelo de soja da praça de Rio Verde (GO);
  - volumosos e subprodutos de uma fazenda de Goiás.

  As fontes estão em `scenarios/precos/README.md`. **[PENDENTE: notas fiscais da fazenda estudada.]**
- **Fazenda de teste:** o cenário de exemplo do RuFaS, com um ano de simulação e formulação automática. **[PENDENTE: fazendas do professor.]**

### 4.2 Otimizador SLP
- **Decisão:** kg de matéria seca de cada alimento por vaca por dia.
- **Objetivo:** custo da dieta.
- **Restrições:** as do RuFaS. Energia e proteína metabolizável são não lineares no RuFaS (desconto de NDT, taxas de passagem e `min()`).
- **Iteração:**
  1. lineariza as **funções do próprio RuFaS** por diferenças finitas;
  2. resolve o PL com HiGHS numa região de confiança;
  3. aceita o passo por uma função de mérito com penalidade tirada dos duais.
- **Casos difíceis e fim:** quando a linearização fica inviável, dá um passo de fase 1. No fim, uma restauração garante que a ração atende às restrições não lineares verdadeiras.
- **Ponto inicial:** determinístico.

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
| NASEM ×0,8 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 20 | 84 |
| NASEM ×1,0 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 17 | 85 |
| NASEM ×1,2 | 0,3119 | 0,3139 | 0,3148 | 0,3157 | −0,65% | −0,92% | 81 | 86 |
| NRC ×0,8 | 0,2696 | 0,2696 | 0,2696 | 0,2696 | 0,00% | 0,00% | 7 | 63 |
| NRC ×1,0 | 0,2911 | 0,2911 | 0,2949 | 0,2978 | 0,00% | −1,28% | 16 | 53 |
| NRC ×1,2 | 0,3546 | 0,3546 | 0,3581 | 0,3652 | 0,00% | −0,97% | 12 | 72 |

- O SLP empata com o melhor de 100 SLSQPs em 5 casos e fica abaixo de todos no NASEM ×1,2, onde o SLSQP para num ótimo local qualquer que seja o ponto de partida.
- O próprio SLSQP varia até 3% conforme a semente.

### 5.2 Simulação de um ano (fazenda de exemplo, 39 formulações pareadas)

| Lote | SLP mais barato | SLP mais caro | Economia média | Velocidade |
|---|---|---|---|---|
| Vacas em lactação | 4 de 13 | 0 | 0,08% | 2,4× |
| Pré-parto | 3 de 13 | 0 | 0,13% | 2,6 a 2,8× |
| Novilhas | 0 de 13 | 0 | 0,00% | 1,8 a 1,9× |

- Os dois otimizadores formularam com sucesso em 100% dos casos.
- Nenhum evento precisou de nova tentativa, corte de leite ou ração de fallback, nem com o SLSQP nem com o SLP. Esse custo oculto só aparece em cenários mais exigentes. **[PENDENTE: medir nas fazendas do professor.]**

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

Com esses preços, a vaca padrão (35 kg de leite) recebe 17,3 kg de silagem de milho, 9,5 kg de casca de soja, 4,1 kg de farelo e 0,3 kg de caroço de algodão (kg de MS). O custo é de R$ 30,26 por dia, com IOFC de R$ 64,31. O SLP e o SLSQP chegam à mesma ração. **[PENDENTE: comparação nas fazendas do professor, economia anual do rebanho e sensibilidade a ±10% e ±20% nos preços dos principais ingredientes.]**

## 6. Discussão

- **Ganho principal:** com os dados atuais, o ganho de custo do SLP contra o SLSQP é pequeno na média, de 0 a 1,3%, mas sempre a favor do SLP. Ele chega a 0,65% abaixo do melhor SLSQP num caso. O ganho maior é de **confiabilidade**: o resultado é sempre o mesmo e não depende da sorte do ponto inicial, cuja variação chega a 3%. O SLP também é mais rápido.
- **Valor da sensibilidade:** os preços-sombra e as faixas dizem o que realmente limita o custo da dieta e até onde uma decisão de compra continua valendo. O RuFaS não dá essas informações.
- **Peculiaridades do RuFaS** encontradas e mantidas, para fidelidade ao simulador:
  - o teor de fósforo da dieta nunca é atualizado e fica 0;
  - o alojamento é comparado com o texto exato, então `"barn"` em minúsculas dá energia de atividade zero;
  - a unidade do ganho de peso diário está documentada errada.
- **Correções ao trabalho de Brito (2026):**
  - o fator de consumo usa (semana − 3,67) onde o NRC usa +3,67, o que dá consumo negativo no início da lactação;
  - a eficiência da proteína do leite aparece como 0,97 no código e 0,67 no texto;
  - a restrição de energia compara energia digestível com exigência de energia líquida.
- **Limitações:**
  - o SLP acha um ótimo local nas restrições não lineares;
  - o modelo PuLP usa o NDT sem desconto por consumo e ainda não roda dentro da simulação;
  - os preços de volumosos e minerais não vêm do CEPEA.

## 7. Conclusão

A formulação linear substitui a do RuFaS sem perder fidelidade ao modelo:
- custa o mesmo ou menos do que o melhor de 100 execuções do otimizador original;
- é determinística e mais rápida;
- acrescenta a análise de sensibilidade que o simulador não tinha.

**[PENDENTE: conclusão econômica com as fazendas do professor.]**

## 8. Trabalhos futuros

- Rodar as fazendas do professor no modo `compare`, com preços reais e notas fiscais.
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
- **[PENDENTE: referência de livro-texto de PL e sensibilidade, por exemplo Hillier & Lieberman, *Introdução à Pesquisa Operacional*.]**
