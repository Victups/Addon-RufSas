"""
Monta as fazendas de teste a partir dos exemplos do próprio RuFaS, com preços brasileiros.

    python scenarios/fazendas/gerar.py

Fazenda = rebanho de exemplo (free-stall com 100 vacas, open lot com 1.000) × lista regional de alimentos
(Midwest, Intermountain, Northeast, Southwest). Cada uma vira uma pasta com config, animal, feed, metadata e
task_manager_metadata, pronta para `python -m addon_rufas.run --optimizer compare -p <pasta>/task_manager_metadata.json`.

Mudanças em relação ao exemplo: só animais, um ano (2013); ração formulada pelo otimizador (`user_input: false`);
preços de `scenarios/precos/planilha-2026.json` (R$/kg MS). Alimentos sem preço na planilha (concentrado de bezerra e
"BP Blends") recebem o preço pelo método de Petersen: o valor da energia e da proteína do milho e do farelo de soja.
"""

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUFAS = ROOT / "RufSas" / "RuFaS"
HERE = Path(__file__).resolve().parent
SMOKE = ROOT / "scenarios" / "smoke"
HERDS = {"freestall": "example_freestall_animal.json", "openlot": "example_open_lot_animal.json"}
REGIONS = ["Midwest", "Intermountain", "Northeast", "Southwest"]


def petersen(library: dict[int, dict], prices: dict[int, float]) -> callable:
    """Preço (R$/kg MS) = a·NEL + b·PB, com a e b tirados do milho (44) e do farelo de soja (167)."""
    def nel_cp(feed_id: int) -> list[float]:
        row = library[feed_id]
        tdn = float(row["TDN"]) or 80.0  # o concentrado de bezerra (216) vem sem NDT na biblioteca; 80% é o típico
        return [0.0245 * tdn - 0.12, float(row["CP"])]

    a, b = np.linalg.solve([nel_cp(44), nel_cp(167)], [prices[44], prices[167]])
    return lambda feed_id: round(float(a * nel_cp(feed_id)[0] + b * nel_cp(feed_id)[1]), 4)


def main() -> None:
    with (RUFAS / "input" / "data" / "feed" / "NASEM_Comp_with_TDN.csv").open(encoding="utf-8") as handle:
        library = {int(row["rufas_id"]): row for row in csv.DictReader(handle)}
    scenario = json.loads((ROOT / "scenarios" / "precos" / "planilha-2026.json").read_text(encoding="utf-8"))
    prices = {int(key[5:]): value for key, value in scenario.items() if key.startswith("cost_")}
    estimate = petersen(library, prices)
    estimated = {}

    config = json.loads((SMOKE / "config.json").read_text(encoding="utf-8"))
    metadata = json.loads((SMOKE / "metadata.json").read_text(encoding="utf-8"))
    tasks = json.loads((SMOKE / "tasks.json").read_text(encoding="utf-8"))
    for herd, animal_file in HERDS.items():
        animal = json.loads((RUFAS / "input" / "data" / "animal" / animal_file).read_text(encoding="utf-8"))
        animal["ration"]["user_input"] = False
        for region in REGIONS:
            name = f"{herd}-{region.lower()}"
            folder = HERE / name
            folder.mkdir(exist_ok=True)
            rel = f"../../scenarios/fazendas/{name}"  # relative to the RuFaS folder, where the simulation runs
            feed = json.loads((RUFAS / "input" / "data" / "feed" / f"example_{region}_feed.json").read_text(encoding="utf-8"))
            # O exemplo Northeast do RuFaS repete o alimento 176, e o próprio RuFaS recusa o arquivo.
            feed["feeds"] = list({item["feed_type"]: item for item in feed["feeds"]}.values())
            for item in feed["feeds"]:
                feed_id = item["feed_type"]
                if feed_id not in prices:
                    prices[feed_id] = estimated[feed_id] = estimate(feed_id)
                item["purchased_feed_cost"] = prices[feed_id]
            metadata["files"]["config"]["path"] = f"{rel}/config.json"
            metadata["files"]["animal"]["path"] = f"{rel}/animal.json"
            metadata["files"]["feed"]["path"] = f"{rel}/feed.json"
            tasks["tasks"][0].update(metadata_file_path=f"{rel}/metadata.json", output_prefix=name)
            task_manager = {"files": {"tasks": {"title": "Task manager data", "description": "Fazenda de teste.",
                                                "path": f"{rel}/tasks.json", "type": "json",
                                                "properties": "tasks_properties"}}}
            for file_name, data in [("config", config), ("animal", animal), ("feed", feed), ("metadata", metadata),
                                    ("tasks", tasks), ("task_manager_metadata", task_manager)]:
                (folder / f"{file_name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for feed_id, price in sorted(estimated.items()):
        print(f"Petersen: {feed_id} {library[feed_id]['Name']}: R$ {price}/kg MS")


if __name__ == "__main__":
    main()
