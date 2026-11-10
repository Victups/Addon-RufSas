# Add-on de otimização de dieta para o RuFaS — documentação da implementação

Este documento descreve o artefato entregue. Ele cobre o modelo matemático, a integração com o RuFaS, a análise de sensibilidade, a análise econômica, a interface, os testes e as limitações. O escopo e o plano estão em [`addon-rufas-otimizacao-dieta.md`](../addon-rufas-otimizacao-dieta.md), e as notas tiradas dos livros estão em [`notas-livros.md`](notas-livros.md).

## 1. Visão geral

O **RuFaS** (Ruminant Farm Systems) simula uma fazenda leiteira dia a dia. Para cada lote (*pen*), ele formula a ração de menor custo com `RationOptimizer`, que usa `scipy.optimize.minimize(method="SLSQP")` a partir de um ponto inicial aleatório. O add-on entrega três otimizadores para o mesmo problema. Todos vivem **fora** do código do RuFaS, que não é editado:

| Otimizador | Arquivo | Modelo | Solver | Para que serve |
|---|---|---|---|---|
| **SLSQP** (original) | RuFaS, `RationOptimizer` | Restrições não lineares do RuFaS (NASEM/NRC) | SciPy SLSQP | Linha de base |
| **SLP** (programação linear sequencial) | `addon_rufas/linear_ration_optimizer.py` | O mesmo modelo do RuFaS, linearizado a cada iteração | HiGHS (`scipy.optimize.linprog`) | Substituto direto do SLSQP dentro da simulação. É a comparação justa. |
| **NRC clássico** | `addon_rufas/nrc_lp.py` | PL linear do NRC 2001, com PDR, PNDR, minerais e vitaminas | **PuLP** + HiGHS | Modelo de livro-texto, com preços-sombra exatos |

```
RufSas/RuFaS/ (cópia de referência, só leitura, commit 2114532)
        ▲  importado; nada é alterado
        │
addon_rufas/
├── linear_ration_optimizer.py   SLP: subclasse de RationOptimizer
├── run.py                       roda a simulação RuFaS trocando o otimizador (slsqp | lp | compare)
├── instrument.py                registra custo, tempo e iterações de cada formulação (JSONL)
├── summarize.py                 tabela comparativa SLSQP × SLP
├── nrc_lp.py                    modelo NRC clássico em PuLP
├── web.py + templates/ static/  interface Flask
tests/                           testes com alimentos reais da biblioteca do RuFaS
```

## 2. Integração com o RuFaS

O add-on se conecta ao RuFaS só em tempo de execução, sem tocar nos arquivos dele:

1. **Subclasse.** `LinearRationOptimizer(RationOptimizer)` herda a montagem do problema: alimentos, limites, exigências e funções de restrição. Só troca o solver.
2. **Troca do solver.** Durante `attempt_optimization`, o método substitui `minimize` no módulo `ration_optimizer` por uma função que resolve com o SLP (`unittest.mock.patch.object`). O RuFaS segue o fluxo dele e recebe um `OptimizeResult` como se viesse do SLSQP.
3. **Troca do otimizador na simulação.** `addon_rufas/run.py` aponta `pen.RationOptimizer` para a classe escolhida. O RuFaS simula os lotes num `multiprocessing.Pool`, que no Windows usa *spawn*. Por isso a troca é refeita na importação do módulo, nos processos filhos, pelas variáveis `ADDON_RUFAS_OPTIMIZER` e `ADDON_RUFAS_OUTPUT`.
4. **Modo `compare`.** O SLP conduz a simulação, e o SLSQP resolve **o mesmo problema** em sombra a cada formulação, com o estado aleatório salvo e restaurado. Isso dá pares diretamente comparáveis. Rodar `slsqp` e `lp` em separado não é comparável, porque os animais divergem depois da primeira ração diferente.

```powershell
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\smoke\task_manager_metadata.json
.venv\Scripts\python -m addon_rufas.summarize results\compare
```

O modelo NRC em PuLP roda na interface e nos testes. Ele **ainda não** substitui o otimizador dentro da simulação. Isso exigiria reescrever, no formato do RuFaS, as restrições que o RuFaS confere depois da otimização. Fica como próximo passo (seção 10).

## 3. Modelagem

### 3.1 Variáveis e objetivo (comuns aos três)

`xᵢ` = kg de matéria seca (MS) do alimento *i* por vaca por dia, com `minᵢ ≤ xᵢ ≤ maxᵢ`.

**Objetivo:** `min Σᵢ cᵢ·xᵢ`, com `cᵢ` = preço por kg de MS.

### 3.2 O modelo do RuFaS e o SLP

As restrições do RuFaS (`RationOptimizer.set_constraints`) para vaca em lactação (NASEM) são:
- energia líquida (NASEM);
- cálcio e fósforo;
- proteína metabolizável (mínimo e máximo, com máximo = 1,5 × exigência);
- FDN entre 25% e 45% da MS;
- FDN de forragem ≥ 15%;
- gordura ≤ 7%;
- matéria seca dentro de ±30% da exigência.

Energia e proteína **não são lineares** em `x`: há desconto de NDT, taxas de passagem e um `min()` na proteína microbiana. As proporções em % da MS dividem por `Σx`.

O SLP resolve esse mesmo modelo assim:
1. Lineariza **as próprias funções do RuFaS** no ponto atual, por diferenças finitas: `g(x) + J·(z − x) ≥ 0`.
2. Resolve o PL resultante com HiGHS dentro de uma região de confiança.
3. Aceita o passo se a função de mérito `custo + μ·Σ violações` cair. O peso μ vem dos duais do próprio PL.
4. Quando o PL linearizado é inviável, porque a linearização ficou ruim no ponto, dá um **passo de fase 1** que minimiza a violação, em vez de desistir.
5. No fim, uma **restauração** reaperta as restrições violadas até a ração atender ao modelo **não linear** verdadeiro, que é o que o RuFaS confere.

O ponto inicial é determinístico, então a mesma entrada sempre dá a mesma ração.

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

Exemplo com os alimentos padrão e o SLP: **+15% de proteína metabolizável** faz o custo passar de 0,2918 para 0,5421 (+86%), com custo marginal de 0,00073 por g. Entram silagem de milho, feno, farinha de sangue e mineral, e a silagem de leguminosa sai. Ficam no limite cálcio, PM mínima e FDN máximo.

**2. Preços-sombra (modelo NRC em PuLP).** O dual de cada restrição diz **quanto o custo sobe se a exigência subir 1 unidade**. Restrições com folga têm preço-sombra zero. Nas restrições em % da MS, o dual é convertido para "custo por 1 ponto percentual" (dual × MS total). Os testes conferem que o preço-sombra é igual à diferença finita do custo:
- +0,5 Mcal de energia: previsto 0,119633, observado 0,119633;
- +10 g de PM: previsto 0,001622, observado 0,001622.

Com o SLSQP, parte da diferença entre duas formulações pode ser ruído do ponto inicial aleatório. Para a análise, prefira o SLP ou o PuLP, que são determinísticos.

## 5. Análise econômica

- **Custo da dieta:** `Σ cᵢxᵢ` por vaca por dia.
- **IOFC** (renda sobre o custo de alimentação): `leite (kg) × preço do leite − custo da dieta`, por vaca por dia. Na vaca seca e na novilha a receita é zero. É a métrica usada no TCC anterior do mesmo orientador (seção 9).
- **Comparação SLSQP × SLP:** modo `compare` na simulação e `summarize` para a tabela.
- **Economia anual:** economia por vaca por dia × número de vacas × 365.

**Resultados até agora** (preços de exemplo do RuFaS, de 0,01 a 1,0 por kg):

| Problema de teste (vaca de 35 kg de leite) | Custo SLSQP | Custo SLP |
|---|---|---|
| NASEM, exigência ×1,0 | 0,2920 | 0,2918 |
| NASEM, exigência ×1,2 | 0,3153 | 0,3119 |
| NRC, exigência ×1,2 | 0,3626 | 0,3546 |

| Fazenda de exemplo, 39 formulações pareadas | SLP mais barato | SLP mais caro | Economia média | Velocidade |
|---|---|---|---|---|
| Vacas em lactação | 4 de 13 | 0 | 0,08% | 2,4× |
| Pré-parto (CLOSE_UP) | 3 de 13 | 0 | 0,13% | 2,8× |
| Novilhas (GROWING) | 0 de 13 | 0 | 0,00% | 1,9× |

O SLP **nunca custou mais** que o SLSQP. Ele é **determinístico** e **2 a 3 vezes mais rápido**, e achou ração viável em 100% dos casos. A economia em dinheiro só tem sentido com **preços reais** (CEPEA, seção 7) e as fazendas do professor, porque os preços de exemplo são genéricos.

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
- exportar e importar o cenário em JSON, inclusive arquivos `dietopt-scenario` de outra ferramenta de dieta (veja o README);
- a página "Sobre", que mostra o próprio README convertido de Markdown.

Pedidos simultâneos são atendidos um de cada vez, por uma trava global. O SLP troca uma função global do RuFaS e muda a pasta de trabalho durante a formulação.

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

Para a comparação econômica final, os mesmos preços entram no `feed.json` do cenário da simulação (`purchased_feed_cost`), e roda-se o modo `compare`.

## 8. Testes

`.venv\Scripts\python -m pytest` roda 32 testes, todos com alimentos reais da biblioteca do RuFaS:
- **SLP** (`test_linear_ration_optimizer.py`): ração viável, custo ≤ SLSQP, determinismo e inviabilidade reportada.
- **NRC/PuLP** (`test_nrc_lp.py`): todas as restrições atendidas, preço-sombra igual à diferença finita, e diagnóstico de inviabilidade.
- **Interface** (`test_web.py`):
  - páginas, nomes das restrições, erros de entrada e as três categorias;
  - alojamento, fósforo do processo, IOFC;
  - exportar e importar JSON, inclusive o formato `dietopt-scenario`;
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

**Limites do SLP:** nas restrições não lineares, ele acha um ótimo **local**, como o SLSQP.

**Modelo PuLP:** ainda roda fora da simulação, e o NDT entra sem o desconto por consumo.

**Pendente:**
- rodar as fazendas do professor no modo `compare` com preços CEPEA;
- medir as re-tentativas e o fallback do SLSQP;
- ligar o modelo PuLP dentro da simulação;
- terminar a leitura catalogada dos livros (o NASEM 2021 é escaneado e precisa de OCR).
