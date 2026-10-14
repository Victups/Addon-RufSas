"""Compares the formulations logged by `addon_rufas.run`: python -m addon_rufas.summarize [results_dir]"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean


def load(results_dir: Path) -> list[dict]:
    """All logged formulation records."""
    return [
        json.loads(line)
        for path in sorted(results_dir.glob("*/formulations_*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def main() -> None:
    records = load(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "results")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    pairs: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for record in records:
        groups[(record["optimizer"], record["animal_combination"])].append(record)
        if "shadow" in record:
            groups[(record["shadow"]["optimizer"] + " (shadow)", record["animal_combination"])].append(record["shadow"])
            pairs[record["animal_combination"]].append((record, record["shadow"]))

    print(f"{'optimizer':15} {'group':10} {'n':>4} {'ok %':>6} {'cost/cow/day':>13} {'ms/solve':>9} {'iters':>6} {'DMI kg':>7}")
    for (optimizer, group), rows in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        print(
            f"{optimizer:15} {group:10} {len(rows):4d} {100 * mean(r['success'] for r in rows):6.1f} "
            f"{mean(r['cost'] for r in rows):13.4f} {1000 * mean(r['seconds'] for r in rows):9.1f} "
            f"{mean(r['iterations'] for r in rows):6.1f} {mean(r['dmi'] for r in rows):7.2f}"
        )

    if pairs:
        print("\nPaired (same problem solved by both; both successful):")
        print(f"{'group':10} {'n':>4} {'LP cheaper':>11} {'LP dearer >0.1%':>16} {'mean saving %':>14} {'speedup x':>10}")
        for group, rows in sorted(pairs.items()):
            both = [(lp, sl) for lp, sl in rows if lp["success"] and sl["success"]]
            if not both:
                continue
            saving = [100 * (sl["cost"] - lp["cost"]) / sl["cost"] for lp, sl in both if sl["cost"] > 0]
            print(
                f"{group:10} {len(both):4d} {sum(s > 0.1 for s in saving):11d} {sum(s < -0.1 for s in saving):16d} "
                f"{mean(saving):14.2f} {mean(sl['seconds'] for _, sl in both) / mean(lp['seconds'] for lp, _ in both):10.1f}"
            )


if __name__ == "__main__":
    main()
