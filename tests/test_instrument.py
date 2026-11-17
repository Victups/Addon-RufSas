import json
from types import SimpleNamespace

from addon_rufas.instrument import record_ration_events


class FakePen:
    """Mimics RuFaS Pen's formulation loop: fail, cut milk, retry, as many times as `failures`."""

    animal_combination = SimpleNamespace(name="LAC_COW")

    def __init__(self, failures, final_success):
        self.failures, self.final_success = failures, final_success

    def _attempt_formulation(self):
        return SimpleNamespace(success=self.failures == 0 and self.final_success)

    def reduce_milk_production(self):
        return True

    def _run_formulation_attempts(self, is_ration_defined_by_user):
        while True:
            solution = self._attempt_formulation()
            if solution.success or self.failures == 0:
                return solution
            self.failures -= 1
            self.reduce_milk_production()


def test_events_count_retries_milk_cuts_and_fallbacks(tmp_path):
    record_ration_events(FakePen, tmp_path / "events.jsonl", "slsqp")
    FakePen(failures=0, final_success=True)._run_formulation_attempts(False)
    FakePen(failures=2, final_success=True)._run_formulation_attempts(False)
    FakePen(failures=1, final_success=False)._run_formulation_attempts(False)
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [(e["attempts"], e["milk_reductions"], e["fallback"]) for e in events] == [
        (1, 0, None),
        (3, 2, None),
        (2, 1, "previous_ration"),
    ]
