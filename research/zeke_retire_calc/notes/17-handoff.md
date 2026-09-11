# Handoff — continuing the clone with live access to the reference

You have the one thing the sessions before you did not: **a route to
zekestories.com**. Everything here is written on that assumption. If it turns
out you do not, stop and say so rather than working around it — three sessions
have now burned time rediscovering that a blocked egress proxy cannot be
argued with.

Check it first, and check it with the harness rather than a ping:

```bash
python -c "import sys; sys.path.insert(0,'research/zeke_retire_calc'); \
import zeke; s=zeke.Session().load(); print('csrf', s.token[:12], len(s.defaults), 'fields')"
```

A CSRF token and ~70 fields means you are live. A `ProxyError` or a 403 means
you are not.

## Where the clone stands

`notes/12-status.md` is the standing account and should stay current — update
it as you go, it is the file the next reader starts from. In one line: all 134
recorded runs replay the full 533-month horizon with **nothing fed in**, 115 of
them inside a tenth of a shekel on every series in every month, 126 inside 15
shekels, and the eight that miss are named and bounded in
`test_reference_parity.KNOWN_GAPS`.

Everything is measured, nothing is fitted at runtime. Do not add a constant
without an experiment behind it.

## The loop

1. **Probe.** `probe_open_questions.py` holds the sweep that was designed for
   exactly the two open questions (below). Add families to it rather than
   writing new one-off scripts.
2. **Compare.** Every probe is replayed as it lands and reports two numbers:
   the gap with nothing supplied, and the gap once that run's own decumulation
   rate is fitted. **The pair is the diagnostic.** A small second number beside
   a large first one means the model is right and only the rate it read is
   wrong — one scalar, a surface question. Both large means the model itself is
   off, and that is a different and more interesting bug.
3. **Hypothesise, then test against the whole corpus.** Every rule here was
   found by a fixture and killed by a different one. Before believing a rule,
   run the full parity suite — a change that fixes three runs and breaks twenty
   is the normal outcome of a first guess.
4. **Regenerate, in order** (see below).
5. **Re-verify and commit.** Small commits, each with the evidence in the
   message.

## Regeneration has a strict order, and it is a footgun

The measured artefacts depend on each other:

```
backend/services/fire/pension.py  ANNUITY_FACTORS
        |  (the fitted rates are computed with these)
        v
fit_decumulation.py        ->  decumulation_rates.json        (slow: 134 fits, tens of minutes)
        |
        v
build_decumulation_table.py ->  backend/services/fire/decumulation_table.json  (a couple of minutes)
```

and the factors themselves come from

```
measure_annuity_factors.py   # brackets each factor from the printed annuity
tune_annuity_factors.py      # picks the point inside the bracket that replays best (also slow)
```

**Change a factor and the rates and the table are both stale.** Re-run the
first pair after the second, always. This is the single easiest way to produce
a corpus that looks worse for no visible reason.

## Open question 1 — the gemel-conversion bridge

The big one: `pf_mukeret2`, `pf_mukeret3_t60`, `pf_mukeret4_order` miss by
15k-57k. All three, and only they, hold a gemel earmarked `mukeret_*`, which
converts to an annuity at 60. Given the right rate each replays to 1.5-2.8
shekels, so what is unexplained is **one scalar per run**.

`notes/15-the-bridge.md` has the full characterisation and **eight disproved
rules** — read it before forming a ninth. The sharpest constraint: every
annuity in `pf_mukeret3_t60` starts in the same month, so no weighting of any
subset of them can produce the rate it needs. Whatever is happening involves
something that is not in its annuity list.

**The experiment is already designed and pre-registered.** `gb_t60_*` pins the
retirement age, claims everything at 60, and varies nothing but the gemel
balance. Our rule therefore predicts the *same* rate for all five rungs (note
the trailing underscore — without it the prefix also catches `gb_t6067_*`):

```
python research/zeke_retire_calc/probe_open_questions.py --predict gb_t60_
# gb_t60_0k .. gb_t60_1600k   all 0.35056199
```

A rate that climbs with the balance settles it and measures the effect per
shekel; the script solves each rung for the surface value the gemel money must
carry. A rate that holds flat says the anomaly is not the gemel's weight at all
and `notes/15` needs reopening from a different angle.

## Open question 2 — one missing surface cell

`pn_annuity_6067` costs 260 shekels, and it is **not** a rule failure. It is
the only run that genuinely reads two bridges; its shorter one sits in the
collapsed stretch where the surface is 0.0002, so the blend reduces to the
longer stream's weight times `S(18)`. Solving gives `S(18) = 1.3462` against
the 1.3559 the table interpolates. Rule 85 is measured at 17.25 and 18.33 and
nowhere between, over a gap the curve climbs 26% across.

`br_age49` samples a bridge of 18.083, inside that gap. `br_age50` at 17.083 is
the consistency check — a measured cell sits a month away at 17.0, so a reading
far from 1.0968 means the surface is wrong in the whole stretch rather than
merely sparse.

Note the cell is deliberately **not** back-solved from the blend and added to
the table: every other cell is measured off a run reading one bridge, and
deriving this one from the rule would make the surface depend on the rule that
reads it.

## Gotchas that cost real time

- **Bridges are `X + 1/12`, never `X`.** An annuity starts the month *after*
  the claim birthday. Take bridges from `Simulator._streams`, never by asking
  which month the series first reaches the claim age — that lands one month
  early and moves a solved value in the third decimal. The cells sitting at
  round numbers came from `retire_asap` runs whose retirement month was not
  chosen by an age at all.
- **A high-residual fixture must not set a cell a clean fixture shares.**
  `build_decumulation_table.consensus()` drops a vote when another vote on the
  same cell replays an order of magnitude better. Two fixtures were being
  handed rates they could not replay before it existed.
- **`KNOWN_GAPS` has a hygiene test.** A gap that closes must be removed from
  the dict or `test_every_known_gap_is_still_needed` fails. That is deliberate:
  a stale bound hides a regression.
- **Targeted pytest needs `--no-cov`** or the repo's 40% gate fails the run.
  Full suite ~28 min; `tests/backend/unit/fire` alone ~5 min.
- **The parity suites cache their replays** (`lru_cache` on `_run` / `_replay`).
  Removing that took the suite from 7 minutes to 34.
- **Be polite to the reference.** It is a shared job queue with a `position`
  field; each probe costs a few seconds of someone else's server. Pace the
  sweep (the script sleeps between probes), keep it to what the question needs,
  and do not brute-force a parameter space.

## What "done" looks like

Bit-exact on every recorded run is the goal, but a bounded, *named*, tested
approximation is an acceptable resting place — that is what the eight entries
in `KNOWN_GAPS` are. If the probes show a rule is genuinely unrecoverable from
the observable surface, record the disproofs in `notes/15` the way the first
eight are recorded and bound it. Do not fit a fudge factor to make a number go
away; every constant in this engine can name the experiment that produced it,
and that property is worth more than the last few shekels.

## Still deferred

Wiring the calculator to the user's own tracked data. Deliberately postponed by
the user at the start of the project — it is the largest remaining piece of the
original goal and needs no network at all, so it is the right thing to pick up
if the reference turns out to be unreachable after all.
