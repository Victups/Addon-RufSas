# Fazendas de teste

Oito fazendas montadas a partir dos exemplos do próprio RuFaS. O professor não vai enviar fazendas, então estas são as fazendas da comparação econômica.

| Rebanho | Origem | Vacas |
|---|---|---|
| `freestall` | `example_freestall_animal.json` | 100 |
| `openlot` | `example_open_lot_animal.json` | 1.000 |

Cada rebanho é combinado com as 4 listas regionais de alimentos do RuFaS: `example_{Midwest,Intermountain,Northeast,Southwest}_feed.json`.

Mudanças em relação aos exemplos (`gerar.py`):
- só animais, um ano de simulação (2013), como `scenarios/smoke`;
- `ration.user_input: false`, para a ração ser formulada pelo otimizador, e não fixada pelo usuário;
- **preços brasileiros** de [`../precos/planilha-2026.json`](../precos/planilha-2026.json), em R$/kg MS, com os preços de Goiás onde existem;
- os alimentos sem preço na planilha recebem o preço pelo **método de Petersen**, isto é, o valor da energia (NEL) e da proteína (PB) do milho e do farelo de soja:

  | Alimento | R$/kg MS |
  |---|---|
  | Concentrado de bezerra (216) | 1,47 |
  | BP Blend Midwest (302) | 1,61 |
  | BP Blend Northeast (303) | 1,83 |
  | BP Blend South (304) | 1,84 |
  | BP Blend West (305) | 1,66 |

  O concentrado de bezerra vem sem NDT na biblioteca, então assumimos 80%.
- o exemplo Northeast do RuFaS repete o alimento 176, e o RuFaS recusa o arquivo. O gerador remove a duplicata.

## Como rodar

```powershell
.venv\Scripts\python scenarios\fazendas\gerar.py
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p scenarios\fazendas\freestall-midwest\task_manager_metadata.json -o results\fazendas\freestall-midwest\
.venv\Scripts\python -m addon_rufas.summarize results\fazendas\freestall-midwest
```

Uma fazenda free-stall roda em 15–30 s; uma open lot, em até 2 min.

## Resultado (modo `compare`, novembro de 2026)

O add-on conduz a simulação com o **simplex** (PuLP, restrições NASEM do RuFaS), e o SLSQP do RuFaS resolve em sombra o mesmo problema. São 39 formulações pareadas por fazenda (13 por lote: lactação, pré-parto e novilhas), 312 no total.

| Fazenda | Custo lactação simplex (R$/vaca/dia) | SLSQP | Simplex mais barato | Simplex mais caro | Diferença/ano |
|---|---|---|---|---|---|
| freestall-midwest | 32,55 | 32,35 | 0 | 11 (pior: +1,08%) | R$ 7.048 a mais |
| freestall-intermountain | 23,66 | 23,66 | 0 | 0 | — |
| freestall-northeast | 23,52 | 23,52 | 0 | 0 | — |
| freestall-southwest | 23,66 | 23,66 | 0 | 0 | — |
| openlot-midwest | 27,43 | 27,34 | 0 | 9 (pior: +0,77%) | R$ 31.392 a mais |
| openlot-intermountain | 19,84 | 19,84 | 0 | 0 | — |
| openlot-northeast | 19,73 | 19,73 | 0 | 0 | — |
| openlot-southwest | 19,84 | 19,84 | 0 | 0 | — |

Como ler a tabela:
- "Mais barato" e "mais caro" contam diferenças acima de 0,1%.
- A diferença por ano é calculada só para as vacas em lactação: diferença média × número de vacas × 365.

O que os resultados mostram:
- **Viabilidade:** o simplex formulou com sucesso em 100% dos casos; o SLSQP falhou em 2 formulações da openlot-midwest.
- **Robustez:** nenhum evento precisou de nova tentativa, corte de leite ou ração de fallback.
- **Custo:** nas seis fazendas não Midwest, os dois chegaram à mesma ração. Nas duas Midwest, o simplex ficou mais caro na lactação: 0,60% na freestall e 0,31% na open lot.

**Por que Midwest.** É a lista em que a decisão é entre milho grão e silagem. O simplex fixa, em cada rodada, os números que dependem da ração inteira (consumo, amido, % de concentrado). Com eles fixos, o grão parece mais barato do que é, porque o PL não vê que mais grão reduz a digestibilidade da fibra e muda a passagem da proteína de todos os alimentos. O README principal explica isso em "Limite do método". O SLP da branch `integracao-rufas`, que usa derivadas, ficava 0,05% mais barato que o SLSQP nessas mesmas fazendas.
