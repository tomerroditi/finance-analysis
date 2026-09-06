"""Monthly simulation engine for the early-retirement calculator.

Reproduces the reference calculator documented in
``research/zeke_retire_calc/notes/``. Four rules dominate the design, each
verified against recorded fixtures:

1. Growth is monthly and multiplicative in the fee:
   ``(balance + deposit) * ((1 + return) * (1 - fee)) ** (1/12)``.
2. The model is **two-phase**: at retirement, portfolios designated for
   withdrawal stop compounding (notes/07); goal portfolios never stop.
3. Every date input is **month-granular** — the day component is ignored.
4. Loans use a *nominal* monthly rate (``annual / 12``), unlike portfolios.

Everything is in real terms — today's shekels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from backend.services.fire import decumulation
from backend.services.fire import loans as loan_math
from backend.services.fire import national_insurance
from backend.services.fire.keren_hishtalmut import KerenAccount
from backend.services.fire.pension import PensionAccount, annuity_factor
from backend.services.fire.taxation import TaxableAccount
from backend.services.fire.models import (
    CashFlow,
    PortfolioType,
    EndType,
    PensionTactic,
    Plan,
    Portfolio,
    PortfolioDesignation,
    StartType,
)

HORIZON_AGE = 81.0
"""Simulation end age — a hard-coded constant in the reference, not gender- or
cohort-derived (verified for male/female and DOB 1980/1990)."""


@dataclass
class MonthRecord:
    """One simulated month."""

    index: int
    year: int
    month: int
    age: float
    incomes: dict[str, float] = field(default_factory=dict)
    """Every shekel that came in this month, by source.

    A closed decomposition, exactly as the reference charts it: pay and one-off
    income, each annuity, the state pension, and every withdrawal — from the
    checking account, from each portfolio (gross of the tax on the sale), and
    from each study fund. `shortfall` is the reference's "missing piece": what
    the plan needed and could not fund."""

    expenses: dict[str, float] = field(default_factory=dict)
    """Every shekel that went out this month, by destination.

    Balances `incomes` to the agora, because the reference's own two charts do:
    living costs and one-off spending, debt service, the tax on each portfolio
    sale, income tax and national insurance on each annuity, every deposit
    routed into a portfolio, the top-up of the cash buffer, and finally
    `unplanned` — surplus that found no destination and stayed in checking."""
    assets: dict[str, float] = field(default_factory=dict)
    liabilities: float = 0.0
    cash: float = 0.0
    shortfall: float = 0.0

    @property
    def net_worth(self) -> float:
        """Assets less outstanding debt — the reference's net-worth line."""
        return sum(self.assets.values()) - self.liabilities


@dataclass
class Annuity:
    """One row of the reference's annuity list (`רשימת הקצבאות`)."""

    owner: str
    source: str
    """`pension`, `gemel` or `national_insurance`."""
    component: str
    """`tagmulim` / `pitzuim` for a pension, else the source's own name."""
    recognised: bool
    claim_age: float
    monthly: float
    factor: float | None
    description: str = ""
    """The account's name, where the user gave one."""


@dataclass
class Withdrawal:
    """One segment of the reference's drawdown plan (`תוכנית המשיכה מהתיקים`)."""

    source: str
    description: str
    from_age: float
    to_age: float
    monthly_average: float


@dataclass
class Snapshot:
    """One of the reference's two asset cards, with its doughnut breakdown."""

    label: str
    """`now` or `retirement`."""
    year: int
    month: int
    net_worth: float
    breakdown: dict[str, float]
    """Totals by asset class: `portfolios`, `cash`, `keren`, `pension`,
    `realestate` — the categories the reference's doughnut uses. Empty classes
    are dropped, as it drops them; an entirely empty breakdown is a plan that
    owns nothing yet, which the reference draws as a single placeholder slice."""

    shortfall_capital: float = 0.0
    """The reference's `חוסר` slice: what the plan is short, as capital.

    The present value of every unfunded month, discounted at the first
    portfolio's **gross** return — the fee is not deducted for this one figure.
    Recovered from six recorded runs, exact to 0.2 shekels on the first card
    (notes/16)."""


@dataclass
class SimulationResult:
    months: list[MonthRecord]
    retire_index: int
    solvent: bool
    annuity_streams: list[tuple[float, int]] = field(default_factory=list)
    """Every annuity this run started: `(monthly amount, month it began)`.

    Feeds the decumulation bridge, which is weighted by these (notes/15)."""

    annuities: list[Annuity] = field(default_factory=list)
    """The annuity list the reference prints, one row per component."""

    def withdrawal_plan(self) -> list["Withdrawal"]:
        """Where the money came from, as the reference's drawdown plan.

        One segment per bucket ever drawn: the ages of its first and last draw,
        and the average over that span. Verified against the reference's own
        prose — `baseline` draws from checking between 53.2 and 73.2 averaging
        4,145.8, then from the broker account to 81.0 averaging 2,210.2.
        """
        segments: list[Withdrawal] = []
        keys = {key for record in self.months for key, value in record.incomes.items()
                if value and (key == "cash" or key.startswith(("portfolio", "keren")))}
        for key in sorted(keys):
            run: list[MonthRecord] = []
            for record in self.months + [None]:
                if record is not None and record.incomes.get(key):
                    run.append(record)
                    continue
                # A gap closes the segment: the reference reports each unbroken
                # stretch a bucket funded, not the span from first draw to last.
                if run and sum(r.incomes[key] for r in run) / len(run) >= 0.05:
                    segments.append(Withdrawal(
                        source=key, description=self.labels.get(key, ""),
                        from_age=run[0].age, to_age=run[-1].age,
                        monthly_average=sum(r.incomes[key] for r in run) / len(run)))
                run = []
        return sorted(segments, key=lambda s: (s.from_age, s.source))

    labels: dict[str, str] = field(default_factory=dict)
    """Display name per asset key, where the user named the account."""

    opening: dict[str, float] = field(default_factory=dict)
    """Balances before the first month's growth — the reference's "today" card."""

    def snapshots(self) -> list["Snapshot"]:
        """The two asset cards: today, and the last working month.

        The shortfall slice is discounted to month 0 on the first card and to
        the first *retired* month on the second — one month past the balances
        beside it, which is the reference's own convention.
        """
        cards = [("now", -1, self.opening, 0)]
        if 0 < self.retire_index <= len(self.months):
            record = self.months[self.retire_index - 1]
            cards.append(("retirement", self.retire_index - 1, record.assets,
                          self.retire_index))
        out = []
        for label, index, assets, as_of in cards:
            record = self.months[max(index, 0)]
            out.append(Snapshot(
                label=label,
                year=record.year, month=record.month,
                shortfall_capital=self._shortfall_capital(as_of),
                net_worth=sum(assets.values()) - (record.liabilities if index >= 0 else 0.0),
                breakdown={group: total for group, total in (
                    (group, sum(value for key, value in assets.items()
                                if key.startswith(prefix)))
                    for group, prefix in (("cash", "cash"), ("portfolios", "portfolio"),
                                          ("keren", "keren"), ("pension", "pension"),
                                          ("realestate", "realestate")))
                    if total}))
        return out

    def pension_income(self) -> list[tuple[str, float, float]]:
        """`(owner, age, monthly)` — the reference's closing line, per person.

        "Your annuity from all pension sources will be, at age X, Y" — where X
        is the age the last of that person's pension components starts (the
        state pension is not one of them, and a person with no pension at all
        is quoted at 60), and Y is what they all pay together.
        """
        out = []
        for owner in dict.fromkeys(a.owner for a in self.annuities):
            rows = [a for a in self.annuities
                    if a.owner == owner and a.source != "national_insurance"]
            out.append((owner,
                        max((a.claim_age for a in rows),
                            default=self.default_claim_age.get(owner, 60.0)),
                        sum(a.monthly for a in rows)))
        return out

    default_claim_age: dict[str, float] = field(default_factory=dict)
    """Age the reference quotes for a person whose pension pays nothing — the
    age their tactic would have claimed at (`pf_tactics67` quotes 67, not 60)."""

    def _shortfall_capital(self, as_of: int) -> float:
        """Present value at month `as_of` of everything the plan cannot fund.

        Two parts, both discounted the same way. Every unfunded month, and —
        for a plan that misses a portfolio's goal — the gap at the retirement
        month, since that is the last month the search tried. `desig_goal` is
        the recorded example: 9,000,000 wanted, 2,900,229.1 there, and the
        reference's slice is exactly that difference (notes/16).
        """
        factor = self.gross_monthly_factor
        total = sum(record.incomes.get("shortfall", 0.0) / factor ** (record.index + 1 - as_of)
                    for record in self.months)
        if 0 < self.retire_index <= len(self.months):
            assets = self.months[self.retire_index - 1].assets
            for key, goal in self.goals.items():
                total += (max(goal - assets.get(key, 0.0), 0.0)
                          / factor ** (self.retire_index - as_of))
        return total

    goals: dict[str, float] = field(default_factory=dict)
    """Target balance per asset key, for the accounts the plan has one for."""

    gross_monthly_factor: float = 1.0
    """Discount rate for the shortfall slice — gross of the management fee."""

    def unallocated_surplus(self) -> list[float]:
        """The reference's puzzling "unplanned expense" series.

        It is simply the month-on-month increase in the checking account —
        surplus that found no destination. Reproduced here so the chart can be
        drawn the same way.
        """
        out = [0.0]
        for prev, cur in zip(self.months, self.months[1:]):
            out.append(max(cur.cash - prev.cash, 0.0))
        return out


class Simulator:
    """Runs one scenario with a *given* retirement month.

    Choosing that month is the solver's job; this class answers "what happens
    if retirement is at month R". `retire_index` is the first **fully retired**
    month: flows ending at FIRE are live through `R - 1`, flows starting at
    FIRE begin at `R`.
    """

    def __init__(self, plan: Plan):
        self.plan = plan
        self._today: date | None = None
        self._streams: list[tuple[float, int]] = []
        self._streams_for: int | None = None
        """Annuities the probe pass found, and the retirement month they are for."""
        if plan.person.date_of_birth is None:
            raise ValueError("date of birth is required")
        self.dob = plan.person.date_of_birth

    # -- time grid ---------------------------------------------------------

    def age_at(self, index: int, today: date) -> float:
        """Age in years at month `index`, as whole months since birth / 12."""
        months = (today.year - self.dob.year) * 12 + (today.month - self.dob.month)
        return (months + index) / 12

    def month_count(self, today: date) -> int:
        """Months from the current month through the month age hits 81.0."""
        birth_index = (today.year - self.dob.year) * 12 + (today.month - self.dob.month)
        return int(round(HORIZON_AGE * 12)) - birth_index + 1

    def _index_of(self, when: date, today: date) -> int:
        """Month index of a calendar date. The day is ignored."""
        return (when.year - today.year) * 12 + (when.month - today.month)

    def _age_60_index(self, today: date) -> int:
        """Last month in which the main retiree is under 61 — inclusive end."""
        birth_index = (today.year - self.dob.year) * 12 + (today.month - self.dob.month)
        return 60 * 12 - birth_index

    # -- cash-flow windows -------------------------------------------------

    def _window(self, flow: CashFlow, retire_index: int, today: date) -> tuple[int, int]:
        """Inclusive `(first, last)` month indices in which a flow is live.

        Verified in notes/04: `from_date`/`to_date` are inclusive at month
        granularity, a flow ending at FIRE is live through the last working
        month, and a flow starting at FIRE begins the month after.
        """
        last_month = self.month_count(today) - 1

        if flow.start_type == StartType.NOW:
            first = 0
        elif flow.start_type == StartType.FIRE:
            first = retire_index
        elif flow.start_type in (StartType.FROM_DATE, StartType.ONE_TIME):
            if flow.start_date is None:
                return (1, 0)
            first = max(self._index_of(flow.start_date, today), 0)
        else:
            raise NotImplementedError(flow.start_type)

        if flow.start_type == StartType.ONE_TIME:
            # A single month at the row's start date; a past-dated one is dropped.
            if flow.start_date is None or self._index_of(flow.start_date, today) < 0:
                return (1, 0)
            return (first, first)

        if flow.end_type == EndType.FOREVER:
            last = last_month
        elif flow.end_type == EndType.FIRE:
            last = retire_index - 1
        elif flow.end_type == EndType.TO_DATE:
            last = self._index_of(flow.end_date, today) if flow.end_date else -1
        elif flow.end_type == EndType.AGE_60:
            last = self._age_60_index(today)
        else:
            raise NotImplementedError(flow.end_type)

        return (first, min(last, last_month))

    def _amount(self, flow: CashFlow, index: int, first: int) -> float:
        """Flow amount in month `index`.

        The annual rise compounds monthly and is anchored at the row's **own**
        first active month, not at the start of the simulation (notes/04).
        """
        if not flow.annual_rise_pct:
            return flow.amount
        return flow.amount * (1 + flow.annual_rise_pct / 100) ** ((index - first) / 12)

    def _flow_total(self, flows, index, retire_index, today, one_time=None) -> float:
        """Total of the flows live in `index`.

        `one_time=True` keeps only the single-month rows, `False` only the
        recurring ones. The reference charts the two separately — recurring
        income as `עבודה` and one-off income as `הכנסות חד פעמיות`, recurring
        spending as `הוצאות שוטפות` and one-off spending as `יעדים` (notes/16).
        """
        total = 0.0
        for flow in flows:
            if one_time is not None and (flow.start_type == StartType.ONE_TIME) != one_time:
                continue
            first, last = self._window(flow, retire_index, today)
            if first <= index <= last:
                total += self._amount(flow, index, first)
        return total

    # -- growth ------------------------------------------------------------

    def _decumulation_return(self, retire_index: int) -> float:
        """Post-retirement return: the caller's override, else the measured table.

        The surface is read at the **bridge** — the wait from retirement to the
        pension. With no pension that is the wait to the statutory age; with
        one, it is the wait to each annuity this plan starts, weighted by how
        much each pays (notes/15). Claiming a pension at 60 therefore shortens
        the bridge and cuts the return, and claiming only the recognised share
        early lands in between.
        """
        if self.plan.decumulation_return_pct is not None:
            return self.plan.decumulation_return_pct
        confidence = self.plan.retire_rule_confidence
        retire_age = self._retire_age_cache(retire_index)
        streams = self._streams
        total = sum(monthly for monthly, _ in streams)
        if total <= 0:
            return decumulation.decumulation_return_pct(
                confidence, retire_age,
                national_insurance.STATUTORY_AGE[self.plan.person.gender])
        return sum(
            monthly * decumulation.decumulation_return_pct(
                confidence, retire_age,
                retire_age + max(index - retire_index, 0) / 12)
            for monthly, index in streams) / total

    def _needs_stream_pass(self) -> bool:
        """Whether any annuity here can start before the statutory age.

        When none can, every stream starts at the statutory age and the blend
        collapses to the plain bridge — so the extra pass is skipped.
        """
        if self.plan.decumulation_return_pct is not None:
            return False
        pensions = (self.plan.pension, self.plan.partner_pension)
        if any(pension is not None
               and pension.tactic is not PensionTactic.ALL_FROM_STATUTORY
               for pension in pensions):
            return True
        return any(portfolio.designation in (PortfolioDesignation.MUKERET_MAIN,
                                             PortfolioDesignation.MUKERET_PARTNER)
                   for portfolio in self.plan.portfolios)

    def _retire_age_cache(self, retire_index: int) -> float:
        """Age in the last working month — what the reference reports."""
        if self._today is None:
            return 0.0
        return self.age_at(max(retire_index - 1, 0), self._today)

    def _monthly_factor(self, portfolio: Portfolio, index: int, retire_index: int) -> float:
        """Growth factor for one month.

        Withdrawal portfolios switch at retirement from the user's return to the
        confidence-derived decumulation return; goal portfolios keep the user's
        return for the whole horizon (notes/07).
        """
        if portfolio.designation != PortfolioDesignation.WITHDRAW or index < retire_index:
            return portfolio.monthly_factor
        # The haircut can never *raise* the return: a 0% portfolio stays at 0%
        # (verified — `pn_rule80_flat` and `pn_rule100_flat` are bit-identical).
        rate = min(self._decumulation_return(retire_index), portfolio.annual_return_pct)
        return ((1 + rate / 100) * (1 - portfolio.annual_fee_pct / 100)) ** (1 / 12)

    # -- main loop ---------------------------------------------------------

    def run(self, retire_index: int, today: date | None = None) -> SimulationResult:
        today = today or date.today()
        if self._streams_for != retire_index and self._needs_stream_pass():
            # The bridge is weighted by the annuities this plan starts, and
            # those are only known once it has been run. They do not depend on
            # the decumulation return itself — a pension, and a gemel earmarked
            # for annuitisation, both grow at their own rate whatever the
            # withdrawal portfolios do — so one probe pass settles them and the
            # real run below is exact.
            probe = Simulator(self.plan)
            probe._streams, probe._streams_for = [], retire_index
            self._streams = probe.run(retire_index, today).annuity_streams
            self._streams_for = retire_index
        self._today = today
        plan = self.plan
        annuity_streams: list[tuple[float, int]] = []
        total_months = self.month_count(today)

        cash = plan.cash_balance
        accounts = [TaxableAccount.from_portfolio(p) for p in plan.portfolios]
        funds = [KerenAccount.from_fund(f) for f in plan.kranot_hishtalmut]
        pensions = self._pension_accounts()
        gemel_annuities: dict[int, float] = {}
        gemel_owner: dict[int, str] = {}
        converted: set[int] = set()
        loan_starts = [
            self._index_of(loan.start_date, today) if loan.start_date else 0
            for loan in plan.loans
        ]
        months: list[MonthRecord] = []
        solvent = True

        for t in range(total_months):
            age = self.age_at(t, today)
            cash_in: dict[str, float] = {}
            cash_out: dict[str, float] = {}
            income = self._flow_total(plan.incomes, t, retire_index, today)
            cash_in["work"] = self._flow_total(
                plan.incomes, t, retire_index, today, one_time=False)
            cash_in["one_time"] = self._flow_total(
                plan.incomes, t, retire_index, today, one_time=True)
            if t < retire_index:
                income += plan.monthly_cash_improvement
                cash_in["work"] += plan.monthly_cash_improvement
            partner_age = (self._partner_age(t, today)
                           if plan.partner is not None else None)
            state_pension = national_insurance.monthly_amount(
                plan.person, age, plan.partner, partner_age)
            if plan.partner is not None:
                state_pension += national_insurance.monthly_amount(
                    plan.partner, partner_age, plan.person, age)
            cash_in["state_pension"] = national_insurance.monthly_amount(
                plan.person, age, plan.partner, partner_age)
            if plan.partner is not None:
                cash_in["state_pension_partner"] = national_insurance.monthly_amount(
                    plan.partner, partner_age, plan.person, age)
            expense = self._flow_total(plan.expenses, t, retire_index, today)
            cash_out["living"] = self._flow_total(
                plan.expenses, t, retire_index, today, one_time=False)
            cash_out["one_time"] = self._flow_total(
                plan.expenses, t, retire_index, today, one_time=True)
            debt_service = sum(
                loan_math.payment_at(loan, t - start)
                for loan, start in zip(plan.loans, loan_starts)
            )
            surplus = income + state_pension - expense - debt_service

            # A gemel portfolio earmarked as a recognised annuity converts in
            # full at 60 into a tax-free stream (notes/03). This runs *before*
            # the pension loop because national insurance is charged on the
            # whole annuity a person draws, this one included, from the month it
            # starts (notes/16).
            for index, portfolio in enumerate(plan.portfolios):
                claim_age = self._mukeret_claim_age(portfolio, t, today)
                if claim_age is not None and index not in converted:
                    owner = (plan.partner if portfolio.designation
                             == PortfolioDesignation.MUKERET_PARTNER and plan.partner
                             else plan.person)
                    gemel_annuities[index] = (
                        accounts[index].balance / annuity_factor(owner.gender, 60))
                    annuity_streams.append((gemel_annuities[index], t))
                    gemel_owner[index] = "" if owner is plan.person else "_partner"
                    accounts[index].balance = 0.0
                    accounts[index].basis = 0.0
                    converted.add(index)
            gemel_by_owner: dict[str, float] = {}
            for index, amount in gemel_annuities.items():
                gemel_by_owner[gemel_owner[index]] = (
                    gemel_by_owner.get(gemel_owner[index], 0.0) + amount)

            # Pension: contribute, convert what is due, then collect the annuity.
            annuity_income = 0.0
            annuity_deductions = 0.0
            severance_cash = 0.0
            for owner, account in pensions:
                owner_age = age if owner is plan.person else self._partner_age(t, today)
                first, last = self._window(
                    CashFlow(start_type=StartType.NOW,
                             end_type=account.plan_pension.end_type,
                             end_date=account.plan_pension.end_date),
                    retire_index, today)
                if first <= t <= last:
                    account.contribute()
                # Severance is redeemed in the first retired month — that is
                # "one month after FIRE", since the reference reports FIRE as
                # the last *working* month (notes/05, notes/08).
                if (account.plan_pension.withdraw_severance
                        and t == retire_index):
                    month_number_ = today.month + t
                    severance_cash += account.redeem_severance(
                        today.year + (month_number_ - 1) // 12, t)
                started = len(account.streams)
                account.annuitise_due(owner_age)
                annuity_streams.extend(
                    (stream.monthly, t) for stream in account.streams[started:])
                who = "" if owner is plan.person else "_partner"
                recognised, entitling = account.income_at(owner_age)
                tax, insurance = account.deductions_at(
                    owner_age, t, also_drawing=gemel_by_owner.get(who, 0.0))
                annuity_income += recognised + entitling
                annuity_deductions += tax + insurance
                cash_in[f"recognised{who}"] = recognised
                cash_in[f"entitling{who}"] = entitling
                cash_out[f"income_tax{who}"] = tax
                cash_out[f"national_insurance{who}"] = insurance
            annuity_income += sum(gemel_annuities.values())
            for index, amount in gemel_annuities.items():
                cash_in[f"gemel{index}"] = amount
            # The reference charts a severance redemption as one-off income,
            # alongside any one-time income row the user typed (notes/16).
            cash_in["one_time"] += severance_cash
            surplus += annuity_income - annuity_deductions + severance_cash

            # Study-fund deposits are funded outside the modelled surplus.
            for fund, account in zip(plan.kranot_hishtalmut, funds):
                first, last = self._window(
                    CashFlow(start_type=StartType.NOW, end_type=fund.end_type,
                             end_date=fund.end_date), retire_index, today)
                if first <= t <= last:
                    account.deposit(fund.monthly_deposit)

            shortfall = 0.0
            tax_paid = 0.0
            cash_out["loans"] = debt_service
            if surplus >= 0:
                cash = self._deposit(surplus, cash, accounts, cash_out)
            else:
                cash, shortfall, tax_paid = self._withdraw(
                    -surplus, cash, accounts, funds, age, cash_in, cash_out)
                if shortfall > 0:
                    solvent = False
                    cash_in["shortfall"] = shortfall

            for i, portfolio in enumerate(plan.portfolios):
                accounts[i].grow(self._monthly_factor(portfolio, t, retire_index))
            for account in funds:
                account.grow(
                    None if t < retire_index
                    else account.decumulation_factor(self._decumulation_return(retire_index)))
            for _, account in pensions:
                account.grow()

            assets = {"cash": cash}
            assets.update({f"portfolio{i}": a.balance for i, a in enumerate(accounts)})
            assets.update({f"keren{i}": a.balance for i, a in enumerate(funds)})
            assets.update({f"pension{i}": a.balance for i, (_, a) in enumerate(pensions)})
            for i, property_ in enumerate(plan.real_estate):
                assets[f"realestate{i}"] = property_.value * (
                    1 + property_.annual_rise_pct / 100
                ) ** ((t + 1) / 12)

            liabilities = sum(
                loan_math.balance_at(loan, t - start)
                for loan, start in zip(plan.loans, loan_starts)
            )

            month_number = today.month + t
            months.append(
                MonthRecord(
                    index=t,
                    year=today.year + (month_number - 1) // 12,
                    month=(month_number - 1) % 12 + 1,
                    age=age,
                    incomes={k: v for k, v in cash_in.items() if v},
                    expenses={k: v for k, v in cash_out.items() if v},
                    assets=assets,
                    liabilities=liabilities,
                    cash=cash,
                    shortfall=shortfall,
                )
            )

        return SimulationResult(
            months=months, retire_index=retire_index, solvent=solvent,
            annuity_streams=annuity_streams, labels=self._labels(),
            default_claim_age={
                owner.name: float(60 if pension.tactic is PensionTactic.ALL_FROM_60
                                  else national_insurance.STATUTORY_AGE[owner.gender])
                for owner, pension in ((plan.person, plan.pension),
                                       (plan.partner, plan.partner_pension))
                if owner is not None and pension is not None},
            goals={f"portfolio{index}": portfolio.goal
                   for index, portfolio in enumerate(plan.portfolios)
                   if portfolio.goal > 0
                   and portfolio.designation is not PortfolioDesignation.WITHDRAW},
            gross_monthly_factor=(
                (1 + plan.portfolios[0].annual_return_pct / 100) ** (1 / 12)
                if plan.portfolios else 1.0),
            opening=self._opening_assets(),
            annuities=self._annuity_list(pensions, gemel_annuities, gemel_owner, today))

    # -- the reference's other result sections -----------------------------

    def _labels(self) -> dict[str, float]:
        """Display name per asset key, where the user named the account."""
        return {f"portfolio{index}": portfolio.description
                for index, portfolio in enumerate(self.plan.portfolios)
                if portfolio.description}

    def _opening_assets(self) -> dict[str, float]:
        """What the plan starts with, before the first month's growth."""
        plan = self.plan
        assets = {"cash": plan.cash_balance}
        assets.update({f"portfolio{i}": p.balance for i, p in enumerate(plan.portfolios)})
        assets.update({f"keren{i}": f.balance for i, f in enumerate(plan.kranot_hishtalmut)})
        assets.update({f"pension{i}": f.balance for i, (_, f) in
                       enumerate(self._pension_accounts())})
        assets.update({f"realestate{i}": r.value for i, r in enumerate(plan.real_estate)})
        return {key: value for key, value in assets.items() if value}

    def _annuity_list(self, pensions, gemel_annuities, gemel_owner, today) -> list[Annuity]:
        """Every annuity the plan ends up drawing, as the reference lists them.

        One row per component — the four-way pension split, each annuitised
        gemel, and each person's state pension — with the claim age and the
        annuity factor beside it. Components worth nothing are dropped, as the
        reference drops them.
        """
        plan = self.plan
        rows: list[Annuity] = []
        for owner, account in pensions:
            for stream in account.streams:
                if stream.monthly <= 0:
                    continue
                rows.append(Annuity(
                    owner=owner.name, source="pension", component=stream.component,
                    recognised=stream.recognised, claim_age=float(stream.claim_age),
                    monthly=stream.monthly, factor=stream.factor))
        for index, monthly in gemel_annuities.items():
            if monthly <= 0:
                continue
            owner = (plan.partner if gemel_owner[index] == "_partner" and plan.partner
                     else plan.person)
            rows.append(Annuity(
                owner=owner.name, source="gemel", component="gemel", recognised=True,
                claim_age=60.0, monthly=monthly,
                factor=annuity_factor(owner.gender, 60),
                description=plan.portfolios[index].description))
        for person, spouse in ((plan.person, plan.partner), (plan.partner, plan.person)):
            if person is None:
                continue
            claim = national_insurance.STATUTORY_AGE[person.gender]
            spouse_age = None
            if spouse is not None:
                # The increment depends on whether the spouse is eligible in the
                # month this pension starts, so read their age in exactly that
                # month — the first whose age is past the claim age.
                own_age = (self.age_at(0, today) if person is plan.person
                           else self._partner_age(0, today))
                start = int(claim * 12 - own_age * 12) + 1
                spouse_age = (self._partner_age(start, today) if spouse is plan.partner
                              else self.age_at(start, today))
            rows.append(Annuity(
                owner=person.name, source="national_insurance", component="old_age",
                recognised=True, claim_age=float(claim),
                monthly=national_insurance.monthly_amount(
                    person, claim + 1 / 12, spouse, spouse_age),
                factor=None))
        return rows

    # -- routing -----------------------------------------------------------

    def _deposit(self, surplus, cash, accounts, cash_out=None):
        """Route a monthly surplus, recording where each shekel went.

        Verified order (notes/01): repay any overdraft and top the buffer up,
        then fill portfolios in list order capped by the monthly deposit cap and
        by the goal balance, then leave the remainder in the checking account.
        """
        plan = self.plan
        record = cash_out if cash_out is not None else {}
        if cash < plan.cash_buffer:
            take = min(surplus, plan.cash_buffer - cash)
            cash += take
            surplus -= take
            record["buffer"] = take

        for index, (portfolio, account) in enumerate(zip(plan.portfolios, accounts)):
            if surplus <= 0:
                break
            room = portfolio.goal - account.balance
            if room <= 0:
                continue
            take = min(surplus, room)
            cap = portfolio.effective_deposit_cap
            if cap is not None:
                take = min(take, cap)
            account.deposit(take)
            surplus -= take
            record[f"deposit_portfolio{index}"] = take

        record["unplanned"] = surplus
        return cash + surplus

    def _mukeret_claim_age(self, portfolio, index: int, today: date) -> int | None:
        """Whether this portfolio annuitises this month, and at what claim age.

        Only a **gemel** portfolio earmarked `mukeret_main`/`mukeret_partner`
        converts; on any other instrument the designation behaves exactly like
        `goal` (notes/03).
        """
        if portfolio.designation not in (PortfolioDesignation.MUKERET_MAIN,
                                         PortfolioDesignation.MUKERET_PARTNER):
            return None
        if portfolio.kind != PortfolioType.GEMEL:
            return None
        return 60 if self.age_at(index, today) > 60 else None

    def _pension_accounts(self) -> list[tuple[object, PensionAccount]]:
        """One account per person who has a pension fund."""
        plan = self.plan
        out = []
        for owner, fund in ((plan.person, plan.pension),
                            (plan.partner, plan.partner_pension)):
            if owner is not None and fund is not None:
                out.append((owner, PensionAccount(
                    plan_pension=fund, gender=owner.gender,
                    statutory_age=national_insurance.STATUTORY_AGE[owner.gender])))
        return out

    def _partner_age(self, index: int, today: date) -> float:
        """Partner's age at month `index`."""
        dob = self.plan.partner.date_of_birth
        months = (today.year - dob.year) * 12 + (today.month - dob.month)
        return (months + index) / 12

    def _withdraw(self, need, cash, accounts, funds, age, cash_in=None, cash_out=None):
        """Fund a monthly deficit, returning any unmet shortfall.

        Verified order (notes/08): free cash above the buffer, then withdrawal
        portfolios in list order, then the buffer itself, and finally the
        overdraft down to a hard floor of `-credit_limit` (notes/04).

        Portfolio sales are grossed up for capital-gains tax (taxation.py); the
        reference charts the **gross** sale as income and the tax as its own
        expense row, so that is how both are recorded here.
        """
        plan = self.plan
        drawn = cash_in if cash_in is not None else {}
        taxes = cash_out if cash_out is not None else {}

        take = min(need, max(cash - plan.cash_buffer, 0.0))
        cash -= take
        need -= take
        from_cash = take

        tax_paid = 0.0

        def draw_portfolios(remaining):
            nonlocal tax_paid
            for index, (portfolio, account) in enumerate(zip(plan.portfolios, accounts)):
                if remaining <= 1e-9:
                    break
                if portfolio.designation != PortfolioDesignation.WITHDRAW:
                    continue
                net, tax = account.withdraw_net(
                    remaining, age=age,
                    statutory_age=national_insurance.STATUTORY_AGE[plan.person.gender])
                remaining -= net
                tax_paid += tax
                drawn[f"portfolio{index}"] = drawn.get(f"portfolio{index}", 0.0) + net + tax
                if tax:
                    taxes[f"capital_gains_tax{index}"] = (
                        taxes.get(f"capital_gains_tax{index}", 0.0) + tax)
            return remaining

        def draw_funds(remaining):
            for index, account in enumerate(funds):
                if remaining <= 1e-9:
                    break
                took = account.withdraw_net(remaining)
                remaining -= took
                drawn[f"keren{index}"] = drawn.get(f"keren{index}", 0.0) + took
            return remaining

        # `prati_hishtalmut_order` picks which bucket is emptied first.
        order = ((draw_funds, draw_portfolios) if plan.draw_keren_before_portfolio
                 else (draw_portfolios, draw_funds))
        for step in order:
            need = step(need)

        floor = -plan.credit_limit
        take = min(need, max(cash - floor, 0.0))
        cash -= take
        need -= take
        from_cash += take
        if from_cash:
            drawn["cash"] = drawn.get("cash", 0.0) + from_cash

        return cash, max(need, 0.0), tax_paid
