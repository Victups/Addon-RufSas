import csv
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from addon_rufas.linear_ration_optimizer import LinearRationOptimizer
from RUFAS.biophysical.animal.data_types.animal_combination import AnimalCombination
from RUFAS.biophysical.animal.data_types.nutrition_data_structures import NutritionRequirements
from RUFAS.biophysical.animal.ration.amino_acid import EssentialAminoAcidRequirements
from RUFAS.biophysical.animal.ration.ration_optimizer import RationOptimizer
from RUFAS.data_structures import feed_storage_to_animal_connection as feed_module
from RUFAS.data_structures.feed_storage_to_animal_connection import AvailableFeedsBuilder, Feed, NutrientStandard

RUFAS_INPUT = Path(__file__).parents[1] / "RufSas" / "RuFaS" / "input" / "data" / "feed"
FEED_IDS = {23, 44, 50, 95, 104, 110, 301, 302}  # subset of example_Midwest_feed.json
NRC_FEED_IDS = {23, 44, 50, 95, 104, 110}  # the NRC library has no minerals 301/302


def _read_library(csv_path: Path) -> dict[str, list]:
    """Feed library as the dict-of-lists the InputManager would return."""

    def parse(value: str) -> object:
        if value in ("TRUE", "FALSE"):
            return value == "TRUE"
        try:
            return float(value)
        except ValueError:
            return value

    with open(csv_path, newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    library = {key: [parse(row[key]) for row in rows] for key in rows[0]}
    library["rufas_id"] = [int(value) for value in library["rufas_id"]]
    return library


@pytest.fixture(scope="module")
def feeds() -> list[Feed]:
    return load_feeds()


def load_feeds(standard: NutrientStandard = NutrientStandard.NASEM) -> list[Feed]:
    config = json.loads((RUFAS_INPUT / "example_Midwest_feed.json").read_text(encoding="utf-8"))
    ids = FEED_IDS if standard is NutrientStandard.NASEM else NRC_FEED_IDS
    feed_config = {"feeds": [feed for feed in config["feeds"] if feed["feed_type"] in ids], "rations": []}
    csv_name = "NASEM_Comp_with_TDN.csv" if standard is NutrientStandard.NASEM else "NRC_comp.csv"
    library = _read_library(RUFAS_INPUT / csv_name)
    with patch.object(feed_module, "InputManager", return_value=MagicMock(get_data=lambda _: library)):
        return AvailableFeedsBuilder.setup_available_feeds(feed_config, standard)


def _requirements(scale: float = 1.0) -> NutritionRequirements:
    """High-producing lactating cow (about 35 kg milk/day, 650 kg body weight). `scale` > 1 makes it harder."""
    amino_acids = EssentialAminoAcidRequirements(*[0.0] * 9)
    return NutritionRequirements(
        maintenance_energy=11.0,
        growth_energy=0.0,
        pregnancy_energy=1.5,
        lactation_energy=22.0 * scale,
        metabolizable_protein=2300.0 * scale,
        calcium=110.0,
        phosphorus=50.0,
        process_based_phosphorus=40.0,
        dry_matter=24.0,
        activity_energy=1.0,
        essential_amino_acids=amino_acids,
    )


def _formulate(optimizer: RationOptimizer, feeds: list[Feed], requirements: NutritionRequirements):
    standard = NutrientStandard.NASEM if "NASEM" in type(feeds[0]).__name__ else NutrientStandard.NRC
    nasem = standard is NutrientStandard.NASEM
    return optimizer.attempt_optimization(
        nutrient_standard=standard,
        pen_average_body_weight=650.0,
        pen_average_enteric_methane=400.0 if nasem else None,
        pen_average_urine_nitrogen=0.2 if nasem else None,
        requirements=requirements,
        initial_dry_matter_requirement=requirements.dry_matter,
        initial_protein_requirement=requirements.metabolizable_protein,
        pen_available_feeds=feeds,
        animal_combination=AnimalCombination.LAC_COW,
    )


def _failed_constraints(optimizer: RationOptimizer, solution, config) -> list:
    return RationOptimizer.find_failed_constraints(solution.x, optimizer._select_constraints(config.animal_combination), config)


def test_lp_ration_satisfies_every_constraint(feeds: list[Feed]) -> None:
    optimizer = LinearRationOptimizer()
    solution, config = _formulate(optimizer, feeds, _requirements())

    assert solution.success, solution.message
    assert _failed_constraints(optimizer, solution, config) == []
    assert np.all(solution.x >= -1e-6)


def test_lp_is_deterministic(feeds: list[Feed]) -> None:
    first, _ = _formulate(LinearRationOptimizer(), feeds, _requirements())
    second, _ = _formulate(LinearRationOptimizer(), feeds, _requirements())

    assert np.array_equal(first.x, second.x)


@pytest.mark.parametrize("standard", [NutrientStandard.NASEM, NutrientStandard.NRC])
@pytest.mark.parametrize("scale", [0.8, 1.0, 1.2])
def test_lp_costs_no_more_than_slsqp(standard: NutrientStandard, scale: float) -> None:
    feeds = load_feeds(standard)
    started = time.perf_counter()
    slsqp, _ = _formulate(RationOptimizer(), feeds, _requirements(scale))
    slsqp_seconds = time.perf_counter() - started
    started = time.perf_counter()
    lp, _ = _formulate(LinearRationOptimizer(), feeds, _requirements(scale))
    lp_seconds = time.perf_counter() - started
    print(f"\n{standard.name} x{scale}: SLSQP success={slsqp.success} cost={slsqp.fun:.4f} {slsqp_seconds:.2f}s | "
          f"LP success={lp.success} cost={lp.fun:.4f} nit={lp.nit} {lp_seconds:.2f}s")

    assert lp.success, lp.message
    if slsqp.success:
        assert lp.fun <= slsqp.fun * (1 + 1e-3)
    assert lp.nit < LinearRationOptimizer.MAX_ITERATIONS


def test_lp_reports_failure_when_requirements_are_impossible(feeds: list[Feed]) -> None:
    solution, _ = _formulate(LinearRationOptimizer(), feeds, _requirements(scale=50.0))

    assert not solution.success
