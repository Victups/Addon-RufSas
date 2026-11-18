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

São 39 formulações pareadas por fazenda (13 por lote: lactação, pré-parto e novilhas), 312 no total.

| Fazenda | Custo lactação SLP (R$/vaca/dia) | SLSQP | SLP mais barato | SLP mais caro | Economia/ano |
|---|---|---|---|---|---|
| freestall-midwest | 32,56 | 32,58 | 2 | 0 | R$ 577 |
| freestall-intermountain | 23,66 | 23,66 | 0 | 0 | — |
| freestall-northeast | 23,52 | 23,52 | 0 | 0 | — |
| freestall-southwest | 23,66 | 23,66 | 0 | 0 | — |
| openlot-midwest | 27,59 | 27,61 | 4 | 0 | R$ 5.326 |
| openlot-intermountain | 19,84 | 19,84 | 0 | 0 | — |
| openlot-northeast | 19,73 | 19,73 | 0 | 0 | — |
| openlot-southwest | 19,84 | 19,84 | 0 | 0 | — |

Como ler a tabela:
- "Mais barato" e "mais caro" contam diferenças acima de 0,1%.
- A economia por ano é calculada só para as vacas em lactação: diferença média × número de vacas × 365.

O que os resultados mostram:
- **Viabilidade:** os dois otimizadores formularam com sucesso em 100% dos casos.
- **Robustez:** nenhum evento precisou de nova tentativa, corte de leite ou ração de fallback.
- **Custo:** o SLP **nunca ficou mais caro**. Ele foi mais barato nas listas Midwest, que têm mais alimentos e mais ótimos locais, e empatou nas outras.

**Versão anterior do SLP.** Antes de usar várias partidas, o SLP partia de um único ponto e ficou **1,1% mais caro** na lactação da freestall-midwest. Em 5 de 13 formulações passou do SLSQP, com um caso de +10%. O problema não é convexo, e um único ponto de partida parava num ótimo local pior. Por isso o SLP agora parte de 3 pontos com semente fixa (`EXTRA_STARTS = 2`) e fica com a ração viável mais barata. O resultado continua determinístico, mas cada formulação ficou 2 a 3 vezes mais lenta, de 30 a 110 ms.
