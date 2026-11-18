"""
Converte a planilha de preços dos colegas (R$/kg na matéria natural) num cenário da página (R$/kg de matéria seca).

    python scenarios/precos/converter_planilha.py "Preços de ingredientes para nutrição de vacas (R$ kg).xlsx"

Gera, nesta pasta, `planilha-2026.csv` (todas as linhas, com a conversão e o que foi feito com cada uma) e
`planilha-2026.json` (o cenário para Importar). Os preços de Goiás (`goias-2026-11.json`) têm prioridade.
"""

import csv
import json
import re
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parents[1] / "RufSas" / "RuFaS" / "input" / "data" / "feed" / "NASEM_Comp_with_TDN.csv"

# Linhas cujo preço não serve para a entrada da biblioteca, e correções provisórias (R$/kg na matéria natural).
SKIP = {"Apple pomace or byproduct, wet": "preço é do bagaço seco; a entrada da biblioteca é o úmido"}
FIX = {"VitTM Premix, generic": (5.00, "proxy era um núcleo probiótico (R$ 149,99/kg); premix comum custa R$ 4 a 6,40/kg")}
# Ração de partida ao importar: os alimentos de Goiás mais calcário, sal e premix (o modelo NRC exige minerais).
SELECTED = [44, 51, 58, 163, 167, 234, 239, 300]
# Teto prático (kg MS/vaca/dia, ~1,2%, 0,6% e 0,8% de 24 kg de MS). Sem ele, o modelo do RuFaS, que não limita
# minerais, usa o calcário barato como enchimento (4 a 7 kg/dia).
MAX = {234: 0.3, 239: 0.15, 300: 0.2}


def key(name: str) -> str:
    """Nome sem a glosa em português entre parênteses, pontuação e maiúsculas."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", name).lower())


def main(xlsx: Path) -> None:
    with LIBRARY.open(encoding="utf-8") as handle:
        library = {key(row["Name"]): row for row in csv.DictReader(handle)}
    aliases = {key("Apple pomace"): key("Apple pomace or byproduct, wet")}
    goias = json.loads((HERE / "goias-2026-11.json").read_text(encoding="utf-8"))

    scenario = {"milk_price": goias["milk_price"], "selected_feeds": SELECTED}
    scenario.update({f"max_{feed_id}": limit for feed_id, limit in MAX.items()})
    out = []
    rows = list(openpyxl.load_workbook(xlsx, data_only=True).active.iter_rows(values_only=True))[1:]
    for number, product, price, origin, source, status, note in rows:
        if not product:
            continue
        feed = library.get(aliases.get(key(product), key(product)))
        if feed is None:
            raise SystemExit(f"alimento sem correspondência na biblioteca: {product}")
        feed_id, name, dm = int(feed["rufas_id"]), feed["Name"], float(feed["DM"])
        action, per_dm = "", None
        if name in SKIP:
            action = "ignorado: " + SKIP[name]
        elif f"cost_{feed_id}" in goias:
            per_dm, action = goias[f"cost_{feed_id}"], "substituído pelo preço de Goiás (goias-2026-11.json)"
        elif not isinstance(price, (int, float)):
            action = "sem preço"
        else:
            if name in FIX:
                price, action = FIX[name][0], "corrigido (provisório): " + FIX[name][1]
            per_dm = round(price / (dm / 100), 4)
        if per_dm is not None:
            scenario[f"cost_{feed_id}"] = per_dm
        out.append({"rufas_id": feed_id, "nome": name, "produto_planilha": product, "rs_kg_natural": price,
                    "ms_pct": dm, "rs_kg_ms": per_dm, "origem": origin, "fonte": source, "status": status,
                    "observacao": note, "tratamento": action})

    with (HERE / "planilha-2026.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    (HERE / "planilha-2026.json").write_text(json.dumps(scenario, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(out)} linhas, {sum(r['rs_kg_ms'] is not None for r in out)} preços no cenário")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
