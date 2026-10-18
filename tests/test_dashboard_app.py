"""Runs the real dashboard script (src/dashboard/app.py) end-to-end against
the CURRENT committed results/ files via streamlit.testing.v1.AppTest, and
asserts no exception anywhere.

This is the test that would have caught the real crash found on a laptop run
at commit f81a1ff: results/metrics.json's impact_score_event_study had become
{"status": "not_run", ...} (GDELT abandoned -- see docs/ASSUMPTIONS.md), and
the Engine Quality tab's code did `ies["n_resolved"]` with no .get() guard,
raising KeyError and crashing the whole page before the Stress Test tab (on
the same script run -- Streamlit executes the full script top-to-bottom every
time, `with tab:` only scopes layout, not execution) ever got a chance to
render. Every unit test in this suite mocks its inputs and would never see
this -- only running the real file against the real, current data surfaces
it.

Streamlit's `with tab:` blocks are layout containers, not conditional
branches -- a single `at.run()` executes every tab's code in one pass, so
this covers tabs 1/2/3/5 without needing to simulate switching tabs. Tab 4
(Scenario Explorer)'s revaluation only runs after its button is clicked, so
that's exercised with an explicit button click."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent / "src" / "dashboard" / "app.py"


def _assert_no_exception(at: AppTest) -> None:
    if at.exception:
        messages = "\n".join(f"{e.value!r}" for e in at.exception)
        raise AssertionError(f"Dashboard raised {len(at.exception)} exception(s):\n{messages}")


class TestDashboardAppAgainstRealCommittedResults:
    def test_initial_run_no_exception_on_any_tab(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=60)
        at.run()
        _assert_no_exception(at)

    def test_scenario_explorer_button_click_no_exception(self):
        """Tab 4's revaluation is gated behind st.button -- click it to exercise
        that code path too, not just the page's initial unconditional render."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=60)
        at.run()
        _assert_no_exception(at)
        if at.button:
            at.button[0].click().run()
            _assert_no_exception(at)
