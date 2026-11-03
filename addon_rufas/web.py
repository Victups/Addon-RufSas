"""Local browser interface for exercising the add-on optimizer.

The page calls ``LinearRationOptimizer.attempt_optimization`` directly. It
does not modify the RuFaS checkout or replace the normal RuFaS runner.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
import json
import math
import os
import sys
import threading
from types import SimpleNamespace
import warnings
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Any, Iterator, Mapping

import numpy as np
from flask import Flask, Response, render_template, request
from werkzeug.datastructures import MultiDict

ROOT = Path(__file__).resolve().parents[1]
RUFAS_DIR = ROOT / "RufSas" / "RuFaS"
if str(RUFAS_DIR) not in sys.path:
    sys.path.insert(0, str(RUFAS_DIR))

from addon_rufas import nrc_lp
from addon_rufas.linear_ration_optimizer import LinearRationOptimizer
from RUFAS.biophysical.animal.data_types.animal_combination import AnimalCombination
from RUFAS.biophysical.animal.data_types.animal_types import AnimalType
from RUFAS.biophysical.animal.data_types.nutrients import NutrientsInputs
from RUFAS.biophysical.animal.data_types.nutrition_data_structures import NutritionRequirements
from RUFAS.biophysical.animal.ration.amino_acid import EssentialAminoAcidRequirements
from RUFAS.biophysical.animal.nutrients.nasem_requirements_calculator import NASEMRequirementsCalculator
from RUFAS.biophysical.animal.nutrients.nutrients import Nutrients
from RUFAS.data_structures.feed_storage_to_animal_connection import (
    AvailableFeedsBuilder,
    Feed,
    NutrientStandard,
)
from RUFAS.data_structures import feed_storage_to_animal_connection as feed_module
from RUFAS.biophysical.animal.ration.ration_optimizer import RationOptimizer

app = Flask(__name__)
FEED_CONFIG_PATH = RUFAS_DIR / "input" / "data" / "feed" / "example_Midwest_feed.json"
FEED_LIBRARY_PATH = RUFAS_DIR / "input" / "data" / "feed" / "NASEM_Comp_with_TDN.csv"

DEFAULTS: dict[str, float] = {
    "body_weight": 650.0,
    "maintenance_energy": 11.0,
    "growth_energy": 0.0,
    "pregnancy_energy": 1.5,
    "lactation_energy": 22.0,
    "metabolizable_protein": 2300.0,
    "calcium": 110.0,
    "phosphorus": 50.0,
    "process_based_phosphorus": 40.0,
    "dry_matter": 24.0,
    "activity_energy": 1.0,
}

COW_DEFAULTS: dict[str, float] = {
    "cow_body_weight": 650.0,
    "mature_body_weight": 740.0,
    "day_of_pregnancy": 0.0,
    "body_condition_score": 3.0,
    "days_in_milk": 100.0,
    "average_daily_gain": 0.0,
    "parity": 2.0,
    "calving_interval": 400.0,
    "milk_fat": 4.0,
    "milk_true_protein": 3.2,
    "milk_lactose": 4.8,
    "milk_production": 35.0,
    "walking_distance": 10.0,
    "ndf_percentage": 35.0,
}

# Same grouping as RuFaS's animal_grouping_scenarios: category -> (label, pen combination, lactating).
CATEGORIES: dict[str, tuple[str, AnimalCombination, bool]] = {
    "lactacao": ("Vaca em lactação", AnimalCombination.LAC_COW, True),
    "seca": ("Vaca seca", AnimalCombination.CLOSE_UP, False),
    "novilha": ("Novilha em crescimento", AnimalCombination.GROWING, False),
}

# The only housing values RuFaS's requirement calculators recognise; they change activity energy only.
HOUSING = {"Barn": "Confinamento", "Grazing": "Pasto"}

PEN_DEFAULTS: dict[str, float] = {
    "enteric_methane": 400.0,
    "urine_nitrogen": 0.2,
    "milk_price": 0.45,  # same currency as the feed costs, per kg of milk
}

CONSTRAINT_LABELS = {
    "NE_total_constraint": "Energia líquida total (NRC)",
    "NE_maintenance_and_activity_constraint": "Energia de manutenção e atividade (NRC)",
    "NE_lactation_constraint": "Energia de lactação (NRC)",
    "NE_growth_constraint": "Energia de crescimento (NRC)",
    "NASEM_net_energy_constraint": "Energia líquida (NASEM)",
    "calcium_constraint": "Cálcio",
    "phosphorus_constraint": "Fósforo",
    "protein_constraint_lower": "Proteína metabolizável (mínimo)",
    "protein_constraint_upper": "Proteína metabolizável (máximo)",
    "NDF_constraint_lower": "FDN (mínimo)",
    "NDF_constraint_upper": "FDN (máximo)",
    "forage_NDF_constraint": "FDN de forragem (mínimo)",
    "fat_constraint": "Gordura (máximo)",
    "DMI_constraint_upper": "Matéria seca (máximo)",
    "DMI_constraint_lower": "Matéria seca (mínimo)",
}

# Fields of the "requirements" panel: (form key, label, unit).
REQUIREMENT_FIELDS: list[tuple[str, str, str]] = [
    ("body_weight", "Peso corporal usado pelo otimizador", "kg"),
    ("maintenance_energy", "Energia de manutenção", "Mcal/dia"),
    ("growth_energy", "Energia de crescimento", "Mcal/dia"),
    ("pregnancy_energy", "Energia de gestação", "Mcal/dia"),
    ("lactation_energy", "Energia de lactação", "Mcal/dia"),
    ("metabolizable_protein", "Proteína metabolizável", "g/dia"),
    ("calcium", "Cálcio", "g/dia"),
    ("phosphorus", "Fósforo", "g/dia"),
    ("process_based_phosphorus", "Fósforo baseado em processo", "g/dia"),
    ("dry_matter", "Matéria seca (DMI)", "kg/dia"),
    ("activity_energy", "Energia de atividade", "Mcal/dia"),
    ("enteric_methane", "Metano entérico médio do lote", "g/dia"),
    ("urine_nitrogen", "Nitrogênio urinário médio do lote", "kg/dia"),
    ("milk_price", "Preço do leite", "por kg, na moeda dos alimentos"),
]

# Extra inputs of the classic NRC model (PuLP), defaults in nrc_lp.NRC_DEFAULTS: (form key, label, unit).
NRC_FIELDS: list[tuple[str, str, str]] = [
    ("dmi_tolerance", "Tolerância da matéria seca", "% do DMI, 0 = igual ao DMI"),
    ("ndf_min", "FDN mínimo", "% MS"),
    ("ndf_max", "FDN máximo", "% MS"),
    ("forage_ndf_min", "FDN de forragem mínimo", "% MS"),
    ("fat_max", "Gordura (EE) máxima", "% MS"),
    *((key, label, "% MS") for key, label in nrc_lp.MACRO_MINERALS.items()),
    *((key, label, "mg/kg MS") for key, label in nrc_lp.TRACE_MINERALS.items()),
    *((key, label, "UI por kg de peso vivo") for key, label in nrc_lp.VITAMINS.items()),
]

# Library column that supplies each NRC row, to suggest feeds when the model is infeasible.
NRC_SOURCE_COLUMNS = {
    "Energia líquida de lactação": "TDN",
    "Cálcio absorvível": "calcium",
    "Fósforo absorvível": "phosphorus",
    **{label: column for group in (nrc_lp.MACRO_MINERALS, nrc_lp.TRACE_MINERALS, nrc_lp.VITAMINS)
       for column, label in group.items()},
}

# Amounts below this (kg DM) count as "not in the ration".
NEGLIGIBLE = 1e-3
# A constraint is "at the limit" when its slack is below this fraction of its scale.
BINDING_TOLERANCE = 5e-4

# The optimizers patch scipy's ``minimize`` and the page changes the process
# cwd, both process-wide, so Flask's request threads must take turns.
# ponytail: one global lock, a process pool if several users run at once.
_SOLVER_LOCK = threading.Lock()


@contextmanager
def _rufas_working_directory() -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(RUFAS_DIR)
    try:
        yield
    finally:
        os.chdir(previous)


def _feed_config() -> tuple[dict[str, Any], set[int], dict[str, list[object]]]:
    configured = json.loads(FEED_CONFIG_PATH.read_text(encoding="utf-8"))
    configured_by_id = {int(item["feed_type"]): item for item in configured["feeds"]}
    with FEED_LIBRARY_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    def parse(value: str) -> object:
        if value in ("TRUE", "FALSE"):
            return value == "TRUE"
        try:
            return float(value)
        except ValueError:
            return value

    library = {key: [parse(row[key]) for row in rows] for key in rows[0]}
    library["rufas_id"] = [int(value) for value in library["rufas_id"]]
    feeds = []
    for feed_id in library["rufas_id"]:
        original = configured_by_id.get(feed_id, {})
        feeds.append(
            {
                "feed_type": feed_id,
                "purchased_feed_cost": original.get("purchased_feed_cost", 0.1),
                "buffer": original.get("buffer", 0.15),
                "runtime_purchase_allowance": original.get("runtime_purchase_allowance", 1000.0),
                "advance_purchase_allowance": original.get("advance_purchase_allowance", 1000000.0),
                "planning_cycle_allowance": original.get("planning_cycle_allowance", 1000.0),
            }
        )
    return {"feeds": feeds, "rations": []}, set(configured_by_id), library


def load_feeds() -> list[Feed]:
    """Load the complete NASEM library, with the farm feeds selected by default."""
    config, _, library = _feed_config()
    input_manager = MagicMock(get_data=lambda _: library)
    with _rufas_working_directory():
        with patch.object(feed_module, "InputManager", return_value=input_manager):
            return AvailableFeedsBuilder.setup_available_feeds(config, NutrientStandard.NASEM)


FEEDS = load_feeds()
_, DEFAULT_SELECTED_IDS, _library = _feed_config()
FEED_NAMES: dict[int, str] = dict(zip(_library["rufas_id"], map(str, _library["Name"])))
LIBRARY_ROWS: dict[int, dict[str, object]] = {
    feed_id: {column: values[index] for column, values in _library.items()}
    for index, feed_id in enumerate(_library["rufas_id"])
}


def _float(form: Mapping[str, str], key: str) -> float:
    value = float(form[key])
    if not math.isfinite(value):
        raise ValueError(f"{key} deve ser finito")
    return value


def _requirements(form: Mapping[str, str]) -> NutritionRequirements:
    values = {key: _float(form, key) for key in DEFAULTS if key != "body_weight"}
    if values["dry_matter"] <= 0 or _float(form, "body_weight") <= 0:
        raise ValueError("peso corporal e matéria seca devem ser positivos")
    amino_acids = EssentialAminoAcidRequirements(*([0.0] * 9))
    return NutritionRequirements(essential_amino_acids=amino_acids, **values)


def _selected_ids(form: Mapping[str, str]) -> set[int]:
    if hasattr(form, "getlist"):
        raw_values = form.getlist("selected_feeds")
    else:
        raw_values = str(form.get("selected_feeds", "")).split(",")
    return {int(value) for raw in raw_values for value in str(raw).split(",") if value}


def _category(form: Mapping[str, str]) -> tuple[str, AnimalCombination, bool]:
    category = form.get("category", "lactacao")
    if category not in CATEGORIES:
        raise ValueError("categoria animal desconhecida")
    return CATEGORIES[category]


def _calculate_nasem_requirements(form: Mapping[str, str]) -> NutritionRequirements:
    values = {key: _float(form, key) for key in COW_DEFAULTS}
    if values["day_of_pregnancy"] <= 0:
        day_of_pregnancy = None
    else:
        day_of_pregnancy = int(values["day_of_pregnancy"])
    _, combination, lactating = _category(form)
    if combination is AnimalCombination.LAC_COW:
        animal_type = AnimalType.LAC_COW
    elif combination is AnimalCombination.CLOSE_UP:
        animal_type = AnimalType.DRY_COW
    else:
        animal_type = AnimalType.HEIFER_II if day_of_pregnancy else AnimalType.HEIFER_I
    housing = form.get("housing", "Barn")
    if housing not in HOUSING:
        raise ValueError("alojamento desconhecido")
    milk_production = values["milk_production"] if lactating else 0.0
    requirements = NASEMRequirementsCalculator.calculate_requirements(
        body_weight=values["cow_body_weight"],
        mature_body_weight=values["mature_body_weight"],
        day_of_pregnancy=day_of_pregnancy,
        body_condition_score_5=values["body_condition_score"],
        days_in_milk=int(values["days_in_milk"]),
        average_daily_gain_heifer=values["average_daily_gain"],
        animal_type=animal_type,
        parity=int(values["parity"]),
        calving_interval=int(values["calving_interval"]),
        milk_fat=values["milk_fat"],
        milk_true_protein=values["milk_true_protein"],
        milk_lactose=values["milk_lactose"],
        milk_production=milk_production,
        housing=housing,
        distance=values["walking_distance"],
        lactating=lactating,
        ndf_percentage=values["ndf_percentage"],
        process_based_phosphorus_requirement=0.0,
    )
    # Process-based P comes from RuFaS's phosphorus module, as in a simulation day. RuFaS never updates
    # Nutrients.ration_phosphorus_concentration (it stays 0), so neither does this.
    nutrients = Nutrients()
    nutrients.set_dry_matter_intake(requirements.dry_matter)
    nutrients.perform_daily_phosphorus_update(
        NutrientsInputs(
            animal_type=animal_type,
            body_weight=values["cow_body_weight"],
            mature_body_weight=values["mature_body_weight"],
            daily_growth=values["average_daily_gain"],
            days_in_pregnancy=day_of_pregnancy or 0,
            days_in_milk=int(values["days_in_milk"]) if lactating else 0,
            daily_milk_produced=milk_production,
        )
    )
    return dataclasses.replace(requirements, process_based_phosphorus=nutrients.phosphorus_requirement)


def _configured_feeds(form: Mapping[str, str]) -> list[Feed]:
    selected_ids = _selected_ids(form)
    if not selected_ids:
        raise ValueError("selecione pelo menos um alimento")
    feeds = [copy.deepcopy(feed) for feed in FEEDS if feed.rufas_id in selected_ids]
    for feed in feeds:
        feed.purchase_cost = _float(form, f"cost_{feed.rufas_id}")
        feed.lower_limit = _float(form, f"min_{feed.rufas_id}")
        feed.limit = _float(form, f"max_{feed.rufas_id}")
        if feed.purchase_cost < 0 or feed.lower_limit < 0 or feed.limit < feed.lower_limit:
            raise ValueError(f"limites ou custo inválidos para o alimento {feed.rufas_id}")
    return feeds


def _default_form() -> dict[str, str]:
    values = {key: str(value) for key, value in DEFAULTS.items()}
    values.update({key: str(value) for key, value in COW_DEFAULTS.items()})
    values.update({key: str(value) for key, value in PEN_DEFAULTS.items()})
    values.update({key: str(value) for key, value in nrc_lp.NRC_DEFAULTS.items()})
    values.update(category="lactacao", housing="Barn", optimizer="linear")
    for feed in FEEDS:
        values[f"cost_{feed.rufas_id}"] = str(feed.purchase_cost)
        values[f"min_{feed.rufas_id}"] = str(feed.lower_limit)
        values[f"max_{feed.rufas_id}"] = str(feed.limit)
    values["selected_feeds"] = ",".join(str(feed_id) for feed_id in sorted(DEFAULT_SELECTED_IDS))
    return values


def _constraint_scale(constraint: Mapping[str, Any], size: int, ration_config: Any) -> float:
    """Size of a constraint, for relative tolerances: for "supply - requirement" it is |g(0)| = the requirement."""
    try:
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore")
            value = abs(float(constraint["fun"](np.zeros(size), ration_config)))
    except (ArithmeticError, ValueError):
        return 1.0
    return max(value, 1.0) if math.isfinite(value) else 1.0


def simulate(form: Mapping[str, str]) -> dict[str, Any]:
    feeds = _configured_feeds(form)
    requirements = _requirements(form)
    optimizer_name = form.get("optimizer", "linear")
    optimizer_types = {
        "linear": ("Programação linear sequencial (SLP)", LinearRationOptimizer),
        "rufas": ("Otimizador original do RuFaS (SLSQP)", RationOptimizer),
        "pulp": ("Modelo NRC clássico (PuLP + HiGHS)", None),
    }
    if optimizer_name not in optimizer_types:
        raise ValueError("otimizador desconhecido")
    optimizer_label, optimizer_type = optimizer_types[optimizer_name]
    category_label, combination, _ = _category(form)
    enteric_methane = _float(form, "enteric_methane")
    urine_nitrogen = _float(form, "urine_nitrogen")
    if enteric_methane < 0 or urine_nitrogen < 0:
        raise ValueError("metano e nitrogênio urinário não podem ser negativos")
    milk_price = _float(form, "milk_price")
    milk_production = _float(form, "milk_production") if _category(form)[2] else 0.0
    if milk_price < 0 or milk_production < 0:
        raise ValueError("preço e produção de leite não podem ser negativos")
    if optimizer_type is None:
        return _simulate_nrc(form, feeds, requirements, optimizer_name, optimizer_label, category_label,
                             milk_production * milk_price)
    optimizer = optimizer_type()
    with _SOLVER_LOCK, _rufas_working_directory():
        solution, ration_config = optimizer.attempt_optimization(
            nutrient_standard=NutrientStandard.NASEM,
            pen_average_body_weight=_float(form, "body_weight"),
            pen_average_enteric_methane=enteric_methane,
            pen_average_urine_nitrogen=urine_nitrogen,
            requirements=requirements,
            initial_dry_matter_requirement=requirements.dry_matter,
            initial_protein_requirement=requirements.metabolizable_protein,
            pen_available_feeds=feeds,
            animal_combination=combination,
        )

    constraints = optimizer._select_constraints(combination)
    constraint_rows = [
        {
            "name": CONSTRAINT_LABELS.get(constraint["fun"].__name__, constraint["fun"].__name__),
            "slack": float(constraint["fun"](solution.x, ration_config)),
            "scale": _constraint_scale(constraint, len(solution.x), ration_config),
        }
        for constraint in constraints
    ]
    return {
        "solution": solution,
        "optimizer": optimizer_name,
        "optimizer_label": optimizer_label,
        "category_label": category_label,
        "feeds": feeds,
        "ration": [
            {
                "id": feed.rufas_id,
                "name": FEED_NAMES.get(feed.rufas_id, f"Feed {feed.rufas_id}"),
                "amount": float(amount),
                "cost": float(amount * feed.purchase_cost),
            }
            for feed, amount in zip(feeds, solution.x)
            if amount > 1e-7
        ],
        "constraints": constraint_rows,
        # Income over feed cost per cow per day: milk revenue minus diet cost.
        "milk_revenue": milk_production * milk_price,
        "iofc": milk_production * milk_price - float(solution.fun),
        "requirements": requirements,
    }


def _simulate_nrc(
    form: Mapping[str, str],
    feeds: list[Feed],
    requirements: NutritionRequirements,
    optimizer_name: str,
    optimizer_label: str,
    category_label: str,
    milk_revenue: float,
) -> dict[str, Any]:
    """The same scenario solved by the classic NRC linear program (addon_rufas.nrc_lp)."""
    rows = [
        {**LIBRARY_ROWS[feed.rufas_id], "cost": feed.purchase_cost, "min": feed.lower_limit, "max": feed.limit}
        for feed in feeds
    ]
    extra = {key: _float(form, key) for key, _, _ in NRC_FIELDS}
    if extra["ndf_min"] > extra["ndf_max"] or extra["dmi_tolerance"] < 0:
        raise ValueError("FDN mínimo maior que o máximo, ou tolerância de MS negativa")
    nrc = nrc_lp.solve(
        rows,
        {
            **extra,
            "energy": requirements.maintenance_energy
            + requirements.growth_energy
            + requirements.pregnancy_energy
            + requirements.lactation_energy
            + requirements.activity_energy,
            "mp": requirements.metabolizable_protein,
            "calcium": requirements.calcium,
            "phosphorus": max(requirements.phosphorus, requirements.process_based_phosphorus),
            "dmi": requirements.dry_matter,
            "body_weight": _float(form, "body_weight"),
        },
    )
    selected = {feed.rufas_id for feed in feeds}
    for name in nrc.missing:
        column = NRC_SOURCE_COLUMNS.get(name)
        if column:
            best = sorted(
                (i for i in LIBRARY_ROWS if i not in selected and isinstance(LIBRARY_ROWS[i][column], float)),
                key=lambda i: -LIBRARY_ROWS[i][column],
            )[:2]
            if best and LIBRARY_ROWS[best[0]][column] > 0:
                sources = ", ".join(f"{FEED_NAMES[i]} ({i})" for i in best)
                nrc.warnings.append(f"Fontes na biblioteca para {name}, ainda não marcadas: {sources}.")
    return {
        "solution": SimpleNamespace(success=nrc.success, fun=nrc.cost, nit="—", message=nrc.message, x=nrc.x),
        "optimizer": optimizer_name,
        "optimizer_label": optimizer_label,
        "category_label": category_label,
        "feeds": feeds,
        "ration": [
            {
                "id": feed.rufas_id,
                "name": FEED_NAMES.get(feed.rufas_id, f"Feed {feed.rufas_id}"),
                "amount": amount,
                "cost": amount * feed.purchase_cost,
            }
            for feed, amount in zip(feeds, nrc.x)
            if amount > 1e-7
        ],
        "constraints": nrc.constraints,
        "warnings": nrc.warnings,
        "supply": nrc.supply,
        "milk_revenue": milk_revenue,
        "iofc": milk_revenue - nrc.cost,
        "requirements": requirements,
    }


def _sensitivity_options(form: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """What the sensitivity analysis can vary: every requirement field and the price of each selected feed."""
    options = {key: (label, unit) for key, label, unit in [*REQUIREMENT_FIELDS, *NRC_FIELDS]}
    for feed_id in sorted(_selected_ids(form)):
        options[f"cost_{feed_id}"] = (f"Preço de {FEED_NAMES.get(feed_id, feed_id)}", "por kg")
    return options


def sensitivity(form: Mapping[str, str]) -> dict[str, Any]:
    """Solves the scenario, changes one input by a percentage, solves again and explains what changed."""
    options = _sensitivity_options(form)
    key = form.get("sens_param", "")
    if key not in options:
        raise ValueError("escolha o item a variar")
    label, unit = options[key]
    percent = _float(form, "sens_percent")
    old_value = _float(form, key)
    new_value = old_value * (1 + percent / 100)
    changed = MultiDict(form)
    changed[key] = str(new_value)
    before, after = simulate(form), simulate(changed)

    amounts_before = {item["id"]: item["amount"] for item in before["ration"]}
    amounts_after = {item["id"]: item["amount"] for item in after["ration"]}
    rows = [
        {
            "id": feed_id,
            "name": FEED_NAMES.get(feed_id, f"Feed {feed_id}"),
            "before": amounts_before.get(feed_id, 0.0),
            "after": amounts_after.get(feed_id, 0.0),
            "delta": amounts_after.get(feed_id, 0.0) - amounts_before.get(feed_id, 0.0),
        }
        for feed_id in sorted(set(amounts_before) | set(amounts_after))
    ]
    rows.sort(key=lambda row: -abs(row["delta"]))
    cost_before, cost_after = float(before["solution"].fun), float(after["solution"].fun)
    cost_delta = cost_after - cost_before
    binding = [
        row["name"] for row in after["constraints"] if abs(row["slack"]) <= BINDING_TOLERANCE * row["scale"]
    ]

    conclusions = [f"{label}: {old_value:.4g} → {new_value:.4g} {unit} ({percent:+.4g}%)."]
    if not (before["solution"].success and after["solution"].success):
        which = "a original" if not before["solution"].success else "a nova"
        conclusions.append(f"A comparação não é válida: {which} formulação ficou inviável.")
    else:
        relative = f" ({100 * cost_delta / cost_before:+.2f}%)" if cost_before else ""
        conclusions.append(
            f"Custo da dieta: {cost_before:.4f} → {cost_after:.4f} por vaca/dia, {cost_delta:+.4f}{relative}."
        )
        if new_value != old_value and abs(cost_delta) >= 1e-6:
            conclusions.append(
                f"Custo marginal: {cost_delta / (new_value - old_value):+.4g} de custo por unidade a mais de "
                f"{label.lower()} ({unit})."
            )
        conclusions.append(
            f"IOFC: {before['iofc']:.4f} → {after['iofc']:.4f}, {after['iofc'] - before['iofc']:+.4f} por vaca/dia."
        )
        moved = [row for row in rows if abs(row["delta"]) >= NEGLIGIBLE]
        if not moved:
            conclusions.append("A ração não mudou: nessa faixa, o item não altera a decisão.")
        for verb, chosen in (
            ("Entraram na ração", [r for r in moved if r["before"] < NEGLIGIBLE]),
            ("Saíram da ração", [r for r in moved if r["after"] < NEGLIGIBLE]),
            ("Aumentaram", [r for r in moved if r["delta"] > 0 and r["before"] >= NEGLIGIBLE]),
            ("Diminuíram", [r for r in moved if r["delta"] < 0 and r["after"] >= NEGLIGIBLE]),
        ):
            if chosen:
                listed = "; ".join(f"{r['name']} ({r['delta']:+.3f} kg MS)" for r in chosen)
                conclusions.append(f"{verb}: {listed}.")
        if binding:
            conclusions.append(
                "Restrições no limite na nova solução (são elas que definem o custo): " + ", ".join(binding) + "."
            )
    return {"label": label, "rows": rows, "conclusions": conclusions, "before": before, "after": after}


def _scenario(form: Mapping[str, str]) -> dict[str, Any]:
    """The page state as a JSON-ready dict, with the same keys the form uses."""
    data: dict[str, Any] = {key: form.get(key, value) for key, value in _default_form().items()}
    data["selected_feeds"] = sorted(_selected_ids(form))
    return data


def _imported_form(upload: Any) -> MultiDict:
    """Default page state overridden by an uploaded scenario JSON (any subset of the exported keys)."""
    if upload is None or not upload.filename:
        raise ValueError("escolha um arquivo JSON")
    data = json.load(upload.stream)
    if not isinstance(data, dict):
        raise ValueError("o JSON deve ser um objeto com os campos da página")
    # Accept both the plain form export and the metadata envelope used by
    # newer scenario exporters.
    if isinstance(data.get("data"), dict):
        data = data["data"]
    defaults = _default_form()
    unknown = sorted(set(data) - set(defaults))
    if unknown:
        raise ValueError(f"campos desconhecidos no JSON: {', '.join(unknown[:5])}")
    form = MultiDict({key: value for key, value in defaults.items() if key != "selected_feeds"})
    for key, value in data.items():
        if key != "selected_feeds":
            form[key] = str(value)
    selected = data.get("selected_feeds", sorted(DEFAULT_SELECTED_IDS))
    if not isinstance(selected, list):
        raise ValueError("selected_feeds deve ser uma lista de IDs")
    form.setlist("selected_feeds", [str(int(feed_id)) for feed_id in selected])
    return form


ERROR_PREFIX = {
    "calculate_requirements": "Não foi possível calcular as exigências NASEM",
    "import": "Não foi possível importar o cenário",
    "sensitivity": "Não foi possível fazer a análise de sensibilidade",
}


@app.route("/", methods=["GET", "POST"])
def index():
    form: Mapping[str, str] = _default_form() if request.method == "GET" else request.form.copy()
    action = request.form.get("action") if request.method == "POST" else None
    if action == "export":
        return Response(
            json.dumps(_scenario(form), ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=cenario.json"},
        )
    result: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    error = None
    try:
        if action == "import":
            form = _imported_form(request.files.get("scenario"))
        elif action == "calculate_requirements":
            calculated = _calculate_nasem_requirements(form)
            for key in DEFAULTS:
                if key != "body_weight":
                    form[key] = str(getattr(calculated, key))
            form["body_weight"] = form["cow_body_weight"]
        elif action == "sensitivity":
            analysis = sensitivity(form)
            result = analysis["after"]
        elif request.method == "POST":
            result = simulate(form)
    except (KeyError, TypeError, ValueError) as exc:
        error = f"{ERROR_PREFIX.get(action, 'Entrada inválida')}: {exc}"
    return render_template(
        "index.html",
        form=form,
        feeds=FEEDS,
        feed_names=FEED_NAMES,
        categories=CATEGORIES,
        housing_options=HOUSING,
        selected_ids=_selected_ids(form),
        optimizer=form.get("optimizer", "linear"),
        result=result,
        analysis=analysis,
        requirement_fields=REQUIREMENT_FIELDS,
        nrc_fields=NRC_FIELDS,
        sensitivity_options=_sensitivity_options(form),
        error=error,
    )


@app.get("/sobre")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
