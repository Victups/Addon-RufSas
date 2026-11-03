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
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Any, Iterator, Mapping

from flask import Flask, Response, render_template, request
from werkzeug.datastructures import MultiDict

ROOT = Path(__file__).resolve().parents[1]
RUFAS_DIR = ROOT / "RufSas" / "RuFaS"
if str(RUFAS_DIR) not in sys.path:
    sys.path.insert(0, str(RUFAS_DIR))

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
    values.update(category="lactacao", housing="Barn", optimizer="linear")
    for feed in FEEDS:
        values[f"cost_{feed.rufas_id}"] = str(feed.purchase_cost)
        values[f"min_{feed.rufas_id}"] = str(feed.lower_limit)
        values[f"max_{feed.rufas_id}"] = str(feed.limit)
    values["selected_feeds"] = ",".join(str(feed_id) for feed_id in sorted(DEFAULT_SELECTED_IDS))
    return values


def simulate(form: Mapping[str, str]) -> dict[str, Any]:
    feeds = _configured_feeds(form)
    requirements = _requirements(form)
    optimizer_name = form.get("optimizer", "linear")
    optimizer_types = {
        "linear": ("Programação linear sequencial (SLP)", LinearRationOptimizer),
        "rufas": ("Otimizador original do RuFaS (SLSQP)", RationOptimizer),
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
        error=error,
    )


@app.get("/sobre")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
