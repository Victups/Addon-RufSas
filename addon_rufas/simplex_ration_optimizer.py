"""
Least-cost ration with PuLP and the simplex method, on RuFaS's own NASEM constraints.

How it works, in three sentences. Every NASEM supply in RuFaS is a sum over feeds of (kg of the feed) x (value per kg),
and the value per kg depends on a few numbers of the whole ration: dry matter intake, total starch, share of
concentrate and the TDN intake discount. With those numbers fixed at the current ration, every constraint is a
linear inequality and the simplex method solves the problem; then the numbers are recomputed with the new ration and
the simplex runs again, until the ration stops changing.

No derivative or gradient is used. Each row of the linear program is one RuFaS constraint, listed in `_rows`.
"""

from typing import Any, Optional, Sequence
from unittest.mock import patch

import numpy as np
import pulp
from scipy.optimize import OptimizeResult

from RUFAS.biophysical.animal.animal_module_constants import AnimalModuleConstants
from RUFAS.biophysical.animal.nutrients.nutrition_supply_calculator import FeedInRation
from RUFAS.biophysical.animal.nutrients.nutrition_supply_calculator import NutritionSupplyCalculator as Supply
from RUFAS.biophysical.animal.ration import ration_optimizer as base_module
from RUFAS.biophysical.animal.ration.ration_optimizer import RationConfig, RationOptimizer
from RUFAS.data_structures.feed_storage_to_animal_connection import RUFAS_ID, NutrientStandard

MARGIN = 1e-5  # relative slack added to each requirement, so the ration passes RuFaS's strict `>= 0` check


class SimplexRationOptimizer(RationOptimizer):
    """
    Drop-in replacement for `RationOptimizer` (NASEM only): same problem setup, bounds and constraint functions, and
    only the SLSQP call is swapped for the simplex. The result is deterministic.
    """

    MAX_ROUNDS = 20  # simplex runs per start; the ration usually stops changing after 3 to 9
    DMI_LEVELS = 5  # fixed intakes tried between RuFaS's minimum and maximum, besides the free one
    TOLERANCE = 1e-6  # kg; the ration "stopped changing" when no feed moves more than this

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
        """Runs RuFaS's own setup (config, bounds, constraints) and swaps only its SLSQP `minimize` call."""
        if kwargs.get("nutrient_standard") is not NutrientStandard.NASEM:
            raise ValueError("o otimizador simplex usa só as restrições NASEM do RuFaS")

        def solve_with_simplex(_objective: Any, initial_decision_vector: Any, **solver_kwargs: Any) -> OptimizeResult:
            return self._solve(
                np.asarray(initial_decision_vector, dtype=float),
                solver_kwargs["bounds"],
                solver_kwargs["constraints"],
                solver_kwargs["args"],
            )

        with patch.object(base_module, "minimize", solve_with_simplex):
            return super().attempt_optimization(*args, **kwargs)

    def _solve(
        self,
        start: np.ndarray,
        bounds: list[tuple[float, float]],
        constraints: Sequence[dict[str, Any]],
        config: RationConfig,
    ) -> OptimizeResult:
        """
        Runs `_solve_from` with the dry matter intake free and fixed at `DMI_LEVELS` values inside RuFaS's DMI limits,
        and keeps the cheapest feasible ration. Why: in NASEM, intake changes the value per kg of every feed (fiber and
        starch digestibility, passage rates), and the rounds with intake fixed cannot see that effect.
        """
        lower, upper = np.array(bounds, dtype=float).T
        fraction = config.dmi_constraint_fraction
        dmi_min = config.animal_requirements.dry_matter * (1 - fraction)
        dmi_max = config.initial_dry_matter_requirement * (1 + fraction)
        levels = [None] + list(np.linspace(dmi_min, dmi_max, self.DMI_LEVELS + 2)[1:-1])
        results = []
        for dmi in levels:
            begin = start if dmi is None or start.sum() <= 0 else np.clip(start * dmi / start.sum(), lower, upper)
            results.append(self._solve_from(begin, bounds, constraints, config, dmi))
        best = min(results, key=lambda result: (not result.success, result.fun))
        best.nit = max(result.nit for result in results)
        return best

    def _solve_from(
        self,
        start: np.ndarray,
        bounds: list[tuple[float, float]],
        constraints: Sequence[dict[str, Any]],
        config: RationConfig,
        dmi: Optional[float] = None,
    ) -> OptimizeResult:
        """The rounds of fixed whole-ration numbers + simplex, from `start`; with `dmi`, total intake is fixed to it."""
        lower, upper = np.array(bounds, dtype=float).T
        price = np.array(config.price_list, dtype=float)
        ration = np.clip(start, lower, upper)
        best: Optional[np.ndarray] = None
        message = "O simplex não encontrou ração: as exigências não cabem nos limites dos alimentos."
        rounds = 0
        for rounds in range(1, self.MAX_ROUNDS + 1):
            rows = self._rows(config, ration)
            new = self._simplex(rows, price, lower, upper, dmi=dmi)
            phase_one = new is None
            if phase_one:  # no ration meets the rows: take the one that misses them the least, and try again from it
                new = self._simplex(rows, price, lower, upper, phase_one=True, dmi=dmi)
            if new is None:
                break
            if self._feasible(constraints, new, config) and (best is None or price @ new < price @ best):
                best = new
            converged = float(np.abs(new - ration).max()) <= self.TOLERANCE
            ration = new
            if converged:
                if not phase_one:
                    message = "Optimization terminated successfully."
                break
        else:
            message = "A ração não parou de mudar; devolvida a melhor ração viável encontrada."
        x = best if best is not None else ration
        success = best is not None
        if not success and message.startswith("Optimization"):
            message = "As restrições do RuFaS não foram atendidas."
        return OptimizeResult(x=x, fun=float(price @ x), success=success, message=message, nit=rounds)

    @staticmethod
    def _feasible(constraints: Sequence[dict[str, Any]], x: np.ndarray, config: RationConfig) -> bool:
        """The check RuFaS itself makes: every constraint function of the original model is >= 0."""
        return all(constraint["fun"](x, config) >= 0.0 for constraint in constraints)

    @staticmethod
    def _rows(config: RationConfig, ration: np.ndarray) -> list[tuple[np.ndarray, float]]:
        """
        The NASEM constraints of `RationOptimizer.set_constraints` as linear rows `coefficients @ x >= bound`, with the
        whole-ration numbers (DMI, starch, % concentrate, TDN discount) taken from `ration`. Per-kg values come from
        RuFaS's own supply functions, evaluated for 1 kg of each feed.
        """
        feeds = config.feeds_used
        requirements = config.animal_requirements
        body_weight = config.pen_average_body_weight
        n = len(feeds)
        if ration.sum() <= 0:
            ration = np.full(n, config.initial_dry_matter_requirement / n)
        in_ration = RationOptimizer.convert_decision_vec_to_feeds(config, ration)
        dmi = float(ration.sum())

        def per_kg(function: Any, *extra: Any) -> np.ndarray:
            return np.array([function([FeedInRation(amount=1.0, info=feed)], *extra) for feed in feeds])

        # Net energy (NASEM_net_energy_constraint): efficiency x (digestible energy - gas and urine losses).
        starch = sum(f.amount * f.info.starch / 100 for f in in_ration)
        digestible_energy = per_kg(Supply.calculate_NASEM_digestible_energy, dmi, body_weight, starch)
        losses = Supply.calculate_NASEM_metabolizable_energy(
            [], dmi, body_weight, starch, config.pen_average_enteric_methane, config.pen_average_urine_nitrogen
        )  # with no feed, metabolizable energy is minus the gas and urine energy
        efficiency = Supply.calculate_NASEM_net_energy(1.0)
        energy = efficiency * digestible_energy, requirements.total_energy_requirement - efficiency * losses

        # Metabolizable protein (calculate_metabolizable_protein_supply): microbial protein is 0.64 x min(from TDN,
        # from RDP), plus digestible RUP and 4.72 g endogenous protein per kg DMI. "min >= requirement" is the same as
        # both branches >= requirement, so the minimum becomes two rows.
        discount = Supply.calculate_nutrient_intake_discount(in_ration, body_weight)
        concentrate = Supply._calculate_percentage_of_concentrates(in_ration, dmi)
        passage = Supply._calculate_protein_passage_rates(in_ration, dmi, body_weight, concentrate)
        rdp = Supply._calculate_rumen_degradable_protein_percentages(in_ration, passage)
        rup = Supply._calculate_rumen_undegradable_protein_percentages(in_ration, rdp)
        from_tdn = np.array([0.64 * 0.13 * 1000 * f.TDN * discount / 100 for f in feeds])
        from_rdp = np.array([0.64 * 0.85 * 1000 * rdp[f.rufas_id] / 100 for f in feeds])
        other = np.array([1000 * rup[f.rufas_id] / 100 * f.dRUP / 100 + 0.4 * 11.8 for f in feeds])
        protein = requirements.metabolizable_protein
        # The upper limit uses the branch that is the minimum in the current ration.
        active = from_tdn if from_tdn @ ration <= from_rdp @ ration else from_rdp
        protein_cap = config.initial_protein_requirement * AnimalModuleConstants.PROTEIN_UPPER_LIMIT_FACTOR

        ndf = np.array(config.NDF_list, dtype=float)
        fat = np.array(config.EE_list, dtype=float)
        forage_ndf = per_kg(Supply.calculate_forage_neutral_detergent_fiber_content) * 100
        ones = np.ones(n)
        dmi_fraction = config.dmi_constraint_fraction
        return [
            (per_kg(Supply.calculate_calcium_supply), requirements.calcium),  # calcium_constraint
            (per_kg(Supply.calculate_phosphorus_supply),  # phosphorus_constraint
             max(requirements.phosphorus, requirements.process_based_phosphorus)),
            (from_tdn + other, protein),  # protein_constraint_lower, microbial protein from TDN
            (from_rdp + other, protein),  # protein_constraint_lower, microbial protein from RDP
            (-(active + other), -protein_cap),  # protein_constraint_upper
            (ndf - AnimalModuleConstants.MINIMUM_RATION_NDF, 0.0),  # NDF_constraint_lower, times DMI
            (AnimalModuleConstants.MAXIMUM_RATION_NDF - ndf, 0.0),  # NDF_constraint_upper, times DMI
            (forage_ndf - AnimalModuleConstants.MINIMUM_RATION_FORAGE_NDF, 0.0),  # forage_NDF_constraint, times DMI
            (AnimalModuleConstants.MAXIMUM_RATION_FAT - fat, 0.0),  # fat_constraint, times DMI
            (ones, requirements.dry_matter * (1 - dmi_fraction)),  # DMI_constraint_lower
            (-ones, -config.initial_dry_matter_requirement * (1 + dmi_fraction)),  # DMI_constraint_upper
            energy,  # NASEM_net_energy_constraint
        ]

    @staticmethod
    def _simplex(
        rows: list[tuple[np.ndarray, float]],
        price: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        phase_one: bool = False,
        dmi: Optional[float] = None,
    ) -> Optional[np.ndarray]:
        """
        min price @ x  s.t.  each row coefficients @ x >= bound (+ MARGIN),  lower <= x <= upper. None if infeasible.

        With `phase_one`, each row gets a shortfall variable and the simplex minimizes the total relative shortfall
        instead of the cost (phase 1 of the simplex method): the ration that misses the requirements the least.
        With `dmi`, the total intake is fixed: sum(x) == dmi.
        """
        model = pulp.LpProblem("ration", pulp.LpMinimize)
        x = [model.add_variable(f"x{i}", lowBound=float(lo), upBound=float(up)) for i, (lo, up) in enumerate(zip(lower, upper))]
        shortfalls = []
        for k, (coefficients, bound) in enumerate(rows):
            scale = max(1.0, abs(bound))
            supply = pulp.lpSum(float(c) * xi for c, xi in zip(coefficients, x))
            if phase_one:
                shortfall = model.add_variable(f"s{k}", lowBound=0.0)
                shortfalls.append(shortfall / scale)
                supply = supply + shortfall
            model += supply >= float(bound) + MARGIN * scale
        if dmi is not None:
            model += pulp.lpSum(x) == float(dmi)
        model += pulp.lpSum(shortfalls) if phase_one else pulp.lpSum(float(p) * xi for p, xi in zip(price, x))
        stats = model.solve(pulp.HiGHS(msg=False, solver="simplex"))
        if stats.status != pulp.LpSolveStatus.Optimal:
            return None
        return np.array([xi.value() or 0.0 for xi in x])
