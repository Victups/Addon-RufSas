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

Resultado (vaca padrão da página, 35 kg de leite, lactação, confinamento): o SLP e o SLSQP deram a mesma ração, a R$ 30,26 por vaca/dia, com IOFC de R$ 64,31 por vaca/dia.
