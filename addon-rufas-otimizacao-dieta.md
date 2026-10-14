# Add-on RuFaS — Otimização do Formulador de Dieta

> Documento de escopo do projeto da disciplina. Serve como contexto para a equipe e para IAs de apoio.

---

## 1. Objetivo

O RuFaS **já formula a dieta de menor custo** das vacas, com um otimizador não linear (SLSQP). O projeto entrega um **modelo linear (Programação Linear) de formulação de dieta**, integrado ao RuFaS e comparado com o modelo original, incluindo **análise econômica**.

### Entregas (o que será apresentado ao professor)

| # | Entrega | Conteúdo |
|---|---|---|
| 1 | **Modelagem** | Formulação matemática do problema de dieta como PL (seção 5): variáveis, função objetivo, restrições NASEM/NRC linearizadas, hipóteses e erro introduzido pela linearização. |
| 2 | **Desenvolvimento do artefato** | Classe `LinearRationOptimizer` (HiGHS via `scipy.optimize.linprog`) com a mesma interface de `RationOptimizer.attempt_optimization()`, em `addon_rufas/linear_ration_optimizer.py`. |
| 3 | **Integração** | O add-on vive **fora** de `RufSas/RuFaS/` (cópia de referência, nunca editada). A integração é por subclasse e injeção em tempo de execução: `python -m addon_rufas.run --optimizer slsqp \| lp`. |
| 4 | **Comparação e análise econômica** | Rodar baseline (SLSQP) × PL nos mesmos cenários, com preços CEPEA; comparar custo, viabilidade, tempo e determinismo; quantificar o ganho econômico (seção 8). |

Insumos: **preços reais de mercado (CEPEA)** e exigências **NASEM 2021 / NRC 2001**.

Repositório base: https://github.com/RuminantFarmSystems/RuFaS (Python 3.12/3.13)

---

## 2. Conceitos do domínio

| Termo | Significado |
|---|---|
| **Parto** | Início da lactação. A vaca passa a produzir leite. |
| **Curva de lactação** | Produção sobe após o parto, atinge pico e cai gradualmente. No RuFaS: **curva de Wood** (`l`, `m`, `n`). |
| **DEL** | Dias em lactação (dias desde o último parto). |
| **PEV** | Período de espera voluntária (~60 dias pós-parto) antes da inseminação. |
| **Paridade** | Nº de partos: 1 = primípara, 2 = secundípara, 3+ = multípara. |
| **MS / DMI** | Matéria seca / consumo de matéria seca (kg/dia). Base de cálculo da dieta. |
| **Ciclo** | Parto → lactação → PEV → inseminação → gestação → período seco → novo parto. |

**Inputs das exigências:** leite (kg/dia), gordura e proteína do leite (%), peso vivo, DEL, paridade, dias de gestação.

**Exigências calculadas:** energia líquida, proteína metabolizável, FDN total e de forragem, gordura máx., Ca, P, DMI.

---

## 3. Como o formulador atual funciona (baseline)

| Componente | Arquivo | O que faz |
|---|---|---|
| Otimizador | `RUFAS/biophysical/animal/ration/ration_optimizer.py` | `RationOptimizer.attempt_optimization()` — minimiza `Σ preço × kg` com `scipy.optimize.minimize(method="SLSQP")` |
| Config | mesmo arquivo, `RationConfig` | Exigências, alimentos, preços, limites por ingrediente |
| Chamada | `RUFAS/biophysical/animal/pen.py` → `_attempt_formulation()` | Formula **por baia (pen)** com **médias** dos animais; laço de re-tentativas |
| Exigências NASEM | `RUFAS/biophysical/animal/nutrients/nasem_requirements_calculator.py` | Mantença, crescimento, gestação, atividade, proteína, Ca, P, DMI |
| Exigências NRC | `RUFAS/biophysical/animal/nutrients/nrc_requirements_calculator.py` | Idem, padrão NRC |
| Oferta | `RUFAS/biophysical/animal/nutrients/nutrition_supply_calculator.py` | O que a dieta entrega |
| Curva de lactação | `RUFAS/biophysical/animal/milk/lactation_curve.py` | Wood ajustada por paridade, ano, mês, região |
| Gestão de ração | `RUFAS/biophysical/animal/ration/ration_manager.py` | Dietas do usuário, opções e ajuste de DMI |

**Restrições (NASEM):** `calcium`, `phosphorus`, `protein_lower/upper`, `NDF_lower/upper`, `forage_NDF`, `fat`, `DMI_lower/upper`, `NASEM_net_energy`

### Inputs relevantes

| Arquivo | Campo |
|---|---|
| `input/data/config/*_config.json` | `"nutrient_standard": "NASEM"` ou `"NRC"` |
| `input/data/animal/example_freestall_animal.json` | `ration.formulation_interval` (padrão **30**), `maximum_ration_reformulation_attempts` (padrão **250**) |
| `input/data/feed/*.json` | Alimentos: `feed_type`, `purchased_feed_cost` ($/kg) |
| `input/data/feed/NASEM_Comp_with_TDN.csv` | Composição nutricional dos alimentos |
| `output/output_filters/` | Filtros de saída (renomear `_csv_all_variables.txt` → `csv_all_variables.txt`) |

### Pontos fracos identificados no código (alvos de otimização)

| # | Problema | Onde |
|---|---|---|
| 1 | **Chute inicial aleatório** (`random.random() * 10`) quando não há ração anterior → resultado não determinístico; SLSQP é solver local e depende do chute | `_build_initial_value()` |
| 2 | **Sem gradiente analítico** (jacobiana) → SLSQP estima por diferenças finitas, mais avaliações e mais lento | `minimize(...)` sem `jac` |
| 3 | **Até 250 re-tentativas** por falha, aumentando DMI a cada uma → custo computacional alto e sem diagnóstico prévio de inviabilidade | `pen.py` laço + `_maybe_increased_dmi_for_retry()` |
| 4 | **Fallback para ração anterior** quando falha → vaca recebe dieta que pode não atender exigência atual | `pen.py` |
| 5 | Formulação **por média da baia**, não por animal → vaca de alta produção subalimentada, de baixa superalimentada | `pen.py` |
| 6 | Reformulação a cada **30 dias** → não acompanha a curva de lactação dia a dia | config `formulation_interval` |
| 7 | Maior parte das restrições é **linear** (ou linearizável), mas é resolvida com NLP → sem garantia de ótimo global | `ration_optimizer.py` |
| 8 | Preços de exemplo genéricos, sem mercado brasileiro | `input/data/feed/*.json` |
| 9 | **Banda de DMI de ±30%** (`DMI_CONSTRAINT_FRACTION = 0.30`): o otimizador pode alimentar até 30% a mais de MS que a exigência, e com ingredientes baratos tende a ir ao teto | `animal_module_constants.py`, `DMI_constraint_lower/upper` |

> Validar cada ponto rodando o baseline antes de mexer. Já confirmados em testes (seção 13): pontos 1 e 7 (custo do SLSQP varia entre execuções e para em ótimo local, até ~2% acima da PL) e ponto 9 (DMI foi ao teto de 31,2 kg para exigência de 24 kg).

---

## 4. Escopo das melhorias

Cada melhoria é uma **hipótese** a ser medida contra o baseline (seção 7). O **núcleo da entrega** é M3 (modelo linear) + M6 (preços CEPEA, necessários para a análise econômica).

### Núcleo

#### M3 — Reformulação como Programação Linear
- Linearizar razões (FDN, EE, FDN de forragem) multiplicando pelo `Σ x_i`.
- Resolver com **HiGHS** (`scipy.optimize.linprog(method="highs")`) ou PuLP.
- Ótimo global, determinístico e muito mais rápido.
- Energia e proteína metabolizável **não são lineares** nas funções do RuFaS (desconto de TDN, taxas de passagem, `min()`), e a banda de DMI é de ±30%, então fixar o DMI seria uma linearização ruim.
- **Implementado: PL sequencial (SLP).** A cada iteração as próprias funções de restrição do RuFaS são linearizadas por diferenças finitas no ponto atual, a PL é resolvida com HiGHS dentro de uma região de confiança, e o ponto é aceito por uma função de mérito `custo + μ·violação` (μ vem dos duais da PL). Uma etapa final restaura a viabilidade estrita. Nenhuma fórmula NASEM/NRC é reimplementada, então o modelo acompanha o RuFaS. O resultado é determinístico.
- Quando a linearização é exata (restrições lineares) a PL dá o ótimo global; nas não lineares o SLP converge a um ótimo local (em dieta, o ótimo costuma ser um vértice, e o SLP converge como Newton). A abordagem **híbrida** (PL como ponto de partida, SLSQP refina) fica como alternativa se necessário.

#### M6 — Preços CEPEA
- Coletar indicadores de preço CEPEA (ESALQ/USP) dos ingredientes disponíveis.
- Normalizar para **R$/kg de MS** (teor de MS do CSV de composição).
- Mapear ingrediente → `feed_type` do RuFaS; ingredientes sem indicador (silagem, núcleo mineral) com preço fixo documentado.
- Gerar `feed.json` brasileiro, com preço por data.

### Efeitos colaterais da PL (vêm de graça com M3)
- **M1 — Chute inicial:** deixa de existir; a PL não depende de ponto de partida (resolve o ponto fraco 1).
- **M2 — Jacobiana analítica:** deixa de ser necessária; a PL é linear e o HiGHS usa a própria estrutura (ponto fraco 2).
- **M4 — Diagnóstico de inviabilidade:** o HiGHS retorna o status (`infeasible`) na hora; basta reportar quais restrições conflitam, sem as 250 re-tentativas cegas (ponto fraco 3).

### Extensões (só se sobrar tempo)
- **M5 — Formulação por animal e diária:** `formulation_interval = 1` e formulação individual; só viável porque a PL é rápida.
- **M7 — Multiobjetivo:** custo × metano entérico / N na urina (o RuFaS já calcula as médias NASEM dessas variáveis).

### Integração
- `LinearRationOptimizer` é subclasse de `RationOptimizer` e respeita a interface de `attempt_optimization()`; só troca a chamada `minimize(...)` (SLSQP) pelo solver PL, herdando todo o resto (config, limites, rações do usuário, seleção de restrições).
- **O RuFaS não é modificado.** O runner `python -m addon_rufas.run --optimizer slsqp | lp` troca `pen.RationOptimizer` em tempo de execução e registra cada formulação (tempo, sucesso, custo, DMI, iterações) em `results/<otimizador>/formulations.jsonl`.
- Fica só no add-on: as fazendas que o professor fornecer rodam com os dois otimizadores sem alterar os arquivos delas.

---

## 5. Formulação matemática (PL)

**Variáveis:** `x_i` = kg de MS do ingrediente `i` por vaca/dia

```
min  Σ_i  p_i · x_i                                (p_i = R$/kg MS)

s.a.
DMI_req·(1 − δ) ≤ Σ x_i ≤ DMI_req·(1 + δ)          consumo de MS
Σ x_i · NE_i ≥ NE_req                              energia
PM_min ≤ Σ x_i · PM_i ≤ PM_max                     proteína metabolizável
Σ x_i · (FDN_i − FDN_min) ≥ 0                      FDN mínimo (linearizado)
Σ x_i · (FDN_max − FDN_i) ≥ 0                      FDN máximo (linearizado)
Σ_{i∈forragem} x_i · FDN_i − FDNf_min · Σ x_i ≥ 0  FDN de forragem
Σ x_i · (EE_max − EE_i) ≥ 0                        gordura (linearizado)
Σ x_i · Ca_i ≥ Ca_req
Σ x_i · P_i ≥ P_req
lim_inf_i ≤ x_i ≤ lim_sup_i
```

> No NASEM, energia e proteína dependem do próprio consumo. Fixar o DMI estimado lineariza o problema; documentar o erro introduzido ou usar a abordagem híbrida/sequencial (M3).

---

## 6. Fluxo

```
CEPEA ──► normalização ──► feed.json (R$/kg MS)
                                  │
Animal (DEL, paridade, peso, leite) ──► exigências NASEM/NRC
                                  │
                                  ▼
         Otimizador: SLSQP (baseline) │ PL (artefato)
                                  │
                                  ▼
                 Dieta do dia (kg MS por ingrediente)
                                  │
                                  ▼
       RuFaS simula: leite, peso, reprodução, esterco, metano
                                  │
                                  ▼
       Saída: 1 linha por animal por dia (~3 mil variáveis)
                                  │
                                  ▼
       Logs de desempenho do solver + filtros ──► análise / dashboard
```

---

## 7. Plano de experimentos

O professor exigiu provar **consistência**: funcionar para 1 animal não basta.

### Comparação

**Baseline (SLSQP original)** × **modelo linear (PL/HiGHS)**, nos mesmos cenários, mesmas exigências e mesmos preços. A PL também serve de **referência de ótimo global**: a distância do SLSQP até ela mede a qualidade do baseline.

### Cenários

| Dimensão | Valores |
|---|---|
| Nº de animais | 1, 10, 100, rebanho completo |
| Paridade | 1, 2, 3+ |
| Nível de produção | baixo, médio, alto |
| Duração | 1 ciclo, 2 ciclos |
| Padrão nutricional | NRC, NASEM |
| Intervalo de formulação | 30 dias (original); 7 e 1 só se M5 for feita |
| Granularidade | por baia (original); por animal só se M5 for feita |
| Preços | período estável vs. período de alta |
| Sementes aleatórias | várias (medir determinismo do baseline) |

### Métricas

- **Custo:** R$/vaca/dia, R$/kg de leite, custo total.
- **Viabilidade:** % de sucesso na 1ª tentativa, nº médio de re-tentativas, % de fallback para ração anterior, restrições violadas.
- **Qualidade:** folga de cada restrição (excesso = desperdício), distância do ótimo global (PL como referência).
- **Computacional:** tempo por formulação, nº de iterações/avaliações, tempo total, escalabilidade com nº de animais.
- **Determinismo:** variação do resultado entre execuções com sementes diferentes.
- **Zootécnico/ambiental:** leite produzido, variação de peso, N na urina, metano entérico.
- **Estabilidade:** variação da dieta de um dia para o outro.

---

## 8. Análise econômica

Comparar o custo da dieta do **baseline (SLSQP)** com o da **PL**, nos mesmos animais, exigências e preços CEPEA. A economia só é válida se a dieta atender as exigências (viabilidade) e não reduzir a produção de leite.

| Indicador | Cálculo |
|---|---|
| Custo de alimentação | `Σ p_i · x_i` em **R$/vaca/dia** (p_i = R$/kg MS, x_i = kg MS) |
| Custo por litro/kg de leite | custo de alimentação ÷ leite produzido (R$/kg) |
| **Economia da PL** | `custo_SLSQP − custo_PL` em R$/vaca/dia e em % |
| Economia anual do rebanho | economia/vaca/dia × nº de vacas × 365 (rebanhos de 100 e 1.000 vacas como exemplo) |
| Margem sobre custo de alimentação (IOFC) | receita do leite − custo de alimentação (R$/vaca/dia) |
| Custo evitado de re-tentativas | tempo computacional e dietas de fallback eliminados (efeito na viabilidade, não só no preço) |
| **Sensibilidade a preços** | repetir a comparação com preços estáveis × em alta (±10%, ±20% nos ingredientes principais); ver se a economia aumenta quando os preços sobem |
| **Preço-sombra** | os multiplicadores duais da PL indicam quanto custa cada restrição (ex.: R$ para cada kg extra de exigência de energia); apontam quais ingredientes e restrições mais pesam no custo |
| Custo do modelo (break-even) | esforço de implantação × economia/dia: em quantos dias a PL se paga |

> A PL dá o **ótimo global** para o problema linearizado. Se o SLSQP original encontrar um custo menor, isso indica violação de restrição ou erro de linearização; checar a viabilidade antes de comparar custos.

---

## 9. Entregáveis

1. **Modelagem:** formulação da PL documentada (seção 5), com hipóteses e erro de linearização.
2. **Artefato:** `LinearRationOptimizer` (HiGHS) com a interface de `RationOptimizer.attempt_optimization()`, em `addon_rufas/`.
3. **Integração:** runner `python -m addon_rufas.run --optimizer slsqp | lp`, sem alterar o código do RuFaS.
4. Coletor/normalizador de preços CEPEA + mapeamento de ingredientes (`feed.json` brasileiro).
5. Testes unitários comparando soluções (baseline × PL) em problemas conhecidos.
6. Scripts de execução em lote dos cenários.
7. **Comparação com o modelo do RuFaS** e **análise econômica** (seção 8), em notebook ou dashboard.
8. Relatório final.

---

## 10. Etapas

1. **Setup:** ambiente Python (`.venv` na raiz), rodar o RuFaS de exemplo, entender saídas. ✅
2. **Modelagem:** formulação da PL e linearização das restrições NASEM/NRC (SLP sobre as funções do RuFaS). ✅
3. **Instrumentar o baseline:** registrar tempo, iterações, sucesso, DMI e custo por formulação (`addon_rufas/instrument.py`). ✅ Faltam re-tentativas e fallback.
4. **Artefato:** `LinearRationOptimizer`, validado contra o SLSQP em problemas com alimentos reais da biblioteca NASEM/NRC (`tests/`). ✅
5. **Integração:** runner que injeta o otimizador no RuFaS sem editá-lo. ✅
6. **Preços CEPEA** (M6). ⏳
7. **Bateria de experimentos:** baseline × PL nas fazendas fornecidas pelo professor. ⏳ (aguardando as fazendas)
8. **Análise comparativa e econômica, e relatório.** ⏳
9. *(Extensão)* M5 (formulação diária/por animal) e M7, se sobrar tempo.

---

## 11. Pontos em aberto (validar com o professor)

- ~~O foco é solver ou modelagem?~~ **Definido:** modelo linear (PL), integrado e comparado com o RuFaS, com análise econômica. Confirmar se a **formulação por animal/diária (M5)** entra no escopo.
- Formulação **por animal** ou por **baia/grupo**?
- Padrões: anotações citam "NRC 2021" e "MASEM 2021" — o RuFaS implementa **NRC 2001** e **NASEM 2021**.
- Duração da simulação: "270 + 60 dias" = lactação + período seco?
- Ingredientes obrigatórios na base (milho, farelo de soja, silagem…)?
- Acesso à plataforma de visualização mencionada em aula e ao TCC de referência.
- PEV: 60 dias (aula); no RuFaS é configurável em `farm_level.repro.voluntary_waiting_period`.

---

## 12. Referências

- RuFaS — https://github.com/RuminantFarmSystems/RuFaS
- Documentação RuFaS — https://ruminantfarmsystems.github.io/RuFaS/
- NASEM (2021). *Nutrient Requirements of Dairy Cattle*, 8th rev. ed. National Academies Press.
- NRC (2001). *Nutrient Requirements of Dairy Cattle*, 7th rev. ed. National Academy Press.
- CEPEA / ESALQ-USP — indicadores de preços agropecuários.
- Wood, P.D.P. (1967). Algebraic model of the lactation curve in cattle. *Nature*.
- SciPy — `optimize.minimize` (SLSQP) e `optimize.linprog` (HiGHS).

---

## 13. Status e resultados preliminares

**Reprodução:**

```
.venv\Scripts\python -m pytest                                   # testes do artefato (alimentos reais NASEM/NRC)
.venv\Scripts\python -m addon_rufas.run --optimizer compare -g -v errors -p <task_manager_metadata.json>
.venv\Scripts\python -m addon_rufas.summarize results/compare     # tabela comparativa
```

`--optimizer slsqp | lp | compare`. No modo `compare`, o LP conduz a simulação e o SLSQP resolve em sombra o **mesmo problema** a cada formulação, o que dá dados pareados. Rodar `slsqp` e `lp` separados não é comparável em custo, porque os animais divergem depois da primeira ração diferente. Cenário de teste: `scenarios/smoke/` (fazenda freestall de exemplo, formulação automática, 1 ano). As fazendas do professor entram trocando o `-p`.

### Problema de teste (vaca de 35 kg de leite, alimentos reais da biblioteca, preços de exemplo)

| Padrão | Exigência | Custo SLSQP | Custo LP | Iterações LP |
|---|---|---|---|---|
| NASEM | ×0,8 | 0,2919 | 0,2918 | 5 |
| NASEM | ×1,0 | 0,2920 | 0,2918 | 5 |
| NASEM | ×1,2 | 0,3153 | 0,3119 | 24 |
| NRC | ×0,8 | 0,2696 | 0,2696 | 2 |
| NRC | ×1,0 | 0,2963 | 0,2911 | 4 |
| NRC | ×1,2 | 0,3626 | 0,3546 | 4 |

O LP nunca custa mais que o SLSQP e chega a ~2% menos onde o SLSQP para em ótimo local. O custo do SLSQP muda entre execuções (chute inicial aleatório, ponto fraco 1); o do LP é idêntico (teste de determinismo). Se a exigência é impossível, o LP devolve `success = False`.

### Fazenda de exemplo, 39 formulações pareadas (mesmo problema nos dois)

| Grupo | LP mais barato | LP mais caro (>0,1%) | Economia média | Velocidade (SLSQP/LP) |
|---|---|---|---|---|
| CLOSE_UP | 3 de 13 | 0 | 0,13% | 2,8× |
| GROWING | 0 de 13 | 0 | 0,00% | 1,9× |
| LAC_COW | 4 de 13 | 0 | 0,08% | 2,4× |

Sucesso: 100% nos dois. Iterações: LP ~3, SLSQP 5 a 8.

### Ressalvas
- Os preços do exemplo são genéricos (0,01 a 1,0 por kg), então o **ganho econômico real só aparece com os preços CEPEA** e as fazendas do professor. Os números acima validam a correção e a velocidade, não a economia.
- Para restrições não lineares (energia, proteína) o SLP converge a um ótimo **local**, não global; a garantia de ótimo global vale para a parte linear.
- Quando o problema é inviável, o LP reporta falha, mas ainda não devolve o ponto "mais próximo de viável" (diagnóstico M4 completo fica pendente).
- Ainda não medidos: re-tentativas e fallback do baseline, que a análise comparativa final precisa incluir.
