"""The monthly canary that re-asks the live reference: its list and its verdicts.

The canary itself needs the network and runs on a schedule
(`.github/workflows/fire-canary.yml`). What can rot without anyone noticing is
the offline half — a canary naming a fixture that was renamed, or a verdict
that calls a failing site "drift" — so that is what this pins.
"""

from __future__ import annotations

import canary
import parity


class TestCanaryList:
    """Every canary is a recorded run the corpus already replays."""

    def test_every_canary_is_recorded(self) -> None:
        """Each name resolves to a fixture on disk."""
        missing = [name for name in canary.CANARIES if not parity.exists(name)]
        assert missing == []

    def test_only_the_crashing_mode_is_uncharted(self) -> None:
        """Every canary was answered with charts, except the mode the reference crashes on."""
        uncharted = [n for n in canary.CANARIES if not canary.charted(parity.load(n))]
        assert uncharted == ["sol_improve_cash"]


class TestJudge:
    """How a fresh answer is classified."""

    def test_recorded_answer_agrees_with_itself(self) -> None:
        """A recorded run judged as if fresh is in agreement."""
        recorded = parity.load("pn_pizuim_2010")
        assert canary.judge("pn_pizuim_2010", recorded, recorded).status == "ok"

    def test_error_banner_is_a_site_error(self) -> None:
        """An error banner is reported as the site failing, not as drift."""
        recorded = parity.load("baseline")
        fresh = {"charts": {}, "meta": {"errors": "E_SIMSTATE_DESYNC"}}
        verdict = canary.judge("baseline", recorded, fresh)
        assert (verdict.status, verdict.ok) == ("site error", False)

    def test_refused_where_it_used_to_answer(self) -> None:
        """A scenario that used to be answered and now is not is flagged."""
        recorded = parity.load("baseline")
        fresh = {"charts": {}, "meta": {"messages": "rejected"}}
        assert canary.judge("baseline", recorded, fresh).status == "refused"

    def test_crashing_mode_still_refused_is_fine(self) -> None:
        """The mode that crashed on the reference crashing again is no news."""
        recorded = parity.load("sol_improve_cash")
        verdict = canary.judge("sol_improve_cash", recorded, {"charts": {}, "meta": {}})
        assert (verdict.status, verdict.ok) == ("still refused", True)

    def test_crashing_mode_answering_is_news(self) -> None:
        """A mode the reference used to crash on now answering is flagged."""
        recorded = parity.load("sol_improve_cash")
        fresh = parity.load("baseline")
        verdict = canary.judge("sol_improve_cash", recorded, fresh)
        assert (verdict.status, verdict.ok) == ("answers now", False)
