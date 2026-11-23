"""
PuLP simplex versus the original SLSQP over many random starts, on the same cases as test_lp_costs_no_more_than_slsqp.

RuFaS starts SLSQP from random.random() * 10 per feed, so a single SLSQP run is one draw. This repeats SLSQP with
seeds 0..N-1 and compares the simplex (deterministic, one run) with the best, mean and worst SLSQP cost, and the time.

    .venv\\Scripts\\python tests\\benchmark_seeds.py [N]
"""

import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "RufSas" / "RuFaS"), str(ROOT / "tests")]

from test_simplex_ration_optimizer import _formulate, _requirements, load_feeds  # noqa: E402

from addon_rufas.simplex_ration_optimizer import SimplexRationOptimizer  # noqa: E402
from RUFAS.biophysical.animal.ration.ration_optimizer import RationOptimizer  # noqa: E402
from RUFAS.data_structures.feed_storage_to_animal_connection import NutrientStandard  # noqa: E402


def timed(optimizer, feeds, requirements):
    started = time.perf_counter()
    solution, _ = _formulate(optimizer, feeds, requirements)
    return solution, time.perf_counter() - started


def main(seeds: int) -> None:
    print(f"{seeds} sementes do SLSQP por caso; custo por vaca/dia; diferença = (simplex - SLSQP) / SLSQP")
    print(f"{'caso':12} {'simplex':>7} {'melhor':>7} {'média':>7} {'pior':>7} {'falhas':>7} "
          f"{'sx-melhor':>11} {'sx-média':>10} {'ms sx':>7} {'ms SLSQP':>9}")
    for standard in (NutrientStandard.NASEM,):  # o simplex usa só as restrições NASEM
        feeds = load_feeds(standard)
        for scale in (0.8, 1.0, 1.2):
            requirements = _requirements(scale)
            lp, lp_seconds = timed(SimplexRationOptimizer(), feeds, requirements)
            costs, seconds, failures = [], [], 0
            for seed in range(seeds):
                random.seed(seed)
                solution, elapsed = timed(RationOptimizer(), feeds, requirements)
                seconds.append(elapsed)
                if solution.success:
                    costs.append(solution.fun)
                else:
                    failures += 1
            best, mean, worst = min(costs), statistics.mean(costs), max(costs)
            print(f"{standard.name + ' x' + str(scale):12} {lp.fun:7.4f} {best:7.4f} {mean:7.4f} {worst:7.4f} "
                  f"{failures:7d} {100 * (lp.fun - best) / best:+10.2f}% {100 * (lp.fun - mean) / mean:+9.2f}% "
                  f"{1000 * lp_seconds:7.0f} {1000 * statistics.mean(seconds):9.0f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
