# Interface local do add-on

Execute na raiz de `Addon-RufSas`:

```bash
pip install -r requirements-web.txt
PYTHONPATH=.:RufSas/RuFaS python -m addon_rufas.web
```

Abra `http://127.0.0.1:5000`.

A interface usa a configuração fictícia Midwest, mas chama diretamente
`LinearRationOptimizer.attempt_optimization`. É possível editar peso corporal,
energia, proteína metabolizável, minerais, matéria seca, preço e limites de
cada alimento. A pasta `RufSas/RuFaS` é somente leitura: a composição é lida
para montar as mesmas estruturas do RuFaS e nenhuma alteração é gravada nela.

Na seção **Otimizador**, escolha entre:

- **Programação linear sequencial (SLP)**: usa `LinearRationOptimizer` do
  add-on e resolve passos lineares com HiGHS;
- **RuFaS original (SLSQP)**: usa `RationOptimizer` original, com
  `scipy.optimize.minimize(method="SLSQP")`.

Os dois recebem exatamente os mesmos valores editados no formulário. O
resultado identifica o método escolhido e exibe custo, ração e margens das
restrições. O SLSQP pode produzir resultados diferentes entre execuções porque
o ponto inicial padrão do RuFaS usa valores aleatórios; isso faz parte do
comportamento original e não foi alterado.
