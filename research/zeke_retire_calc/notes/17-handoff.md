# Handoff — how to keep closing the gap

`notes/12-status.md` is the standing account of what matches and what does not;
`notes/18-bridge-rule.md` is the current account of the bridge and the surface.
This note is the working method.

## Check the route first

```bash
python -c "import sys; sys.path.insert(0,'research/zeke_retire_calc'); \
import zeke; s=zeke.Session().load(); print('csrf', s.token[:12], len(s.defaults), 'fields')"
```

A CSRF token and ~73 fields means you are live. A `ProxyError` or a 403 means
you are not — then work from the recorded corpus only.

## The tools

| file | what it does |
|---|---|
| `scenario.py` | builds a **complete** form payload from a structured description. Every row carries every field the reference's own add-row template has; a missing per-row field makes the reference answer `כשל בביצוע` with no charts. Never hand-write an overrides dict. |
| `experiments/<family>.py` | one module per question, exposing `SCENARIOS` (fixture name → payload). The docstring states the question and what each sub-family varies. |
| `lab.py <family>` | submits each scenario once (skips what is recorded), saves it as `fixtures/<name>.json.gz`, and immediately prints our relative error, worst gap, whether our solver lands on the reference's month, and with `--fit` the decumulation rate the run implies and the gap left once it is supplied. `--dry` judges what is on disk without the network. |
| `parity.py` | the one differ: every series in all three charts plus net worth, every month; relative error against the run's peak net worth. `python parity.py [prefixes] [-v] [--worst N]` over the whole corpus takes seconds (process pool). `parity.load/save/exists/corpus` are the only way fixtures are read or written. |
| `surface_read.py` | reads a surface cell straight off an idle-portfolio fixture. |
| `build_decumulation_table.py` | rebuilds `backend/services/fire/decumulation_table.json` from the `sf_*` / `sff_*` fixtures. |
| `measure_annuity_factors.py`, `tune_annuity_factors.py` | bracket and place the four annuity factors. |

## The loop

1. **Write the question as an experiment.** Hold everything inert that can be
   (a frozen pension: `pension(..., frozen=True)`; an idle 1e9 portfolio with
   20M of cash for surface work) and move one thing.
2. **`lab.py <family> --fit`.** The pair of numbers is the diagnostic: a small
   fitted gap beside a large derived one means the model is right and only the
   rate is wrong (a bridge question); both large means something else is off —
   `parity.py <name> -v` shows which series opens first.
3. **Invert, don't guess.** Turn a fitted rate into the horizon it was read at
   (invert the surface), and look for what that horizon depends on. Most rules
   in notes/18 fell out of tabulating horizons against candidate drivers.
4. **Fix, then `parity.py`** over the whole corpus — a rule that fixes three runs
   and breaks twenty is the normal first guess.
5. **Tests**: `tests/backend/unit/fire/test_corpus_parity.py` replays every
   fixture once. A new fixture is covered the moment it is recorded.

## Be a good citizen

The reference is a shared job queue (~2 s of server time per run). `lab.py`
runs one probe at a time with a pause and our own replay in between. Design the
family to answer its question; do not sweep a space you could reason about.

## What cost real time

- **`wanted_retire_age` must be a whole number**; the last working month is the
  one at exactly that age. Fractional bridges come only from `retire_asap` runs
  or from the post-60 rule (notes/18 §4), which `surface_fine` exploits.
- **A couple with `retire_at_age` crashes the reference** (`KeyError: 'age'` in
  `get_summary_text`). Probe couples with `retire_asap`.
- **The reference returns its Python traceback on a crash** — every frame's
  source line. It is the only view of the code there is.
- **A fixture's fitted rate is circular if the table was built from it.**
  Surface cells now come only from dedicated idle-portfolio probes.
- **Fixtures are gzipped** (`parity.save`): the corpus is ~1,900 runs.
