import html
from pathlib import Path
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
    # The first linear program is infeasible here; the simplex phase 1 finds a ration to restart from.
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


def test_importing_only_the_cow_keeps_the_prices_on_the_page():
    page = web._default_form() | {"cost_44": "1.2876", "milk_price": "2.7"}
    upload = {"action": "import", "scenario": (io.BytesIO(b'{"category": "seca", "cow_body_weight": 700}'), "vaca.json")}
    html = client.post("/", data=page | upload, content_type="multipart/form-data").get_data(as_text=True)
    assert field(html, "cow_body_weight") == 700 and re.search(r'name="category" value="seca" checked', html)
    assert field(html, "cost_44") == 1.2876 and field(html, "milk_price") == 2.7


@pytest.mark.parametrize("content", [b"not json", b"[1, 2]", b'{"typo_field": 1}'])
def test_bad_scenario_files_are_rejected(content):
    upload = {"action": "import", "scenario": (io.BytesIO(content), "x.json")}
    html = client.post("/", data=upload, content_type="multipart/form-data").get_data(as_text=True)
    assert "Não foi possível importar o cenário" in html


def test_iofc_is_milk_revenue_minus_diet_cost():
    html = post(milk_price="0.5", milk_production="30")
    cost = float(re.search(r"Custo / vaca / dia \(\$\)</span><strong>([-\d.]+)", html).group(1))
    iofc = float(re.search(r"IOFC / vaca / dia \(\$\)</span><strong>([-\d.]+)", html).group(1))
    assert iofc == pytest.approx(30 * 0.5 - cost, abs=1e-3)


def _spreadsheet_form():
    content = (Path(__file__).parents[1] / "scenarios" / "precos" / "planilha-2026.json").read_bytes()
    return web._imported_form(type("Upload", (), {"filename": "p.json", "stream": io.BytesIO(content)}))[0]


def test_sensitivity_ranks_every_input_and_draws_its_curve():
    page = html.unescape(post(action="sensitivity", sens_percent="10"))
    assert "O que mais pesa no custo" in page and "const SENS" in page and "sensitivity.js" in page
    assert re.search(r"<li>O custo depende mais de: ", page)
    analysis = web.sensitivity(web.MultiDict(web._default_form()) | {"sens_percent": "10"})
    impacts = [max(abs(d) for d in (i["down"], i["up"]) if d is not None) for i in analysis["items"]]
    assert impacts and impacts == sorted(impacts, reverse=True)
    assert all([p["percent"] for p in i["curve"]] == web.CURVE_PERCENTS for i in analysis["items"])
    assert "milk_price" not in {i["key"] for i in analysis["items"]}  # milk price changes the IOFC, not the diet cost


def test_price_elasticity_is_the_feed_share_of_the_diet_cost():
    analysis = web.sensitivity(_spreadsheet_form() | {"sens_percent": "10"})
    silage = next(i for i in analysis["items"] if i["key"] == "cost_51")
    share = next(r["cost"] for r in web.simulate(_spreadsheet_form())["ration"] if r["id"] == 51) / analysis["cost"]
    assert silage["elasticity"] == pytest.approx(share, abs=0.01)
    protein = next(i for i in analysis["items"] if i["key"] == "metabolizable_protein")
    assert protein["breakpoints"] and any(p.get("change") for p in protein["curve"])  # feeds change in the range


def test_validity_range_is_where_the_feeds_change():
    form = _spreadsheet_form()
    analysis = web.sensitivity(form | {"sens_percent": "10"})
    protein = next(i for i in analysis["items"] if i["key"] == "metabolizable_protein")
    up = protein["valid_up"]
    assert 0 < up["same"] < up["change"] <= 10 and up["change"] - up["same"] <= 10 / 2 ** web.BISECTIONS + 1e-9
    assert "sai Cottonseed" in up["what"]

    def feeds(percent):
        changed = web.MultiDict(form)
        changed["metabolizable_protein"] = str(protein["value"] * (1 + percent / 100))
        return {r["id"] for r in web.simulate(changed)["ration"] if r["amount"] >= web.NEGLIGIBLE}

    assert feeds(up["same"]) == feeds(0) != feeds(up["change"])


def test_sensitivity_rejects_a_non_positive_step():
    assert "o passo da variação deve ser positivo" in post(action="sensitivity", sens_percent="0")


def test_pulp_model_in_the_page_reports_shadow_prices():
    selected = ",".join(str(i) for i in sorted(web.DEFAULT_SELECTED_IDS | {300}))
    page = post(optimizer="pulp", selected_feeds=selected)
    assert "<h2>Viável</h2>" in page and "Preço-sombra" in page
    assert "Vale entre" in page and "Custo reduzido e faixa de preço" in page and "não entraria nem de graça" in html.unescape(page)
    infeasible = html.unescape(post(optimizer="pulp"))  # the Midwest farm has no vitamin premix
    assert "Vitamina A: falta" in infeasible and "VitTM Premix, generic (300)" in infeasible


def test_spreadsheet_price_scenario_imports_and_solves():
    name = "planilha-2026.json"
    content = (Path(__file__).parents[1] / "scenarios" / "precos" / name).read_bytes()
    upload = {"action": "import", "scenario": (io.BytesIO(content), name)}
    page = html.unescape(client.post("/", data=upload, content_type="multipart/form-data").get_data(as_text=True))
    assert "Não foi possível importar" not in page
    form = web._imported_form(type("Upload", (), {"filename": name, "stream": io.BytesIO(content)}))[0]
    assert "<h2>Viável</h2>" in client.post("/", data=form).get_data(as_text=True)


def test_imports_a_rufas_farm_feed_file():
    content = (Path(__file__).parents[1] / "scenarios" / "fazendas" / "freestall-midwest" / "feed.json").read_bytes()
    upload = {"action": "import", "scenario": (io.BytesIO(content), "feed.json")}
    page = html.unescape(client.post("/", data=upload, content_type="multipart/form-data").get_data(as_text=True))
    assert "Não foi possível importar" not in page and "lac_cow" in page
    # the lactating pen's feeds, not the calves' milk (202) and starter (216)
    assert sorted(re.findall(r'name="selected_feeds" value="(\d+)" checked', page), key=int) == ["23", "44", "50", "104", "110", "301", "302"]
    assert field(page, "cost_44") == 1.2876 and field(page, "cost_216") == 1.4684
    form = web._imported_form(type("Upload", (), {"filename": "feed.json", "stream": io.BytesIO(content)}))[0]
    assert "<h2>Viável</h2>" in client.post("/", data=form).get_data(as_text=True)


def test_imports_a_dietopt_scenario_file():
    content = (Path(__file__).parent / "data" / "cenario-dietopt.json").read_bytes()
    upload = {"action": "import", "scenario": (io.BytesIO(content), "cenario-avaliar-dietas.json")}
    page = html.unescape(client.post("/", data=upload, content_type="multipart/form-data").get_data(as_text=True))
    assert "Não foi possível importar" not in page
    assert sorted(re.findall(r'name="selected_feeds" value="(\d+)" checked', page), key=int) == ["23", "44", "50", "110", "167", "230"]
    assert field(page, "cow_body_weight") == 680 and field(page, "walking_distance") == 100
    assert field(page, "cost_23") == 1.1 and field(page, "max_230") == 0.6
    assert "diets" in page  # the evaluated diets are not used by this page, and the note says so
