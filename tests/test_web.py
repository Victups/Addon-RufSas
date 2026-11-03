import html
import io
import json
import re

import pytest

pytest.importorskip("flask")
from addon_rufas import web  # noqa: E402

client = web.app.test_client()


def post(**over):
    data = web._default_form()
    data.update(over)
    return client.post("/", data=data).get_data(as_text=True)


def test_pages_open():
    assert client.get("/").status_code == 200
    assert client.get("/sobre").status_code == 200


@pytest.mark.parametrize("optimizer", ["linear", "rufas"])
def test_formulation_is_feasible_with_named_constraints(optimizer):
    html = post(optimizer=optimizer)
    assert "<h2>Viável</h2>" in html
    assert "<td>Cálcio</td>" in html and "Restrição 1" not in html


def test_no_feed_selected_is_an_error():
    assert "selecione pelo menos um alimento" in post(selected_feeds="")


def test_calculating_requirements_keeps_every_selected_feed():
    data = web._default_form()
    data["action"] = "calculate_requirements"
    data["selected_feeds"] = [str(i) for i in sorted(web.DEFAULT_SELECTED_IDS)]
    html = client.post("/", data=data).get_data(as_text=True)
    checked = re.findall(r'name="selected_feeds" value="\d+" checked', html)
    assert len(checked) == len(web.DEFAULT_SELECTED_IDS)


@pytest.mark.parametrize("category", ["seca", "novilha"])
def test_other_categories_compute_requirements_and_formulate(category):
    data = web._default_form()
    data.update(category=category, action="calculate_requirements", cow_body_weight="450", average_daily_gain="0.8")
    html = client.post("/", data=data).get_data(as_text=True)
    assert "Não foi possível" not in html
    energy = float(re.search(r'name="lactation_energy" value="([^"]+)"', html).group(1))
    assert energy == 0.0
    assert "<h2>" in post(category=category)


def test_heifer_is_feasible_for_both_optimizers():
    # The SLP used to stop at iteration 1 here: its first linearization is infeasible (phase-1 step fixes it).
    data = web._default_form()
    data.update(category="novilha", action="calculate_requirements", cow_body_weight="400", average_daily_gain="0.8")
    html = client.post("/", data=data).get_data(as_text=True)
    requirements = {key: re.search(rf'name="{key}" value="([^"]+)"', html).group(1) for key in web.DEFAULTS}
    for optimizer in ("linear", "rufas"):
        assert "<h2>Viável</h2>" in post(category="novilha", optimizer=optimizer, **requirements)


def field(html, key):
    return float(re.search(rf'name="{key}" value="([^"]+)"', html).group(1))


def test_feed_names_are_shown():
    html = client.get("/").get_data(as_text=True)
    feed_id = min(web.DEFAULT_SELECTED_IDS)
    assert web.FEED_NAMES[feed_id] and f"<td>{web.FEED_NAMES[feed_id]}</td>" in html


def test_grazing_raises_activity_energy_and_process_phosphorus_is_calculated():
    barn = post(action="calculate_requirements", housing="Barn")
    grazing = post(action="calculate_requirements", housing="Grazing")
    assert field(grazing, "activity_energy") > field(barn, "activity_energy") + 1
    assert field(barn, "process_based_phosphorus") > 0
    assert field(barn, "process_based_phosphorus") != float(web.DEFAULTS["process_based_phosphorus"])
    assert "alojamento desconhecido" in post(action="calculate_requirements", housing="Tenda")


def test_scenario_export_then_import_round_trips():
    exported = client.post("/", data=web._default_form() | {"action": "export", "cost_44": "0.77", "category": "seca"})
    assert exported.mimetype == "application/json"
    scenario = exported.get_json()
    assert scenario["cost_44"] == "0.77" and scenario["selected_feeds"] == sorted(web.DEFAULT_SELECTED_IDS)
    scenario["selected_feeds"] = [44]
    upload = {"action": "import", "scenario": (io.BytesIO(json.dumps(scenario).encode()), "cenario.json")}
    html = client.post("/", data=upload, content_type="multipart/form-data").get_data(as_text=True)
    assert field(html, "cost_44") == 0.77
    assert re.findall(r'name="selected_feeds" value="(\d+)" checked', html) == ["44"]
    assert re.search(r'name="category" value="seca" checked', html)


@pytest.mark.parametrize("content", [b"not json", b"[1, 2]", b'{"typo_field": 1}'])
def test_bad_scenario_files_are_rejected(content):
    upload = {"action": "import", "scenario": (io.BytesIO(content), "x.json")}
    html = client.post("/", data=upload, content_type="multipart/form-data").get_data(as_text=True)
    assert "Não foi possível importar o cenário" in html


def test_iofc_is_milk_revenue_minus_diet_cost():
    html = post(milk_price="0.5", milk_production="30")
    cost = float(re.search(r"Custo / vaca / dia</span><strong>([-\d.]+)", html).group(1))
    iofc = float(re.search(r"IOFC / vaca / dia</span><strong>([-\d.]+)", html).group(1))
    assert iofc == pytest.approx(30 * 0.5 - cost, abs=1e-3)


def test_sensitivity_explains_the_new_decision():
    html_page = post(action="sensitivity", sens_param="metabolizable_protein", sens_percent="15")
    conclusions = [html.unescape(line) for line in re.findall(r"<li>(.*?)</li>", html_page)]
    assert any(line.startswith("Custo da dieta") and "+" in line for line in conclusions)
    assert any(line.startswith("Custo marginal") for line in conclusions)
    assert any("Proteína metabolizável (mínimo)" in line for line in conclusions if line.startswith("Restrições"))
    assert "Ração antes e depois" in html_page


def test_sensitivity_rejects_unknown_item():
    assert "escolha o item a variar" in post(action="sensitivity", sens_param="nada", sens_percent="10")
