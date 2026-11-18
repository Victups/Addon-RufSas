r"""
Sensibilidade da dieta a ±10% e ±20% no preço dos ingredientes principais, com o cenário `planilha-2026.json` e a vaca
padrão da página (exigências NASEM recalculadas). Re-resolve cada caso e imprime uma tabela em Markdown.

    $env:PYTHONPATH="RufSas/RuFaS"; .venv\Scripts\python scenarios\precos\sensibilidade.py
"""

import io
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "RufSas" / "RuFaS"), str(ROOT)]
from addon_rufas import web  # noqa: E402

INGREDIENTS = [51, 58, 167, 44, 163]  # silagem, caroço, farelo, milho, casca de soja
FACTORS = [0.8, 0.9, 1.1, 1.2]
OPTIMIZERS = {"linear": "SLP", "pulp": "NRC"}


def base_form() -> web.MultiDict:
    raw = (ROOT / "scenarios" / "precos" / "planilha-2026.json").read_bytes()
    form, _ = web._imported_form(SimpleNamespace(filename="planilha-2026.json", stream=io.BytesIO(raw)))
    form.setlist("selected_feeds", form.getlist("selected_feeds") + ["44", "163"])  # milho e casca também disponíveis
    page = web.app.test_client().post("/", data=form | {"action": "calculate_requirements"}).get_data(as_text=True)
    for key in web.DEFAULTS:
        form[key] = re.search(rf'name="{key}" value="([^"]+)"', page).group(1)
    return form


def ration(result: dict) -> dict[int, float]:
    return {row["id"]: row["amount"] for row in result["ration"]}


def describe(before: dict[int, float], after: dict[int, float]) -> str:
    changes = [(feed_id, after.get(feed_id, 0.0) - before.get(feed_id, 0.0)) for feed_id in sorted(set(before) | set(after))]
    text = [f"{web.FEED_NAMES[i].split(',')[0]} {d:+.2f}" for i, d in changes if abs(d) >= 0.05]
    return "; ".join(text) or "sem mudança"


def main() -> None:
    form = base_form()
    print("| Modelo | Ingrediente | Preço | Custo R$/vaca/dia | Δ custo | Mudança na ração (kg MS/dia) |")
    print("|---|---|---|---|---|---|")
    for optimizer, label in OPTIMIZERS.items():
        form["optimizer"] = optimizer
        base = web.simulate(form)
        cost = float(base["solution"].fun)
        print(f"| {label} | (base) | — | {cost:.2f} | — | {describe({}, ration(base))} |")
        for feed_id in INGREDIENTS:
            price = float(form[f"cost_{feed_id}"])
            for factor in FACTORS:
                case = form.copy()
                case[f"cost_{feed_id}"] = str(price * factor)
                result = web.simulate(case)
                new = float(result["solution"].fun)
                print(f"| {label} | {web.FEED_NAMES[feed_id].split(',')[0]} ({feed_id}) | {factor - 1:+.0%} | {new:.2f} "
                      f"| {100 * (new - cost) / cost:+.1f}% | {describe(ration(base), ration(result))} |")


if __name__ == "__main__":
    main()
