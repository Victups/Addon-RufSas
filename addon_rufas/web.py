"""Local browser interface for exercising the add-on optimizer.

The page calls ``LinearRationOptimizer.attempt_optimization`` directly. It
does not modify the RuFaS checkout or replace the normal RuFaS runner.
"""

from __future__ import annotations

import json
import math
import os
import sys
from contextlib import contextmanager
import csv
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Any, Iterator, Mapping

from flask import Flask, render_template, request

ROOT = Path(__file__).resolve().parents[1]
RUFAS_DIR = ROOT / "RufSas" / "RuFaS"
if str(RUFAS_DIR) not in sys.path:
    sys.path.insert(0, str(RUFAS_DIR))

from addon_rufas.linear_ration_optimizer import LinearRationOptimizer
from RUFAS.biophysical.animal.data_types.animal_combination import AnimalCombination
from RUFAS.biophysical.animal.data_types.animal_types import AnimalType
from RUFAS.biophysical.animal.data_types.nutrition_data_structures import NutritionRequirements
from RUFAS.biophysical.animal.ration.amino_acid import EssentialAminoAcidRequirements
from RUFAS.biophysical.animal.nutrients.nasem_requirements_calculator import NASEMRequirementsCalculator
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
USER_FEEDS_PATH = RUFAS_DIR / "input" / "data" / "feed" / "user_feeds.csv"

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
_, DEFAULT_SELECTED_IDS, _ = _feed_config()


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


def _calculate_nasem_requirements(form: Mapping[str, str]) -> NutritionRequirements:
    values = {key: _float(form, key) for key in COW_DEFAULTS}
    if values["day_of_pregnancy"] <= 0:
        day_of_pregnancy = None
    else:
        day_of_pregnancy = int(values["day_of_pregnancy"])
    return NASEMRequirementsCalculator.calculate_requirements(
        body_weight=values["cow_body_weight"],
        mature_body_weight=values["mature_body_weight"],
        day_of_pregnancy=day_of_pregnancy,
        body_condition_score_5=values["body_condition_score"],
        days_in_milk=int(values["days_in_milk"]),
        average_daily_gain_heifer=values["average_daily_gain"],
        animal_type=AnimalType.LAC_COW,
        parity=int(values["parity"]),
        calving_interval=int(values["calving_interval"]),
        milk_fat=values["milk_fat"],
        milk_true_protein=values["milk_true_protein"],
        milk_lactose=values["milk_lactose"],
        milk_production=values["milk_production"],
        housing="Barn",
        distance=values["walking_distance"],
        lactating=True,
        ndf_percentage=values["ndf_percentage"],
        process_based_phosphorus_requirement=_float(form, "process_based_phosphorus"),
    )


def _configured_feeds(form: Mapping[str, str]) -> list[Feed]:
    selected_ids = _selected_ids(form) or DEFAULT_SELECTED_IDS
    if not selected_ids:
        raise ValueError("selecione pelo menos um alimento")
    feeds = [feed for feed in load_feeds() if feed.rufas_id in selected_ids]
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
    optimizer = optimizer_type()
    with _rufas_working_directory():
        solution, ration_config = optimizer.attempt_optimization(
            nutrient_standard=NutrientStandard.NASEM,
            pen_average_body_weight=_float(form, "body_weight"),
            pen_average_enteric_methane=400.0,
            pen_average_urine_nitrogen=0.2,
            requirements=requirements,
            initial_dry_matter_requirement=requirements.dry_matter,
            initial_protein_requirement=requirements.metabolizable_protein,
            pen_available_feeds=feeds,
            animal_combination=AnimalCombination.LAC_COW,
        )

    constraints = optimizer._select_constraints(AnimalCombination.LAC_COW)
    constraint_rows = [
        {
            "name": constraint.get("name", f"Restrição {index + 1}"),
            "slack": float(constraint["fun"](solution.x, ration_config)),
        }
        for index, constraint in enumerate(constraints)
    ]
    return {
        "solution": solution,
        "optimizer": optimizer_name,
        "optimizer_label": optimizer_label,
        "feeds": feeds,
        "ration": [
            {
                "id": feed.rufas_id,
                "name": getattr(feed, "name", f"Feed {feed.rufas_id}"),
                "amount": float(amount),
                "cost": float(amount * feed.purchase_cost),
            }
            for feed, amount in zip(feeds, solution.x)
            if amount > 1e-7
        ],
        "constraints": constraint_rows,
        "requirements": requirements,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    form: Mapping[str, str] = _default_form() if request.method == "GET" else request.form
    if request.method == "POST" and request.form.get("action") == "calculate_requirements":
        mutable_form = dict(request.form)
        try:
            calculated = _calculate_nasem_requirements(request.form)
            for key in DEFAULTS:
                if key != "body_weight":
                    mutable_form[key] = str(getattr(calculated, key))
            mutable_form["body_weight"] = request.form["cow_body_weight"]
            form = mutable_form
        except (KeyError, TypeError, ValueError) as exc:
            error = f"Não foi possível calcular as exigências NASEM: {exc}"
        else:
            error = None
    else:
        error = None
    selected_ids = (
        DEFAULT_SELECTED_IDS
        if request.method == "GET"
        else _selected_ids(form)
    )
    optimizer = form.get("optimizer", "linear")
    result: dict[str, Any] | None = None
    if request.method == "POST":
        if request.form.get("action") != "calculate_requirements":
            try:
                result = simulate(form)
            except (KeyError, TypeError, ValueError) as exc:
                error = f"Entrada inválida: {exc}"
    return render_template(
        "index.html", form=form, feeds=FEEDS, selected_ids=selected_ids, optimizer=optimizer, result=result, error=error
    )


@app.get("/sobre")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
