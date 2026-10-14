## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.

## Projeto Add-on RuFaS

- O add-on é o projeto do usuário e vive **fora** de `RufSas/RuFaS/`. Essa pasta é só uma cópia de referência do RuFaS: **não edite arquivos dela**. O código do add-on fica em `addon_rufas/`, os testes em `tests/`, e a integração com o RuFaS é feita por subclasse e injeção em tempo de execução.
- Escopo e entregas (modelagem, artefato, integração, comparação e análise econômica): `addon-rufas-otimizacao-dieta.md`.
- Python: use o venv da raiz (`.venv`), com `PYTHONPATH=RufSas/RuFaS` para importar `RUFAS`.
- Os livros NASEM 2021 e NRC 2001 (PDF) estão na raiz; consulte só páginas específicas, nunca inteiros.
