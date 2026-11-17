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


def record_ration_events(pen_class: type, path: Path, name: str) -> None:
    """
    Appends one JSON line per ration reformulation of a pen (`Pen._run_formulation_attempts`) to `path`: how many
    optimizer attempts it took, how many times RuFaS cut the pen's milk production to make the ration feasible, and
    whether it ended in a fallback (the user-defined or the previous ration) instead of a formulated one.

    These are the hidden costs of a failed formulation, which the per-call log above does not show.
    """
    run_attempts = pen_class._run_formulation_attempts
    attempt = pen_class._attempt_formulation
    reduce_milk = pen_class.reduce_milk_production
    path.parent.mkdir(parents=True, exist_ok=True)
    log = open(path, "a", encoding="utf-8")

    @functools.wraps(attempt)
    def counted_attempt(self: Any, *args: Any, **kwargs: Any) -> Any:
        self._addon_event["attempts"] += 1
        return attempt(self, *args, **kwargs)

    @functools.wraps(reduce_milk)
    def counted_reduction(self: Any, *args: Any, **kwargs: Any) -> Any:
        if hasattr(self, "_addon_event"):
            self._addon_event["milk_reductions"] += 1
        return reduce_milk(self, *args, **kwargs)

    @functools.wraps(run_attempts)
    def recorded(self: Any, is_ration_defined_by_user: bool, *args: Any, **kwargs: Any) -> Any:
        self._addon_event = {"attempts": 0, "milk_reductions": 0}
        record = {"optimizer": name, "animal_combination": self.animal_combination.name}
        try:
            solution = run_attempts(self, is_ration_defined_by_user, *args, **kwargs)
        except Exception as error:  # RuFaS raises when milk cannot be reduced any further
            record.update(self._addon_event, success=False, fallback=f"error: {error}")
            raise
        else:
            fallback = None if solution.success else ("user_defined" if is_ration_defined_by_user else "previous_ration")
            record.update(self._addon_event, success=bool(solution.success), fallback=fallback)
            return solution
        finally:
            log.write(json.dumps(record) + "\n")
            log.flush()

    pen_class._attempt_formulation = counted_attempt
    pen_class.reduce_milk_production = counted_reduction
    pen_class._run_formulation_attempts = recorded
