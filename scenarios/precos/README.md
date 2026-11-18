# Preços reais (Goiás, novembro de 2026)

`goias-2026-11.json` é um cenário para **Importar** na página. Os preços estão em R$ por kg de **matéria seca**: o preço na matéria natural foi dividido pela MS do alimento na biblioteca do RuFaS.

| Ingrediente (id na biblioteca) | Preço na fonte | Fonte e data | R$/kg MS |
|---|---|---|---|
| Leite | R$ 2,7885/litro (÷ 1,032 kg/L) | CEPEA/Esalq, preço ao produtor em Goiás, set/2026 | 2,7020 /kg |
| Milho grão (44), MS 86,9% | R$ 67,14/saca de 60 kg | CEPEA/Esalq, indicador do milho, 10/11/2026 | 1,2876 |
| Farelo de soja 48% (167), MS 89,3% | R$ 2.020/t | Agrolink, Rio Verde (GO), 13/11/2026 | 2,2629 |
| Silagem de milho (51), MS 35,4% | R$ 201/t | TCC Brito (IFG, 2026), fazenda em Goiás, fev/2025 | 0,5684 |
| Caroço de algodão (58), MS 91,4% | R$ 1.000/t | idem | 1,0945 |
| Casca de soja (163), MS 90,4% | R$ 1.030/t | idem | 1,1397 |

Ressalvas:
- O CEPEA cobre só o leite e o milho desta lista. O farelo é uma cotação de praça, e os volumosos e subprodutos vêm de uma fazenda de Goiás, de 2025. Antes do relatório final, troque esses valores por notas fiscais da fazenda estudada.
- O preço do leite de outubro de 2026 ainda não estava publicado quando o arquivo foi montado.
- Não há preço real para minerais e premix. Por isso eles não estão marcados, e o modelo NRC (PuLP), que exige minerais e vitaminas, fica inviável com esta lista sozinha. Inclua os minerais com o preço da nota fiscal.
- Dados do CEPEA sob licença CC BY-NC 4.0. Cite a fonte no relatório.

Resultado (vaca padrão da página, 35 kg de leite, lactação, confinamento, **depois de "Calcular exigências"**): o SLP e o SLSQP deram a mesma ração, a R$ 30,26 por vaca/dia, com IOFC de R$ 64,31 por vaca/dia. Com as exigências padrão da página, sem recalcular, esta lista fica inviável: falta cálcio, e não há mineral marcado.

# Planilha dos colegas (2026)

`planilha-2026.json` é um cenário para **Importar** com preço para **127 dos 175 alimentos** da biblioteca. Ele foi gerado a partir da planilha *Preços de ingredientes para nutrição de vacas (R$ kg).xlsx*, montada pelos colegas da turma:

```powershell
.venv\Scripts\python scenarios\precos\converter_planilha.py "caminho\Preços de ingredientes para nutrição de vacas (R$ kg).xlsx"
```

O script gera dois arquivos:
- `planilha-2026.csv`, com uma linha por item da planilha: id na biblioteca, preço na matéria natural, MS, R$/kg MS, origem, fonte, status, observação e o tratamento aplicado. Cite este arquivo no relatório.
- `planilha-2026.json`, o cenário.

**Sobre a planilha.** Ela tem 174 itens, com os nomes da biblioteca do RuFaS. Por status:

| Status | Itens |
|---|---|
| Verificado | 40 |
| Parcial | 19 |
| Proxy (preço de um produto parecido) | 45 |
| Não verificado | 24 |
| Não encontrado | 46 |

Dos itens com preço, 110 são do mercado brasileiro e 18 foram convertidos de preços do exterior.

**O que o script faz:**
1. **Converte para matéria seca.** A planilha está em R$/kg de matéria natural, e a página usa R$/kg de MS, então o preço é dividido pela MS da biblioteca. Exemplo: silagem a R$ 0,35/kg natural com 35,4% de MS dá R$ 0,99/kg MS. Sem essa conversão, os volumosos pareceriam até 3 vezes mais baratos.
2. **Usa os preços de Goiás** de `goias-2026-11.json` no milho, farelo de soja, silagem, caroço e casca de soja, e no leite (R$ 2,702/kg). São de Goiás e mais recentes. A planilha traz o leite de mai/2026, média Brasil.
3. **Corrige o premix (300)** para R$ 5,00/kg, valor provisório. O proxy da planilha era um núcleo probiótico (BIOLEITE, R$ 149,99/kg), não um premix vitamínico-mineral, que custa de R$ 4 a 6,40/kg.
4. **Ignora o bagaço de maçã (3).** O preço é do produto seco, e a entrada da biblioteca é o úmido.
5. **Põe teto nos minerais:**

   | Mineral | Teto (kg MS/vaca/dia) | Parte da MS |
   |---|---|---|
   | Calcário (234) | 0,3 | ~1,2% |
   | Sal (239) | 0,15 | ~0,6% |
   | Premix (300) | 0,2 | ~0,8% |

   O modelo do RuFaS não limita minerais, e com o calcário a R$ 0,10/kg os otimizadores o usavam como enchimento: o SLP pôs 6,9 kg/dia e o SLSQP 4,1 kg/dia. Os tetos são uma premissa prática, ajuste-os na página se precisar.
6. **Marca 8 alimentos** ao importar: os 5 de Goiás, mais calcário, sal e premix, que o modelo NRC exige.

**Ressalvas da planilha**, a tratar antes do relatório final:
- O calcário (R$ 0,10) é calcário agrícola, e o óxido de magnésio, o cloreto de potássio e os sulfatos têm preço de fertilizante ou de produto industrial, não de grau ração. A análise de faixas mostrou que a ração só muda com preços muito acima desses: calcário acima de R$ 60/kg, sal acima de R$ 325/kg, premix acima de R$ 245/kg. Então o efeito na decisão é pequeno, mas o custo da dieta fica um pouco subestimado.
- O sal (R$ 0,26) é preço de origem em Mossoró, sem frete. No varejo sai a uns R$ 0,75/kg.
- A maior parte das praças é SP, PR, MT e MG. Há dados de 2020 e de mai/2025, e os 18 preços do exterior não são mercado brasileiro.
- Todos os fenos usam o Tifton como proxy, e as silagens de leguminosa usam a silagem de capiaçu.
- Na fazenda que produz a própria silagem, vale o **custo de produção** dela, não o preço de mercado.

**Resultado** (vaca padrão, depois de "Calcular exigências"):

| Modelo | Custo (R$/vaca/dia) | IOFC (R$/vaca/dia) |
|---|---|---|
| SLP (add-on) | 19,73 | 74,84 |
| SLSQP (RuFaS) | 19,72 | 74,85 |
| NRC (PuLP) | 25,64 | 68,93 |

O SLP ficou 0,05% acima do SLSQP. O NRC sai mais caro porque exige também minerais e vitaminas pelas tabelas do NRC 2001. Com os 8 alimentos marcados, o custo cai de R$ 30,26 para R$ 19,73 em relação à lista de Goiás. O principal motivo é que o calcário supre o cálcio que antes vinha de alimentos caros.
