from typing import Any, Optional, Sequence
from unittest.mock import patch

import numpy as np
from scipy.optimize import OptimizeResult, linprog

from RUFAS.biophysical.animal.ration import ration_optimizer as base_module
from RUFAS.biophysical.animal.ration.ration_optimizer import RationConfig, RationOptimizer
from RUFAS.data_structures.feed_storage_to_animal_connection import RUFAS_ID


class LinearRationOptimizer(RationOptimizer):
    """
    Least-cost ration formulation by sequential linear programming (SLP) with the HiGHS solver.

    Drop-in replacement for `RationOptimizer`: it inherits the constraint set, bounds and interface, and only
    replaces the solver and the initial point.

    Notes
    -----
    The objective (sum of price * kg) is linear. Most constraints (Ca, P, DMI, and the NDF/forage NDF/fat shares at a
    given DMI) are linear in the decision vector. Energy and metabolizable protein are not (TDN discount, passage
    rates, min()), so each iteration linearizes the *existing* RuFaS constraint functions at the current point with
    finite differences and solves the LP inside a trust region. No NASEM/NRC formula is reimplemented.

    Steps are accepted by an exact-penalty merit function (cost + penalty * constraint violation), with the penalty
    taken from the LP's own dual values. When the optimum is a vertex, as in diet problems, SLP converges like Newton's
    method. A final restoration pass guarantees strict feasibility of the returned ration, which is what RuFaS checks.
    The result is deterministic: no random start.
    """

    MAX_ITERATIONS = 40
    FINITE_DIFFERENCE_STEP = 1e-4  # kg, relative to max(1, x_i)
    CONSTRAINT_MARGIN = 1e-7
    RESTORATION_PASSES = 10
    TOLERANCE = 1e-9
    STEP_TOLERANCE = 1e-6  # kg

    @staticmethod
    def _build_initial_value(
        previous_ration: Optional[dict[RUFAS_ID | str, float | str]], ration_config: RationConfig
    ) -> list[float]:
        """Deterministic start: previous ration if any, else the bounds scaled to reach the DMI requirement."""
        if previous_ration:
            return RationOptimizer._build_initial_value(previous_ration, ration_config)
        lower = np.array(ration_config.feed_minimum_list, dtype=float)
        dmi = ration_config.initial_dry_matter_requirement
        upper = np.minimum(np.array(ration_config.feed_maximum_list, dtype=float), dmi)
        span = np.maximum(upper - lower, 0.0)
        share = np.clip((dmi - lower.sum()) / span.sum(), 0.0, 1.0) if span.sum() > 0 else 0.0
        return list(lower + share * span)

    def attempt_optimization(self, *args: Any, **kwargs: Any) -> tuple[OptimizeResult, RationConfig]:
        """Runs RuFaS's own setup (config, bounds, constraints) and swaps only its SLSQP `minimize` call for the LP."""

        def solve_with_lp(_objective: Any, initial_decision_vector: Any, **solver_kwargs: Any) -> OptimizeResult:
            return self._solve(
                initial_decision_vector,
                solver_kwargs["bounds"],
                solver_kwargs["constraints"],
                solver_kwargs["args"],
            )

        with patch.object(base_module, "minimize", solve_with_lp):
            return super().attempt_optimization(*args, **kwargs)

    def _solve(
        self,
        initial_decision_vector: np.ndarray[tuple[int, ...], np.dtype],
        bounds: list[tuple[float, float]],
        constraints: Sequence[dict[str, Any]],
        ration_config: RationConfig,
    ) -> OptimizeResult:
        lower, upper = np.array(bounds, dtype=float).T
        price = np.array(ration_config.price_list, dtype=float)
        x = np.clip(initial_decision_vector, lower, upper)
        trust = max(float(x.sum()), 1.0)
        penalty = 1.0
        message = "Optimization terminated successfully."
        iteration = 0

        def merit(point: np.ndarray) -> float:
            return float(price @ point + penalty * np.maximum(-self._values(constraints, point, ration_config), 0).sum())

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            lp = self._linear_step(constraints, x, ration_config, price, lower, upper, trust)
            if lp is None:
                message = "Linear program infeasible: the linearized constraints cannot be met within the feed limits."
                break
            candidate, duals = lp
            penalty = max(penalty, 2.0 * float(np.abs(duals).max(initial=0.0)))
            if float(np.abs(candidate - x).max()) <= self.STEP_TOLERANCE * (1.0 + x.sum()):
                break  # the LP says to stay: converged
            if merit(candidate) < merit(x) - self.TOLERANCE * (1.0 + abs(merit(x))):
                x = candidate
            else:
                trust *= 0.5
                if trust < self.STEP_TOLERANCE:
                    break
        else:
            message = "Maximum number of iterations reached."

        x = self._restore_feasibility(constraints, x, ration_config, price, lower, upper)
        success = bool(np.all(self._values(constraints, x, ration_config) >= 0.0))
        if not success and message.startswith("Optimization"):
            message = "The nonlinear constraints could not be satisfied."
        return OptimizeResult(x=x, fun=float(price @ x), success=success, message=message, nit=iteration)

    def _linear_step(
        self,
        constraints: Sequence[dict[str, Any]],
        x: np.ndarray,
        ration_config: RationConfig,
        price: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        trust: float,
        margin: Optional[np.ndarray] = None,
    ) -> Optional[tuple[np.ndarray, np.ndarray]]:
        """
        Solves the LP of the constraints linearized at `x`, inside a trust region of half-width `trust` (kg).

        Returns the new point and the duals of the constraints, or None when the LP is infeasible. If it is infeasible
        inside the trust region, the region is dropped, since infeasibility within the feed limits is real.
        """
        value, jacobian = self._linearize(constraints, x, ration_config)
        margin = self.CONSTRAINT_MARGIN if margin is None else margin
        # g(x) + J (z - x) >= margin  <=>  -J z <= g(x) - J x - margin
        rhs = value - jacobian @ x - margin
        for half_width in (trust, np.inf):
            box = np.column_stack([np.maximum(lower, x - half_width), np.minimum(upper, x + half_width)])
            lp = linprog(price, A_ub=-jacobian, b_ub=rhs, bounds=box, method="highs")
            if lp.status == 0:
                return lp.x, lp.ineqlin.marginals
        return None

    def _restore_feasibility(
        self,
        constraints: Sequence[dict[str, Any]],
        x: np.ndarray,
        ration_config: RationConfig,
        price: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
    ) -> np.ndarray:
        """Re-solves the LP with each violated constraint tightened by twice its violation until none is violated."""
        for _ in range(self.RESTORATION_PASSES):
            violation = np.maximum(-self._values(constraints, x, ration_config), 0.0)
            if not violation.any():
                break
            lp = self._linear_step(
                constraints, x, ration_config, price, lower, upper, 1.0, margin=2.0 * violation + self.CONSTRAINT_MARGIN
            )
            if lp is None:
                break
            x = lp[0]
        return x

    @staticmethod
    def _values(constraints: Sequence[dict[str, Any]], x: np.ndarray, ration_config: RationConfig) -> np.ndarray:
        """Values of all constraints at `x` (non-negative means satisfied)."""
        return np.array([constraint["fun"](x, ration_config) for constraint in constraints], dtype=float)

    @classmethod
    def _linearize(
        cls, constraints: Sequence[dict[str, Any]], x: np.ndarray, ration_config: RationConfig
    ) -> tuple[np.ndarray, np.ndarray]:
        """Returns the values and the Jacobian (forward differences) of all constraints at `x`."""
        value = cls._values(constraints, x, ration_config)
        jacobian = np.empty((len(constraints), len(x)))
        for i in range(len(x)):
            step = cls.FINITE_DIFFERENCE_STEP * max(1.0, abs(x[i]))
            shifted = x.copy()
            shifted[i] += step
            jacobian[:, i] = (cls._values(constraints, shifted, ration_config) - value) / step
        return value, jacobian
