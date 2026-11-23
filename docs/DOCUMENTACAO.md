# Add-on de otimização de dieta para o RuFaS — documentação da implementação

Este documento descreve o artefato entregue. Ele cobre o modelo matemático, a integração com o RuFaS, a análise de sensibilidade, a análise econômica, a interface, os testes e as limitações. O escopo e o plano estão em [`addon-rufas-otimizacao-dieta.md`](../addon-rufas-otimizacao-dieta.md), e as notas tiradas dos livros estão em [`notas-livros.md`](notas-livros.md).

## 1. Visão geral

O **RuFaS** (Ruminant Farm Systems) simula uma fazenda leiteira dia a dia. Para cada lote (*pen*), ele formula a ração de menor custo com `RationOptimizer`, que usa `scipy.optimize.minimize(method="SLSQP")` a partir de um ponto inicial aleatório. O add-on entrega três otimizadores para o mesmo problema. Todos vivem **fora** do código do RuFaS, que não é editado:

| Otimizador | Arquivo | Modelo | Solver | Para que serve |
|---|---|---|---|---|
| **SLSQP** (original) | RuFaS, `RationOptimizer` | Restrições não lineares do RuFaS (NASEM/NRC) | SciPy SLSQP | Linha de base |
| **Simplex** (PuLP) | `addon_rufas/simplex_ration_optimizer.py` | As mesmas restrições NASEM do RuFaS, com os números da ração inteira fixados a cada rodada | **PuLP** + HiGHS, método simplex | Substituto direto do SLSQP dentro da simulação. É a comparação justa. |
| **NRC clássico** | `addon_rufas/nrc_lp.py` | PL linear do NRC 2001, com PDR, PNDR, minerais e vitaminas | **PuLP** + HiGHS | Modelo de livro-texto, com preços-sombra exatos |

```
RufSas/RuFaS/ (cópia de referência, só leitura, commit 2114532)
        ▲  importado; nada é alterado
        │
addon_rufas/
├── simplex_ration_optimizer.py  simplex (PuLP): subclasse de RationOptimizer
├── run.py                       roda a simulação RuFaS trocando o otimizador (slsqp | lp | compare)
├── instrument.py                registra custo, tempo e iterações de cada formulação (JSONL)
├── summarize.py                 tabela comparativa SLSQP × simplex
├── nrc_lp.py                    modelo NRC clássico em PuLP
├── web.py + templates/ static/  interface Flask
tests/                           testes com alimentos reais da biblioteca do RuFaS
```

## 2. Integração com o RuFaS

O add-on se conecta ao RuFaS só em tempo de execução, sem tocar nos arquivos dele:

1. **Subclasse.** `SimplexRationOptimizer(RationOptimizer)` herda a montagem do problema: alimentos, limites, exigências e funções de restrição. Só troca o solver.
2. **Troca do solver.** Durante `attempt_optimization`, o método substitui `minimize` no módulo `ration_optimizer` por uma função que resolve com o simplex (`unittest.mock.patch.object`). O RuFaS segue o fluxo dele e recebe um `OptimizeResult` como se viesse do SLSQP.
3. **Troca do otimizador na simulação.** `addon_rufas/run.py` aponta `pen.RationOptimizer` para a classe escolhida. O RuFaS simula os lotes num `multiprocessing.Pool`, que no Windows usa *spawn*. Por isso a troca é refeita na importação do módulo, nos processos filhos, pelas variáveis `ADDON_RUFAS_OPTIMIZER` e `ADDON_RUFAS_OUTPUT`.
4. **Modo `compare`.** O simplex conduz a simulação, e o SLSQP resolve **o mesmo problema** em sombra a cada formulação, com o estado aleatório salvo e restaurado. Isso dá pares diretamente comparáveis. Rodar `slsqp` e `lp` em separado não é comparável, porque os animais divergem depois da primeira ração diferente.

```powershell
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\smoke\task_manager_metadata.json
.venv\Scripts\python -m addon_rufas.summarize results\compare
```

O modelo NRC em PuLP roda na interface e nos testes. Ele **ainda não** substitui o otimizador dentro da simulação. Isso exigiria reescrever, no formato do RuFaS, as restrições que o RuFaS confere depois da otimização. Fica como próximo passo (seção 10).

## 3. Modelagem

### 3.1 Variáveis e objetivo (comuns aos três)

`xᵢ` = kg de matéria seca (MS) do alimento *i* por vaca por dia, com `minᵢ ≤ xᵢ ≤ maxᵢ`.

**Objetivo:** `min Σᵢ cᵢ·xᵢ`, com `cᵢ` = preço por kg de MS.

### 3.2 O modelo do RuFaS e o simplex

As restrições do RuFaS (`RationOptimizer.set_constraints`) para vaca em lactação (NASEM) são:
- energia líquida (NASEM);
- cálcio e fósforo;
- proteína metabolizável (mínimo e máximo, com máximo = 1,5 × exigência);
- FDN entre 25% e 45% da MS;
- FDN de forragem ≥ 15%;
- gordura ≤ 7%;
- matéria seca dentro de ±30% da exigência.

Energia e proteína **não são lineares** em `x`: há desconto de NDT, taxas de passagem e um `min()` na proteína microbiana. As proporções em % da MS dividem por `Σx`.

O simplex resolve esse mesmo modelo (só o padrão NASEM) assim:
1. Toda oferta NASEM do RuFaS é uma soma de **quantidade × valor por kg**. O valor por kg depende de poucos números da ração inteira: consumo, amido total, % de concentrado e desconto do NDT. Esses números são **fixados** com a ração atual.
2. Com eles fixos, cada restrição vira uma linha linear. Os valores por kg vêm das próprias funções de oferta do RuFaS, avaliadas para 1 kg de cada alimento. O `min()` da proteína microbiana vira duas linhas (`min(a, b) ≥ R` ⇔ `a ≥ R` e `b ≥ R`), e as proporções da MS são multiplicadas pelo DMI.
3. O PL é resolvido pelo **método simplex** (`pulp.HiGHS(solver="simplex")`).
4. Os números são recalculados com a ração nova, e o simplex roda de novo até a ração parar de mudar (3 a 11 rodadas; no máximo 20).
5. Se o PL não tem solução, usa a **fase 1 do simplex** (folgas nas linhas, minimizando a falta total) e tenta de novo a partir dessa ração.
6. Repete com o consumo livre e com o consumo fixado em 5 níveis entre o mínimo e o máximo do RuFaS, e fica com a ração mais barata que passa na checagem das funções originais do RuFaS (todas `≥ 0`).

Não há derivadas. **Limite:** com os números fixos, o PL não vê que trocar um alimento muda o valor por kg dos outros. Trocar silagem por grão, por exemplo, aumenta o amido e o concentrado, o que reduz a digestibilidade da fibra de toda a ração. Por isso o simplex pode parar numa ração viável um pouco mais cara que a do SLSQP quando a escolha é entre grão e silagem (seção 5). O README tem o passo a passo e a tabela das linhas.

**Re-tentativas e fallback.** Quando a formulação de um lote de vacas em lactação falha, o RuFaS (`Pen._run_formulation_attempts`) tenta de novo, cortando a produção de leite exigida ou aumentando o consumo de matéria seca. Se ainda assim falha, usa a ração anterior ou a definida pelo usuário. O `run.py` registra cada evento de reformulação em `events_<pid>.jsonl`, com o número de tentativas, os cortes de leite e o fallback, e o `summarize` mostra a tabela. Na fazenda de exemplo não houve nenhuma falha, nem com o SLSQP nem com o simplex: 1 tentativa por evento.

### 3.3 O modelo NRC clássico (PuLP)

Unidades: os teores vêm da biblioteca do RuFaS (`NASEM_Comp_with_TDN.csv`):
- PB, FDN, EE e macrominerais em % da MS;
- RUP em % da PB e dRUP em % da RUP;
- microminerais em mg/kg;
- vitaminas em UI/kg.

| Restrição | Forma linear | Fonte |
|---|---|---|
| Matéria seca | `DMI·(1 − t) ≤ Σx ≤ DMI·(1 + t)`; t = tolerância, 0 por padrão | NRC 2001 |
| Energia líquida de lactação | `Σ NELᵢ·xᵢ ≥ ELL exigida`, com `NELᵢ = 0,0245·NDTᵢ − 0,12` (Mcal/kg) | NRC 2001, Eq. 2-3 |
| Balanço de PDR | `Σ PDRᵢ·xᵢ ≥ 1,18 · Σ PBmicᵢ·xᵢ`, com `PBmicᵢ = 0,13·NDTᵢ` | NRC 2001, cap. 5 |
| Proteína metabolizável | `Σ (0,64·PBmicᵢ + PNDRdigᵢ + 0,4·11,8)·xᵢ ≥ PM exigida` | NRC 2001, cap. 5 |
| Ca e P absorvíveis | `Σ aᵢ·Caᵢ·xᵢ ≥ Ca exigido`; idem P. `aᵢ` vem do tipo: forragem 0,30/0,64; concentrado 0,60/0,70; mineral 0,95/0,80 | Coeficientes que o RuFaS usa (`NutritionSupplyCalculator`) |
| FDN, FDN de forragem, gordura | `Σ (vᵢ − r)·xᵢ ≥ 0` (mínimo) ou `≤ 0` (máximo) | Limites do RuFaS: 25–45%, ≥ 15%, ≤ 7% |
| Mg, K, Na, Cl, S | `Σ (vᵢ − r)·xᵢ ≥ 0`, r em % da MS: 0,19 / 1,04 / 0,23 / 0,26 / 0,20 | NRC 2001, Tabela 14-7 |
| Co, Cu, I, Fe, Mn, Se, Zn | igual, r em mg/kg de MS: 0,11 / 11 / 0,5 / 15 / 14 / 0,3 / 48 | NRC 2001, Tabela 14-7 |
| Vitaminas A, D, E | `Σ Vitᵢ·xᵢ ≥ r·peso`, com r = 110 / 30 / 0,8 UI por kg de peso vivo | NRC 2001, cap. 7 |

A energia, a PM, o Ca, o P e a matéria seca exigidos vêm das mesmas exigências usadas pelos outros dois otimizadores. Assim os três resolvem o mesmo animal. Os limites de minerais e vitaminas podem ser editados na interface. O valor 0 desliga a restrição.

**Como as não linearidades viram lineares:**
- **Proporções na MS:** `Σ vᵢxᵢ / Σ xᵢ ≥ r` equivale exatamente a `Σ (vᵢ − r)·xᵢ ≥ 0`, sem aproximação.
- **O `min()` da proteína microbiana:** o NRC usa `PBmic = min(0,13·NDT; 0,85·PDR)`. Com o balanço de PDR imposto, que é uma recomendação do próprio NRC, o mínimo é sempre o termo da energia, e a PM fica linear. A alternativa exata seria uma variável auxiliar `m ≤ 0,13·NDT` e `m ≤ 0,85·PDR`.
- **Vitaminas por kg de peso:** o peso é um dado, então a restrição é linear.

**Simplificações declaradas:**
- O NDT entra com o valor da biblioteca, sem o desconto do NRC por nível de consumo, que é não linear.
- O consumo de matéria seca é um dado de entrada, não uma função da dieta.
- Um nutriente que nenhum alimento marcado tem na biblioteca é **ignorado com aviso**, em vez de tornar o problema inviável sem explicação.

**Diagnóstico de inviabilidade (PL elástico):** quando não há ração possível, o modelo resolve de novo:
1. Dá uma folga a cada restrição de nutriente.
2. Minimiza a soma das folgas, normalizadas pelo tamanho de cada restrição.
3. Mostra quanto falta de cada nutriente.

A interface sugere as duas melhores fontes daquele nutriente na biblioteca. Por exemplo: "Vitamina A: falta 21.720 UI… Fontes: Vit A premix (297), VitTM Premix (300)". A matéria seca fica fixa nesse diagnóstico, porque aumentá-la afrouxaria todas as outras restrições.

## 4. Análise de sensibilidade

Atende ao pedido: "modificar valores e verificar a nova decisão, quais alimentos aumentaram, quanto aumentou ou diminuiu, se exigir mais energia, qual o impacto, gerar conclusões". São duas ferramentas complementares, da teoria clássica de sensibilidade em PL.

**1. Re-solução com variação (todos os otimizadores).** No painel "Análise de sensibilidade", o usuário escolhe um item e uma variação em %. O item pode ser qualquer exigência, o preço do leite, o preço de um alimento ou um limite do modelo NRC. A página formula antes e depois da mudança e mostra:
- cada alimento, antes, depois e a diferença, em kg MS;
- o custo e o IOFC antes e depois;
- o **custo marginal**, que é Δcusto ÷ Δitem;
- conclusões em texto: o que entrou, saiu, aumentou ou diminuiu, e as restrições **no limite**, que são as que definem o custo. A margem precisa ser menor que 0,05% do tamanho da restrição.

Se a ração não muda, o item não limita a decisão naquela faixa.

Exemplo com os alimentos padrão e o simplex: **+15% de proteína metabolizável** faz o custo passar de 0,2918 para 0,2998 (+2,7%). A mistura de capim e leguminosa (104) sai, e a silagem de leguminosa (110) sobe para 30 kg MS. A proteína metabolizável fica no limite. O SLSQP chega a 0,3017 no mesmo caso.

**2. Preços-sombra, faixas de validade e custos reduzidos (modelo NRC em PuLP).** O dual de cada restrição diz **quanto o custo sobe se a exigência subir 1 unidade**. Restrições com folga têm preço-sombra zero. Nas restrições em % da MS, o dual é convertido para "custo por 1 ponto percentual" (dual × MS total). Os testes conferem que o preço-sombra é igual à diferença finita do custo:
- +0,5 Mcal de energia: previsto 0,119633, observado 0,119633;
- +10 g de PM: previsto 0,001622, observado 0,001622.

A análise de faixas (*ranging*) do HiGHS completa a sensibilidade clássica de PL:
- **Faixa de validade:** para cada restrição, mostra entre que valores da exigência o preço-sombra continua valendo. No caso de teste, a energia vale 0,239 por Mcal entre 33,1 e 35,7 Mcal; acima disso, o custo sobe mais rápido.
- **Custo reduzido:** para cada alimento fora da dieta, mostra quanto o preço precisa cair para ele entrar. O feno, por exemplo, tem 0,56, ou seja, não entraria nem de graça.
- **Faixa de preço:** para cada alimento na dieta, mostra em que intervalo de preço a ração continua ótima.

A página escreve uma leitura em texto para cada alimento. Os testes conferem as faixas resolvendo o problema de novo, logo dentro e logo fora delas.

Com o SLSQP, parte da diferença entre duas formulações pode ser ruído do ponto inicial aleatório. Para a análise, prefira o simplex ou o modelo NRC, que são determinísticos.

## 5. Análise econômica

- **Custo da dieta:** `Σ cᵢxᵢ` por vaca por dia.
- **IOFC** (renda sobre o custo de alimentação): `leite (kg) × preço do leite − custo da dieta`, por vaca por dia. Na vaca seca e na novilha a receita é zero. É a métrica usada no TCC anterior do mesmo orientador (seção 9).
- **Comparação SLSQP × simplex:** modo `compare` na simulação e `summarize` para a tabela.
- **Diferença anual:** diferença por vaca por dia × número de vacas × 365.

**Contra o melhor SLSQP.** O SLSQP do RuFaS parte de um ponto sorteado (`random.random() * 10` por alimento). Por isso, comparar com uma única execução dele pode favorecer o simplex por sorte. Em `tests/benchmark_seeds.py`, o SLSQP roda com as sementes 0 a 99 em cada caso de teste (preços de exemplo do RuFaS), e o simplex roda uma vez:

| Caso | Simplex | Melhor SLSQP | Média SLSQP | Pior SLSQP | Simplex × melhor | Simplex × média | ms simplex | ms SLSQP |
|---|---|---|---|---|---|---|---|---|
| NASEM ×0,8 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 33 | 112 |
| NASEM ×1,0 | 0,2918 | 0,2918 | 0,2920 | 0,2921 | −0,01% | −0,06% | 38 | 97 |
| NASEM ×1,2 | 0,3119 | 0,3139 | 0,3148 | 0,3157 | **−0,65%** | −0,92% | 58 | 109 |

- O simplex **empata com o melhor de 100 SLSQPs** em 2 casos e é **0,65% mais barato do que todas as 100 execuções** no NASEM ×1,2.
- Ele leva de 33 a 58 ms, contra 97 a 112 ms de **uma** execução do SLSQP.

**Fazenda de exemplo do RuFaS** (preços genéricos, 39 formulações pareadas): o simplex foi mais barato em 6 formulações e nunca mais caro.

**Fazendas com preços brasileiros.** O professor não vai enviar fazendas. Por isso a comparação econômica usa 8 fazendas montadas com os exemplos do RuFaS ([`scenarios/fazendas/`](../scenarios/fazendas/README.md)): rebanhos free-stall (100 vacas) e open lot (1.000 vacas), cada um com as 4 listas regionais de alimentos, e os preços de `planilha-2026.json`. Resultados:
- **312 formulações pareadas**: o simplex formulou com sucesso em 100%; o SLSQP falhou em 2;
- nenhuma re-tentativa, corte de leite ou fallback;
- nas **6 fazendas não Midwest**, os dois chegaram à mesma ração;
- nas **2 fazendas Midwest**, o simplex ficou mais caro na lactação: **0,60%** na freestall (11 de 39 pares acima de 0,1%, o pior com 1,08%) e **0,31%** na open lot (9 de 39). Isso dá cerca de **R$ 7 mil/ano** no rebanho de 100 vacas e **R$ 31 mil/ano** no de 1.000;
- o custo da dieta de lactação ficou entre **R$ 19,73 e R$ 32,55 por vaca/dia**;
- tempo por formulação: 23 a 52 ms no simplex, 10 a 73 ms no SLSQP.

A diferença nas fazendas Midwest vem do limite do método (seção 3.2): a escolha ali é entre milho grão e silagem, e com os números da ração fixos o grão parece mais barato do que é. Para comparação, o SLP da branch `integracao-rufas`, que usa derivadas, ficava 0,05% mais **barato** que o SLSQP nessas mesmas fazendas.

Para reproduzir: `.venv\Scripts\python tests\benchmark_seeds.py 100`.

## 6. Interface

Flask local, aberta com `.venv\Scripts\python -m addon_rufas.web` em `http://127.0.0.1:5000`. O passo a passo de uso está no [README](../README.md). Recursos:
- os três otimizadores;
- as três categorias animais (lactação, seca e novilha), mapeadas para os tipos e lotes do RuFaS;
- alojamento confinamento ou pasto;
- exigências calculadas pela calculadora NASEM do RuFaS, inclusive o fósforo do processo, que vem do módulo de fósforo dele;
- os 175 alimentos da biblioteca NASEM, com nome, busca e "desmarcar todos";
- preços e limites editáveis;
- IOFC;
- análise de sensibilidade;
- painel do modelo NRC;
- exportar e importar o cenário em JSON, inclusive arquivos `dietopt-scenario` de outra ferramenta de dieta e o `feed.json` de uma fazenda do RuFaS, do qual vêm os alimentos e os preços (veja o README);
- a página "Sobre", que mostra o próprio README convertido de Markdown.

Pedidos simultâneos são atendidos um de cada vez, por uma trava global. O simplex troca uma função global do RuFaS e muda a pasta de trabalho durante a formulação.

## 7. Preços reais: CEPEA

O CEPEA (Esalq/USP) publica indicadores de preço sob a licença CC BY-NC 4.0. O uso acadêmico é livre, desde que a fonte seja citada.

1. Em [cepea.org.br](https://www.cepea.org.br), vá em **Indicadores** e abra a página do produto:
   - [**Leite cru**](https://www.cepea.org.br/br/indicador/leite.aspx): preço médio ao produtor por estado, **inclusive Goiás**, em R$/litro, mensal;
   - **Milho**: Indicador Esalq/B3, em R$ por saca de 60 kg;
   - [**Soja**](https://www.cepea.org.br/br/indicador/soja.aspx): Indicador Paraná, em R$ por saca de 60 kg.
2. Em cada página, clique em **"Série de preços"**, ou use a [área de séries](https://www.cepea.org.br/br/categoria/serie-de-preco.aspx). Escolha a periodicidade (diária, semanal ou mensal) e baixe a planilha. O site pode pedir nome e e-mail.
3. **Converta para o formato da página**, que usa preço por kg de **matéria seca**:
   - grão (saca de 60 kg na matéria natural): `R$/kg MS = (R$/saca ÷ 60) ÷ (MS% ÷ 100)`. Exemplo: milho a R$ 70/saca, com 87% de MS, sai a 70 ÷ 60 ÷ 0,87 = **R$ 1,34/kg MS**;
   - leite: `R$/kg = R$/litro ÷ 1,032`, a densidade do leite.
4. O CEPEA **não cobre** a maioria dos ingredientes: silagem, feno, caroço de algodão, núcleo mineral e premix. Para esses, use as notas fiscais da fazenda, que é o que o TCC de referência fez (R$/tonelada), ou cotações regionais. Converta da mesma forma, dividindo por 1.000 e pela MS.
5. Coloque os preços na página, ou num JSON de cenário. Usar reais nos alimentos e no leite deixa custo e IOFC em R$:

```json
{"milk_price": 2.35, "cost_44": 1.34, "cost_50": 0.62, "selected_feeds": [44, 50, 95, 104, 300, 234, 239]}
```

**Preços já coletados:** [`scenarios/precos/goias-2026-11.json`](../scenarios/precos/goias-2026-11.json) tem o leite (CEPEA, Goiás, set/2026), o milho (CEPEA, 10/11/2026), o farelo de soja (Rio Verde, 13/11/2026) e silagem, caroço e casca de soja (fazenda de Goiás, 2025). As fontes e as ressalvas estão no [README da pasta](../scenarios/precos/README.md). Com esses preços, depois de "Calcular exigências", a vaca padrão sai a R$ 30,26 por dia, com IOFC de R$ 64,31.

**Planilha dos colegas:** [`scenarios/precos/planilha-2026.json`](../scenarios/precos/planilha-2026.json) tem preço para 127 dos 175 alimentos da biblioteca. Ele foi gerado por `converter_planilha.py` a partir da planilha de preços da turma:
- os preços foram convertidos de matéria natural para MS;
- os preços de Goiás têm prioridade;
- o premix foi corrigido para R$ 5/kg, porque o proxy da planilha era um núcleo probiótico;
- calcário, sal e premix receberam teto de 0,3, 0,15 e 0,2 kg MS/dia.

O teto é necessário porque o modelo do RuFaS não limita minerais: sem ele, o calcário a R$ 0,10/kg entra como enchimento, com 4 a 7 kg/dia.

Resultado: simplex R$ 19,74, SLSQP R$ 19,72 e NRC/PuLP R$ 25,64 por vaca/dia. O `planilha-2026.csv` registra o status de cada preço (verificado, parcial, proxy, não verificado) e o tratamento dado.

**Sensibilidade a ±10% e ±20%** nos preços de silagem, caroço, farelo, milho e casca de soja: [`sensibilidade.md`](../scenarios/precos/sensibilidade.md), gerado por `sensibilidade.py`, que re-resolve cada caso.
- A **silagem de milho** é o que mais pesa. Com ±20% no preço dela, o custo varia ±10,6% no simplex e ±5,3% no NRC. Depois vêm o farelo (até ±7,8% no NRC) e o caroço (±5,6%).
- O milho grão e a casca de soja não entram na ração, ou entram pouco, e mudam o custo em menos de 1%.
- No **NRC, a ração não muda** em nenhum dos casos. Só o custo varia, o que confirma as faixas de preço da análise de PL.
- No simplex, a ração muda pouco na maioria dos casos. As exceções: com o farelo 20% mais barato, ele troca 4,6 kg de silagem por 1,6 kg de farelo; com o caroço 20% mais barato, +2,4 kg de caroço e −0,9 kg de farelo; com a silagem 20% mais cara, −1,4 kg de silagem e +0,4 kg de farelo.

Para a comparação econômica final, os mesmos preços entram no `feed.json` do cenário da simulação (`purchased_feed_cost`), e roda-se o modo `compare`.

## 8. Testes

`.venv\Scripts\python -m pytest` roda 35 testes, todos com alimentos reais da biblioteca do RuFaS:
- **Simplex** (`test_simplex_ration_optimizer.py`): ração viável, custo ≤ SLSQP, determinismo, inviabilidade reportada e recusa do padrão NRC.
- **NRC/PuLP** (`test_nrc_lp.py`): todas as restrições atendidas, preço-sombra igual à diferença finita, faixas de validade e custo reduzido conferidos por re-solução, e diagnóstico de inviabilidade.
- **Instrumentação** (`test_instrument.py`): contagem de tentativas, cortes de leite e fallback num lote simulado que falha.
- **Interface** (`test_web.py`):
  - páginas, nomes das restrições, erros de entrada e as três categorias;
  - alojamento, fósforo do processo, IOFC;
  - exportar e importar JSON, inclusive o formato `dietopt-scenario`, o `feed.json` de uma fazenda do RuFaS e o cenário de preços da planilha (viável);
  - análise de sensibilidade e o modelo PuLP na página.

## 9. Trabalho relacionado

O TCC *Formulação Nutricional Otimizada como Ferramenta para Aumento de Margem Econômica na Pecuária Leiteira* (Brito, IFG, 2026, mesmo orientador) usou PL do NRC 2001 com `linprog`/HiGHS, IOFC e dados reais de uma fazenda de Goiás. Ele obteve um aumento médio de 9,14% no IOFC. Este artefato difere em três pontos:
- **Usa as calculadoras do próprio RuFaS**, NASEM e NRC, e liga a otimização à simulação da fazenda.
- **Corrige três pontos daquele modelo:**
  - **Consumo de matéria seca:** lá o fator de lactação é `1 − e^(−0,192·(semana − 3,67))`, e o NRC usa **+3,67**. Com −3,67, o consumo fica negativo no início da lactação.
  - **Proteína para o leite:** a eficiência é 0,67, mas o código usou 0,97.
  - **Energia:** a restrição comparava energia **digestível** com exigência de energia **líquida**, que é menor. Isso deixava a energia frouxa e é coerente com a queda de leite previsto que aquele trabalho observou.
- Calcula a proteína metabolizável pela PDR e pela PNDR, e não por PB ÷ 0,64. Também inclui minerais, vitaminas e preços-sombra.

## 10. Limitações e próximos passos

**Peculiaridades do RuFaS** encontradas e mantidas, para os resultados baterem com a simulação:
- **Teor de P da dieta:** `Nutrients.ration_phosphorus_concentration` nunca é atualizado e fica 0. A eficiência de absorção do P na vaca em lactação é sempre a constante 1,867.
- **Alojamento:** as calculadoras comparam o texto com `"Barn"` e `"Grazing"` exatos. As fazendas de exemplo usam `"open air barn"` e `"barn"`, então o NASEM dá energia de atividade **zero** na simulação. Uma fazenda a pasto precisa trazer exatamente `"Grazing"`.
- **Ganho médio diário:** a docstring do RuFaS diz gramas, mas a equação usa kg/dia.
- **Exemplo Northeast:** `example_Northeast_feed.json` repete o alimento 176, e o próprio RuFaS recusa o arquivo. O gerador das fazendas remove a duplicata.
- **Sem teto de minerais:** o modelo do RuFaS não limita minerais. Com calcário barato, o otimizador o usa como enchimento. Os cenários de preço trazem um teto prático.

**Limites do simplex:** os números da ração inteira (consumo, amido, % de concentrado, desconto do NDT) ficam fixos em cada rodada, então o PL não vê que trocar um alimento muda o valor por kg dos outros. Os 5 níveis de consumo reduzem o efeito, mas na troca entre grão e silagem o simplex ainda fica até ~1% mais caro que o SLSQP (fazendas Midwest).

**Modelo PuLP:** ainda roda fora da simulação, e o NDT entra sem o desconto por consumo.

**Dados:**
- as fazendas são os exemplos do RuFaS, com preços brasileiros, porque o professor não vai enviar fazendas;
- os preços são de set–nov/2026, sem notas fiscais;
- o premix é provisório, e os minerais têm preço de grau agrícola.

**Próximos passos:**
- ligar o modelo PuLP dentro da simulação;
- terminar a leitura catalogada dos livros (o NASEM 2021 é escaneado e precisa de OCR).
