import functools
import json
import random
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np


def _outcome(solution: Any, seconds: float) -> dict[str, Any]:
    return {
        "seconds": seconds,
        "success": bool(solution.success),
        "cost": float(solution.fun),
        "dmi": float(np.sum(solution.x)),
        "iterations": int(getattr(solution, "nit", -1)),
        "message": str(solution.message),
    }


def record_formulations(
    optimizer_class: type, path: Path, name: str, shadow_class: Optional[type] = None, shadow_name: str = ""
) -> None:
    """
    Appends one JSON line per `attempt_optimization` call (time, success, cost, DMI, iterations) to `path`.

    With `shadow_class`, the same problem is also solved by that optimizer and logged under "shadow". The shadow
    result is never used by RuFaS, and the random state is restored so the simulation is not disturbed.
    """
    original = optimizer_class.attempt_optimization
    path.parent.mkdir(parents=True, exist_ok=True)
    log = open(path, "a", encoding="utf-8")

    @functools.wraps(original)
    def timed(self: Any, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        solution, ration_config = original(self, *args, **kwargs)
        record = {
            "optimizer": name,
            "animal_combination": kwargs["animal_combination"].name,
            "feeds": len(kwargs["pen_available_feeds"]),
            **_outcome(solution, time.perf_counter() - started),
        }
        if shadow_class is not None:
            random_state = random.getstate()
            started = time.perf_counter()
            shadow_solution, _ = shadow_class().attempt_optimization(*args, **kwargs)
            record["shadow"] = {"optimizer": shadow_name, **_outcome(shadow_solution, time.perf_counter() - started)}
            random.setstate(random_state)
        log.write(json.dumps(record) + "\n")
        log.flush()
        return solution, ration_config

    optimizer_class.attempt_optimization = timed
