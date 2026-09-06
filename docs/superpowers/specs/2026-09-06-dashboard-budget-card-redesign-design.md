# Dashboard Budget Card Redesign

**Date:** 2026-09-06
**Status:** Approved, ready for implementation planning

## Problem

The dashboard's budget card (`BudgetSpendingGauge` in
`frontend/src/components/dashboard/BudgetSection.tsx`) spends a 240px
`SemiGauge` plus a 24px margin — roughly 265px of a card capped at 39rem — to
say "66 ₪ of 12,000 ₪, 1% used". That is a large amount of space for a small
signal, and it crowds out the rule tiles, which are where the per-category
signal actually lives.

The card also exposes only two of the three budget kinds. `budget_rules`
discriminates monthly, yearly and project budgets via `period_type`, and the
Budget page has carried all three tabs since the yearly feature shipped, but
the dashboard card still toggles between Monthly and Projects only. Yearly
rules are invisible from the dashboard.

## Goals

1. Replace the gauge with a compact summary that says the same thing in ~70px.
2. Add a Yearly tab, bringing the card to parity with the Budget page.
3. Spend the reclaimed vertical space on rule tiles rather than on padding.
4. Leave `BudgetSection.tsx` in a shape a fourth tab would not make worse.

## Non-goals

- No backend change. Every endpoint this needs already exists.
- No change to the Budget page's own tabs or views, beyond extracting a shared
  sub-component out of `BudgetStatusBand`.
- No change to the dashboard grid, the card-size registry, or drag-to-reorder.

## Design

### Card structure

The shell (`BudgetSection.tsx`) is reduced to chrome plus tab routing:

```
<div className="… flex flex-col h-full">
  ── header ──  BUDGET eyebrow   ·   [ Monthly | Yearly | Projects ]
  {activeTab element}                     ← flex-1 flex flex-col min-h-0
</div>
```

Each tab element owns everything below the header:

```
nav row (period navigation / project selector)
BudgetTotalBar
rule grid            ← flex-1 min-h-[16rem] max-h-[16rem] lg:max-h-none, overflow-y-auto
"View All Budget Rules →"
```

…or, when the tab has no rules, its empty state in place of all four.

### Why flex-fill rather than a fixed tile height

The dashboard grid (`Dashboard.tsx:464`) sets `align-items: stretch` with
`[&>*]:h-full` and a `--dash-card-h: 39rem` cap. Two half cards sharing a row
render at the height of the taller one, and `dashboard-block-sizes.spec.ts:100`
asserts exactly that for `budget` and `recent`.

Consequently, shrinking the budget card's *content* on desktop does not shrink
the *card* — it leaves dead space at the bottom. Any hard-coded tile height
(the original "grow the box to 340px" idea) inherits that problem and is also a
magic number that drifts as the row-mate changes.

Making the tile grid `flex-1 min-h-[16rem] overflow-y-auto` inside a
`flex flex-col h-full` chain resolves both cases from one rule:

- **Desktop** — the card height is fixed by the row regardless, so the ~195px the
  gauge held beyond the new band's footprint lands in the tile grid
  automatically. More categories visible, no padding.
- **Mobile** — the grid is single-column with content-sized rows, so the card
  genuinely shrinks by ~195px. That is the compaction the redesign was asked
  for.

A `min-h-[16rem]` floor (about today's 4-tile height) keeps a short row from
crushing the grid.

**The mobile case needs a ceiling as well as a floor** (found in Task 4's
visual verification; the original reasoning below was incomplete). `Dashboard.tsx:471`
applies its `--dash-card-h` cap only at `lg:` — below that the comment at line
462 is explicit: "a single column with natural, uncapped heights". So the
card's flex parent has an *indefinite* height on mobile, where `flex-1` bounds
nothing and `min-h-[16rem]` is only a floor: the grid renders every tile and
the card grew to 968px with demo data, against ~684px before the redesign —
the opposite of the goal. The grid is therefore `max-h-[16rem] lg:max-h-none`:
pinned to the old four-tile scrolling box wherever the row height is
indefinite, flex-filling wherever it is definite. Measured after the fix: 486px
on mobile (vs ~684px before), 624px on desktop with a 374px grid (vs 260px).

The full chain must be unbroken: dashboard grid child (`h-full`, already
present) → `BudgetSection` root (`flex flex-col h-full`) → tab root
(`flex flex-1 flex-col min-h-0`) → grid (`flex-1 min-h-[16rem]`, plus the
`max-h-[16rem] lg:max-h-none` ceiling described above).
`Dashboard.tsx:470` also puts `overflow-y-auto` on the card root; with an inner
scroller that outer scroller should never engage, which is worth confirming
visually rather than assuming.

### Tab strip

Three real `<button>`s with `aria-pressed`, mirroring `Budget.tsx:29-55` —
same labels, same active styling (`bg-[var(--surface)] text-[var(--primary)]`),
minus the icons, which do not fit a half-width card.

Today's control is a single `<button>` wrapping two `<span>`s that flips on
click. That is replaced outright; it does not extend to three states, and it
was never correct as a control.

### Data

Each tab owns its own query. This removes both the `enabled: viewMode === …`
gating on every query and the `activeAnalysis` ternary chain: an unmounted tab
does not fetch.

| Tab | Query key | Totals | Grid rows |
|---|---|---|---|
| Monthly | `qk.budget.analysis(year, month, false)` | the `"Total Budget"` pseudo-rule | all other rules |
| Yearly | `qk.budget.yearly(year)` | `summary.total_spent` / `summary.total_allocated` | all rules |
| Projects | `qk.budget.projectDetails(name, false)` | the `"Total Budget"` pseudo-rule | all other rules |

The yearly row differs deliberately. `backend/services/budget/yearly.py:221`
computes `total_allocated` as a plain sum over the view and emits no
`Total Budget` pseudo-rule, so the yearly grid must **not** filter one out and
the yearly band must read the summary.

Yearly rules carry `tags: string[]`; monthly and project rules carry
`tags: string | null`. Each tab normalizes to the grid's single shape rather
than the grid branching on rule kind.

Period cursors — `{year, month}`, `yearCursor`, `selectedProject` — live in the
shell and are passed down, so switching tabs does not discard a month the user
had navigated to. This preserves today's behaviour across the monthly/projects
toggle.

The existing 11-month prefetch effect moves into `MonthlyBudgetTab`. Yearly
gets no prefetch; one year back or forward is a single request and the
speculative fetch is not worth it.

### Files

| Action | Path | Note |
|---|---|---|
| new | `frontend/src/components/common/BudgetTotalBar.tsx` | figure `/` total, remaining-or-over pill, thin bar, over/near thresholds |
| new | `frontend/src/components/dashboard/budget/MonthlyBudgetTab.tsx` | |
| new | `frontend/src/components/dashboard/budget/YearlyBudgetTab.tsx` | |
| new | `frontend/src/components/dashboard/budget/ProjectBudgetTab.tsx` | project logic moved verbatim |
| new | `frontend/src/components/dashboard/budget/BudgetRuleGrid.tsx` | extracted from `BudgetRuleCards` |
| mod | `frontend/src/components/budget/BudgetStatusBand.tsx` | left column renders `BudgetTotalBar` |
| mod | `frontend/src/components/dashboard/BudgetSection.tsx` | 425 lines → ~110 |
| del | `frontend/src/components/common/SemiGauge.tsx` | 113 lines; `BudgetSection` was its only consumer |

`BudgetTotalBar` is extracted so the dashboard card and `BudgetStatusBand`
cannot drift apart on the over/near/under thresholds or on the remaining-vs-over
pill wording. It lands in `common/` because it now has two consumers in
different feature folders.

### Internationalization

No new keys. Every string is already present in both `en.json` and `he.json`:
`budget.monthlyBudget`, `budget.yearly.tab`, `budget.projectBudgets`,
`budget.yearly.empty`, `budget.remainingAmount`, `budget.overByAmount`,
`dashboard.viewAllBudgetRules`, `dashboard.noBudgetRulesForMonth`,
`dashboard.noProjectBudgets`.

The yearly empty state reuses `budget.yearly.empty` with a link to `/budget`,
matching how the monthly empty state links to the same page.

The new year-nav chevrons need the same `isRtl` swap the month nav already
performs, and currency figures keep their `dir="ltr"` wrappers.

## Explicitly out of scope

- **No pace marker or months-elapsed stat.** Both offered variants were
  declined in favour of the plain mirror. The band has room if it is wanted
  later.
- **Tab selection is not persisted.** It resets to Monthly on reload.
- **The two amber thresholds are not unified.** Rule tiles turn amber at 75%,
  the total bar at 90%. This predates the change and is plausibly intentional —
  a single category nearing its cap deserves an earlier warning than the whole
  month does. `BudgetTotalBar` owns only the total-bar threshold; the tile
  threshold stays in `BudgetRuleGrid`.

## Testing

**Unit (vitest).** `BudgetTotalBar.test.tsx` covering under / near / over
thresholds, the remaining-vs-over pill, and the zero-budget-with-spend case
that today's `getProgressColor` special-cases (budget 0, spend > 0 must read as
fully over, not empty).

**e2e (Playwright).** Extend the existing journey test in `dashboard.spec.ts`
as a labeled block: all three tab labels present, click Yearly and assert its
content renders, click Projects. These are read-only checks, so per CLAUDE.md
they belong in the existing single-load journey rather than a new `test()`
paying another ~30 s dashboard boot. `dashboard.spec.ts` is not in
`READ_ONLY_SPECS`, so no parallel-safety constraint applies.

Note that `dashboard.spec.ts:51` currently locates the section via
`getByText(/Monthly Budget/i)` precisely because the "Budget" heading collides
with the sidebar nav link. That locator survives the redesign.

**Specs that must be run, not assumed:**

- `dashboard-block-sizes.spec.ts` — the equal-height and 39rem-cap assertions
  are the main risk in this change.
- `rtl-chevrons.spec.ts` — covers the new year-nav chevrons.
- `budget.spec.ts` and `yearly-budget.spec.ts` — `BudgetStatusBand` is being
  modified and both exercise it.

Plus the full pre-PR checklist from CLAUDE.md.

## Risks

1. **Equal-height assertion.** Flex-fill should satisfy
   `dashboard-block-sizes.spec.ts:100` by construction, but the interaction
   between the card's own `overflow-y-auto` (from `Dashboard.tsx:470`) and the
   inner scroller needs visual confirmation, not just a green assertion.
2. **`BudgetStatusBand` regression.** The extraction touches a component the
   Budget page's monthly, yearly and project views all render.
3. **Yearly totals.** Reading `summary` rather than a `Total Budget` rule is
   correct for yearly and wrong for the other two. Getting this backwards
   yields a silently wrong denominator rather than an error.
