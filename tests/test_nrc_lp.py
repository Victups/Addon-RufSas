import csv
from pathlib import Path

import pytest

from addon_rufas import nrc_lp

LIBRARY = Path(__file__).resolve().parents[1] / "RufSas" / "RuFaS" / "input" / "data" / "feed" / "NASEM_Comp_with_TDN.csv"
REQUIREMENTS = {"energy": 34.8, "mp": 2407, "calcium": 65, "phosphorus": 56.5, "dmi": 23.6, "body_weight": 680}
# corn grain, grass hay, legume silage, VitTM premix, blood meal, corn silage, legume silage, limestone, salt
PRICES = {44: 0.20, 95: 0.15, 104: 0.12, 300: 2.0, 23: 0.35, 50: 0.4, 110: 0.10, 234: 0.08, 239: 0.10}


def number(value):
    try:
        return float(value)
    except ValueError:
        return value


@pytest.fixture(scope="module")
def feeds():
    rows = {int(r["rufas_id"]): r for r in csv.DictReader(LIBRARY.open(encoding="utf-8"))}
    return [
        {**{k: number(v) for k, v in rows[i].items()}, "id": i, "cost": c, "min": 0, "max": 100}
        for i, c in PRICES.items()
    ]


def test_ration_meets_every_constraint(feeds):
    result = nrc_lp.solve(feeds, REQUIREMENTS)
    assert result.success, result.warnings
    assert all(row["slack"] >= -1e-6 for row in result.constraints)
    assert sum(result.x) == pytest.approx(REQUIREMENTS["dmi"])
    assert result.supply["Proteína metabolizável (g)"] >= REQUIREMENTS["mp"] - 1e-6
    assert 25 - 1e-6 <= result.supply["FDN (% MS)"] <= 45 + 1e-6
    assert result.cost == pytest.approx(sum(f["cost"] * a for f, a in zip(feeds, result.x)))


@pytest.mark.parametrize(("key", "name", "step"), [("energy", "Energia líquida de lactação", 0.5), ("mp", "Proteína metabolizável", 10)])
def test_shadow_price_is_the_marginal_cost(feeds, key, name, step):
    base = nrc_lp.solve(feeds, REQUIREMENTS)
    more = nrc_lp.solve(feeds, {**REQUIREMENTS, key: REQUIREMENTS[key] + step})
    shadow = next(row["shadow_price"] for row in base.constraints if row["name"] == name)
    assert more.cost - base.cost == pytest.approx(shadow * step, rel=1e-4, abs=1e-9)


def test_infeasible_model_says_what_is_missing(feeds):
    without_premix = [f for f in feeds if f["id"] != 300]
    result = nrc_lp.solve(without_premix, REQUIREMENTS)
    assert not result.success
    assert "Zinco" in result.missing  # trace minerals only come from the premix
    assert any(w.startswith("Vitamina D: nenhum alimento") for w in result.warnings)  # no data: skipped, not infeasible
    assert sum(result.x) == 0  # no meaningless ration when infeasible
