"""
Runs RuFaS unchanged, optionally with the add-on's `LinearRationOptimizer`.

    python -m addon_rufas.run --optimizer slsqp|lp|compare [RuFaS options, e.g. -p path/to/task_manager_metadata.json]

`compare` runs the simulation with the LP and solves every problem with SLSQP too (paired data, same inputs).
RuFaS reads `input/` relative to its own folder, so the run happens there. Output goes to `results/<optimizer>/`
unless `-o` is given. Every formulation is logged to `<output>/formulations_<pid>.jsonl`.

RuFaS runs simulations in a `multiprocessing.Pool` (spawn on Windows), and each worker re-imports this module. The
optimizer is therefore installed at import time from environment variables, which the workers inherit.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUFAS_DIR = ROOT / "RufSas" / "RuFaS"
OPTIMIZER_VARIABLE = "ADDON_RUFAS_OPTIMIZER"
OUTPUT_VARIABLE = "ADDON_RUFAS_OUTPUT"


def install(optimizer: str, output_dir: Path) -> None:
    """Swaps the ration optimizer used by RuFaS pens and records its formulations. Safe to call once per process."""
    if str(RUFAS_DIR) not in sys.path:
        sys.path.insert(0, str(RUFAS_DIR))
    from RUFAS.biophysical.animal import pen
    from RUFAS.biophysical.animal.ration.ration_optimizer import RationOptimizer
    from addon_rufas.instrument import record_formulations
    from addon_rufas.linear_ration_optimizer import LinearRationOptimizer

    log_path = output_dir / f"formulations_{os.getpid()}.jsonl"
    if optimizer == "slsqp":
        record_formulations(RationOptimizer, log_path, "slsqp")
        return
    pen.RationOptimizer = LinearRationOptimizer  # Pen() builds its optimizer from this module-level name
    shadow = RationOptimizer if optimizer == "compare" else None  # compare: also solve each problem with SLSQP
    record_formulations(LinearRationOptimizer, log_path, "lp", shadow, "slsqp")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--optimizer", choices=["slsqp", "lp", "compare"], default="slsqp")
    options, rufas_args = parser.parse_known_args()

    output_dir = ROOT / "results" / options.optimizer
    if not {"-o", "--output-dir"} & set(rufas_args):
        rufas_args += ["-o", f"{output_dir}/", "-l", f"{output_dir / 'logs'}/"]
    os.environ[OPTIMIZER_VARIABLE] = options.optimizer
    os.environ[OUTPUT_VARIABLE] = str(output_dir)

    install(options.optimizer, output_dir)
    os.chdir(RUFAS_DIR)
    from RUFAS.main import main as rufas_main

    sys.argv = [sys.argv[0], *rufas_args]
    rufas_main()


if OPTIMIZER_VARIABLE in os.environ and __name__ != "__main__":
    install(os.environ[OPTIMIZER_VARIABLE], Path(os.environ[OUTPUT_VARIABLE]))

if __name__ == "__main__":
    main()
