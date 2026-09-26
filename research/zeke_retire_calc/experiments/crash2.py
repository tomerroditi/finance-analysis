"""Second attempt at a traceback from inside the bridge code.

`crash` showed zero spending is guarded. These feed values the form never
offers into the fields the bridge reads — an unknown tactic, a partner who is
not born yet — hoping the exception is raised where the bridge is computed.
"""
from experiments.couple import couple
from scenario import flow, form, pension, portfolio

SCENARIOS = {
    "crash_tactic_main": form(retire_at=45, expenses=[flow(5_000)],
                              portfolios=[portfolio(1_200_000, description="W1")],
                              pension=pension(600_000, tactic="61", frozen=True)),
    "crash_tactic_partner": couple(partner_pension=pension(600_000, tactic="61", frozen=True)),
    "crash_partner_unborn": couple(partner_pension=pension(600_000, tactic="60", frozen=True),
                                   partner_dob="2030-01-01"),
}
