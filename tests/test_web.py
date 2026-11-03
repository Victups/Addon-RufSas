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
