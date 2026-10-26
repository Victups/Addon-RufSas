# Notas dos livros (NRC 2001 e NASEM 2021)

Fonte: `NRC 2001.pdf` (Nutrient Requirements of Dairy Cattle, 7th rev. ed., 406 páginas, texto extraível). O `NASEM 2021` da raiz é um **PDF escaneado** (562 páginas sem camada de texto); só dá para ler com OCR, e ainda não foi lido.

Convenção: "p. N" é a página impressa do livro; "PDF N" é a página do arquivo (PDF = livro + 25).

## Equações usadas no modelo linear

| Item | Equação | Onde |
|---|---|---|
| NEL de um alimento | `NEL (Mcal/kg) = 0,0245 × TDN(%) − 0,12` (Eq. 2-3) | cap. 2 |
| Proteína microbiana (MCP) | `MCP = 0,13 × TDN descontado (kg)`, e no máximo `0,85 × PDR ingerida` | cap. 5 |
| Eficiência da MCP | MCP rende 0,85 da PDR ingerida (1/1,18) | cap. 5 |
| Vitamina A | 110 IU/kg de peso vivo (lactação) | cap. 7 |
| Vitamina D | 30 IU/kg de peso vivo (vacas adultas) | cap. 7 |
| Vitamina E | 0,8 IU/kg de peso vivo, suplementar, quando se usam forragens armazenadas (≈ 20 IU/kg de MS) | cap. 7 |

No RuFaS (`calculate_metabolizable_protein_supply`): `MP = 0,64 × min(0,13·TDN, 0,85·PDR) + PNDR digestível + 0,4 × 11,8 × DMI`. Todas as partes são lineares em `x`, e o `min` se resolve em PL com uma variável auxiliar (`m ≤ a`, `m ≤ b`).

## Tabela 14-7 (p. 266, PDF 291): caso de referência para validar o modelo

Vaca Holstein de 680 kg, 90 dias em lactação, 3,5% de gordura, 3,0% de proteína no leite. Coluna de **35 kg de leite**, DMI previsto 23,6 kg:

| Nutriente | Exigência |
|---|---|
| NEL | 34,8 Mcal/dia (1,47 Mcal/kg) |
| Proteína metabolizável (MP) | 2.407 g/dia (10,2% da MS) |
| PDR (rumen degradável) | 2.298 g/dia (9,7% da MS) |
| PNDR (rumen não degradável) | 1.291 g/dia (5,5% da MS) |
| FDN mínimo | 25 a 33% (ADF mínimo 17 a 21%, NFC máximo 36 a 44%) |
| Cálcio absorvível / na dieta | 65 g/dia / 0,61% |
| Fósforo absorvível / na dieta | 56,5 g/dia / 0,35% |
| Mg, Cl, K, Na, S (% da MS) | 0,19 / 0,26 / 1,04 / 0,23 / 0,20 |
| Co, Cu, I, Fe, Mn, Se, Zn (mg/kg) | 0,11 / 11 / 0,5 / 15 / 14 / 0,3 / 48 |
| Vitamina A / D / E (IU/dia) | 75.000 / 21.000 / 545 |

Dieta de exemplo do próprio livro (kg de MS/dia, mesma coluna): silagem de milho 8,21; farelo de soja 1,62; milho grão floculado 4,33; calcário 0,07; premix de vitaminas e minerais 0,49; mais forragens de leguminosa e gordura (nas linhas de forragem a extração do PDF desalinhou as colunas, então conferir direto no livro, p. 266 a 267). Custo e composição dependem da biblioteca de feeds, então a comparação com o livro é de **viabilidade e composição**, não de custo.

Tabelas vizinhas: 14-4 a 14-6 (vacas de 680 kg por faixa de produção), 14-1 a 14-3 (raças pequenas), 14-8 (vaca recém-parida), 14-9 (vaca seca).

## Dados disponíveis na biblioteca de feeds do RuFaS

| Dado | NASEM (175 feeds) | NRC (134 feeds) |
|---|---|---|
| CP, RUP (% da CP), dRUP, NDF, EE, TDN, DE, Ca, P | sim | sim |
| Mg, K, Na, Cl, S | em ~110 feeds | em ~110 feeds |
| Co, I, Se (traço) | em 12 a 83 feeds | não |
| **Vitaminas A, D, E** | **só 4 feeds** (premix 297 e 300, ração de bezerro 203 e 216) | **nenhum** |

Consequências para o modelo:
- A restrição de vitaminas só é viável se a lista de alimentos incluir um **premix de vitaminas** (feed 300, "VitTM Premix", tem A, D e E; feed 297 só vitamina A). Sem fonte, o modelo avisa e **não** restringe aquela vitamina, em vez de ficar inviável sem explicação.
- No padrão NRC, os dados de vitamina vêm da biblioteca NASEM (o premix é o mesmo).
- Unidade das vitaminas na biblioteca: a documentação diz "% da MS", mas o premix 300 tem A = 560.000, o que só faz sentido como IU/kg de MS. **Confirmar a unidade antes de usar.**

## Pendências de leitura

- Conferir no cap. 5 as equações do desconto de TDN e das taxas de passagem (para explicar a diferença entre o modelo linear e o RuFaS).
- Ler o NASEM 2021 (precisa de OCR): comparar exigências de energia e proteína, e resolver a dúvida "NRC 2021" no `.md`.
