"""
Classic NRC (2001) least-cost ration as a linear program, written in PuLP and solved with HiGHS.

Decision variables: kg of dry matter of each feed per cow per day. Every constraint is linear in them:

- dry matter intake within DMI * (1 +- tolerance);
- net energy of lactation, with feed NEL = 0.0245 * TDN - 0.12 (Mcal/kg DM; NRC 2001, Eq. 2-3);
- RDP (PDR) balance: RDP supply >= 1.18 * microbial CP, with microbial CP = 0.13 * TDN (NRC 2001, ch. 5);
- metabolizable protein = 0.64 * microbial CP + digestible RUP (PNDR) + 0.4 * 11.8 g/kg DMI endogenous.
  Because the RDP balance holds, microbial CP is energy-limited and the NRC min() disappears;
- absorbable Ca and P with the NRC absorption coefficients RuFaS uses (NutritionSupplyCalculator);
- NDF min/max, forage NDF min and fat (EE) max, as % of DM;
- Mg, K, Na, Cl, S (% DM), trace minerals (mg/kg DM) and vitamins A, D, E (IU per kg body weight).

Simplification: TDN is the library value at maintenance, without the NRC discount for intake level.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pulp

# (Ca, P) absorption coefficients by feed type, as RUFAS NutritionSupplyCalculator.calculate_*_supply.
ABSORPTION = {"Forage": (0.30, 0.64), "Conc": (0.60, 0.70), "Mineral": (0.95, 0.80)}

MACRO_MINERALS = {
    "magnesium": "Magnésio",
    "potassium": "Potássio",
    "sodium": "Sódio",
    "chlorine": "Cloro",
    "sulfur": "Enxofre",
}
TRACE_MINERALS = {
    "cobalt": "Cobalto",
    "copper": "Cobre",
    "iodine": "Iodo",
    "iron": "Ferro",
    "manganese": "Manganês",
    "selenium": "Selênio",
    "zinc": "Zinco",
}
VITAMINS = {"Vit_A": "Vitamina A", "Vit_D": "Vitamina D", "Vit_E": "Vitamina E"}

# Defaults: NDF, forage NDF and fat limits are the RuFaS ones, so the comparison is fair; minerals come from
# NRC 2001 Table 14-7 (680 kg cow, 35 kg milk); vitamins from NRC 2001 ch. 7 (IU per kg body weight).
NRC_DEFAULTS: dict[str, float] = {
    "dmi_tolerance": 0.0,
    "ndf_min": 25.0,
    "ndf_max": 45.0,
    "forage_ndf_min": 15.0,
    "fat_max": 7.0,
    "magnesium": 0.19,
    "potassium": 1.04,
    "sodium": 0.23,
    "chlorine": 0.26,
    "sulfur": 0.20,
    "cobalt": 0.11,
    "copper": 11.0,
    "iodine": 0.5,
    "iron": 15.0,
    "manganese": 14.0,
    "selenium": 0.3,
    "zinc": 48.0,
    "Vit_A": 110.0,
    "Vit_D": 30.0,
    "Vit_E": 0.8,
}


@dataclass
class NRCResult:
    success: bool
    message: str
    cost: float
    x: list[float]
    constraints: list[dict[str, Any]] = field(default_factory=list)
    supply: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # rows the elastic LP had to relax when infeasible


def _num(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _diagnose(
    feeds: Sequence[Mapping[str, Any]], rows: Mapping[str, tuple[Any, str, bool]], dmi: float
) -> dict[str, float] | None:
    """
    Why the model is infeasible: the elastic LP.

    Every nutrient row gets a slack s >= 0 and the model minimizes sum(s / size of the row). The rows left with a slack
    are the smallest set of relaxations that makes a ration possible, and the slack says how much is missing. The dry
    matter rows stay hard: more intake loosens every other row, so it would always be the "answer".
    Returns {row name: amount missing, in the row's unit}, or None if even the elastic LP fails.
    """
    elastic = pulp.LpProblem("nrc_elastic", pulp.LpMinimize)
    y = {f"x{i}": elastic.add_variable(f"x{i}", lowBound=_num(f["min"]), upBound=_num(f["max"])) for i, f in enumerate(feeds)}
    slacks = []
    for index, (name, (constraint, unit, per_dm)) in enumerate(rows.items()):
        lhs = pulp.lpSum(c * y[v.name] for v, c in constraint.items()) + constraint.constant
        s = elastic.add_variable(f"s{index}", lowBound=0, upBound=0 if name.startswith("Matéria seca") else None)
        if constraint.sense == pulp.LpConstraintGE:
            elastic += lhs + s >= 0, f"c{index}"
        else:
            elastic += lhs - s <= 0, f"c{index}"
        slacks.append((name, unit, per_dm, s, max(1.0, abs(constraint.constant))))
    elastic += pulp.lpSum(s * (1 / size) for _, _, _, s, size in slacks)
    if elastic.solve(pulp.HiGHS(msg=False)).status != pulp.LpSolveStatus.Optimal:
        return None
    missing = {name: float(s.value() or 0.0) / (dmi if per_dm and dmi else 1.0) for name, _, per_dm, s, _ in slacks}
    return {name: amount for name, amount in missing.items() if amount > 1e-6}


def solve(feeds: Sequence[Mapping[str, Any]], requirements: Mapping[str, float]) -> NRCResult:
    """
    Least-cost ration for `feeds` meeting `requirements`.

    Each feed has id, cost (per kg DM), min, max (kg DM) and the library columns (CP, RUP, dRUP, NDF, EE, TDN,
    calcium, phosphorus, minerals, vitamins, feed_type). `requirements` has energy (Mcal NEL), mp, calcium and
    phosphorus (g absorbable), dmi (kg), body_weight (kg) and the NRC_DEFAULTS keys.
    """
    req = {**NRC_DEFAULTS, **requirements}
    model = pulp.LpProblem("nrc_ration", pulp.LpMinimize)
    x = [model.add_variable(f"x{i}", lowBound=_num(f["min"]), upBound=_num(f["max"])) for i, f in enumerate(feeds)]
    model += pulp.lpSum(_num(f["cost"]) * xi for f, xi in zip(feeds, x))
    total = pulp.lpSum(x)

    def per_kg(column: str) -> list[float]:
        return [_num(f.get(column)) for f in feeds]

    tdn, cp, rup, drup = per_kg("TDN"), per_kg("CP"), per_kg("RUP"), per_kg("dRUP")
    nel = [max(0.0, 0.0245 * t - 0.12) for t in tdn]
    mcp = [0.13 * t * 10 for t in tdn]  # g microbial CP per kg DM (TDN % -> g/kg is * 10)
    rdp = [c * (1 - r / 100) * 10 for c, r in zip(cp, rup)]  # g per kg DM
    drup_g = [c * r / 100 * d / 100 * 10 for c, r, d in zip(cp, rup, drup)]  # digestible RUP, g per kg DM
    mp = [0.64 * m + d + 0.4 * 11.8 for m, d in zip(mcp, drup_g)]
    absorption = [ABSORPTION.get(str(f.get("feed_type")), (0.0, 0.0)) for f in feeds]
    ca = [a[0] * v * 10 for a, v in zip(absorption, per_kg("calcium"))]
    p = [a[1] * v * 10 for a, v in zip(absorption, per_kg("phosphorus"))]
    ndf = per_kg("NDF")
    forage_ndf = [n if f.get("feed_type") == "Forage" else 0.0 for f, n in zip(feeds, ndf)]

    def dot(values: list[float]) -> Any:
        return pulp.lpSum(v * xi for v, xi in zip(values, x))

    # name -> (constraint, unit, per_dm). A per_dm row is a share of DM, sum((v - r) x) >= 0, so one more unit
    # of r costs dual * total DM.
    rows: dict[str, tuple[Any, str, bool]] = {}
    tolerance = req["dmi_tolerance"] / 100
    rows["Matéria seca (mínimo)"] = (total >= req["dmi"] * (1 - tolerance), "kg", False)
    rows["Matéria seca (máximo)"] = (total <= req["dmi"] * (1 + tolerance), "kg", False)
    rows["Energia líquida de lactação"] = (dot(nel) >= req["energy"], "Mcal", False)
    rows["Balanço de PDR (PDR ≥ 1,18 × PB microbiana)"] = (dot([r - 1.18 * m for r, m in zip(rdp, mcp)]) >= 0, "g", False)
    rows["Proteína metabolizável"] = (dot(mp) >= req["mp"], "g", False)
    rows["Cálcio absorvível"] = (dot(ca) >= req["calcium"], "g", False)
    rows["Fósforo absorvível"] = (dot(p) >= req["phosphorus"], "g", False)
    rows["FDN (mínimo)"] = (dot([n - req["ndf_min"] for n in ndf]) >= 0, "% MS", True)
    rows["FDN (máximo)"] = (dot([n - req["ndf_max"] for n in ndf]) <= 0, "% MS", True)
    rows["FDN de forragem (mínimo)"] = (dot([n - req["forage_ndf_min"] for n in forage_ndf]) >= 0, "% MS", True)
    rows["Gordura (máximo)"] = (dot([e - req["fat_max"] for e in per_kg("EE")]) <= 0, "% MS", True)

    warnings = []
    for group, unit in ((MACRO_MINERALS, "% MS"), (TRACE_MINERALS, "mg/kg MS"), (VITAMINS, "UI")):
        for column, label in group.items():
            values = per_kg(column)
            if req[column] <= 0:
                continue
            if not any(values):
                warnings.append(f"{label}: nenhum alimento marcado tem esse dado; a restrição foi ignorada.")
                continue
            if group is VITAMINS:
                rows[label] = (dot(values) >= req[column] * req["body_weight"], unit, False)
            else:
                rows[label] = (dot([v - req[column] for v in values]) >= 0, unit, True)

    for index, (constraint, _, _) in enumerate(rows.values()):
        model += constraint, f"c{index}"
    stats = model.solve(pulp.HiGHS(msg=False))
    optimal = stats.status == pulp.LpSolveStatus.Optimal
    # Without an optimum the solver's values mean nothing; report an empty ration instead.
    amounts = [float(xi.value() or 0.0) if optimal else 0.0 for xi in x]
    result = NRCResult(
        success=optimal,
        message="Solução ótima (PuLP + HiGHS)." if optimal else f"PuLP/HiGHS: {stats.status.name}.",
        cost=sum(_num(f["cost"]) * a for f, a in zip(feeds, amounts)),
        x=amounts,
        warnings=warnings,
    )
    if not optimal:
        missing = _diagnose(feeds, rows, req["dmi"])
        if missing is None:
            result.warnings.append("Não foi possível diagnosticar a inviabilidade.")
        for name, amount in (missing or {}).items():
            result.warnings.append(
                f"{name}: falta {amount:.4g} {rows[name][1]} para a ração ficar viável. "
                "Relaxe essa exigência ou inclua uma fonte."
            )
            result.missing.append(name)
    total_dm = sum(amounts)
    # PuLP 4 keeps the solved constraints (with values and duals) on the problem, in insertion order.
    for (name, (_, unit, per_dm)), constraint in zip(rows.items(), model.constraints()):
        value = float(constraint.value() or 0.0)  # lhs - rhs
        margin = -value if constraint.sense == pulp.LpConstraintLE else value
        scale = max(1.0, abs(constraint.constant), sum(abs(c) * (v.value() or 0.0) for v, c in constraint.items()))
        dual = float(constraint.pi or 0.0) if optimal else 0.0
        shadow_price = abs(dual) * (total_dm if per_dm else 1.0)
        result.constraints.append(
            {"name": name, "slack": margin, "scale": scale, "unit": unit, "shadow_price": shadow_price}
        )
    result.supply = {
        "NEL (Mcal)": sum(a * v for a, v in zip(amounts, nel)),
        "PDR (g)": sum(a * v for a, v in zip(amounts, rdp)),
        "PNDR (g)": sum(a * c * r / 100 * 10 for a, c, r in zip(amounts, cp, rup)),
        "PNDR digestível (g)": sum(a * v for a, v in zip(amounts, drup_g)),
        "Proteína metabolizável (g)": sum(a * v for a, v in zip(amounts, mp)),
        "FDN (% MS)": sum(a * v for a, v in zip(amounts, ndf)) / total_dm if total_dm else 0.0,
    }
    return result
