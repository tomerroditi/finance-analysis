# research/

Evidence for reverse-engineered models. Not application code, and nothing here
is imported by the running app — but the fixtures **are** loaded by tests, so
this directory has to ship.

## `zeke_retire_calc/`

The complete record of reverse-engineering the zekestories early-retirement
calculator, which `backend/services/fire/` reproduces.

| | |
|---|---|
| `notes/` | 14 evidence notes. Every rule in the engine is derived here, with the numbers that prove it. **Read these before changing any constant in `backend/services/fire/`.** |
| `fixtures/` | 140 recorded runs of the reference calculator — the input payload and its full monthly output series. The parity tests in `tests/backend/unit/fire/` replay these. |
| `zeke.py`, `probe.py`, `extract.py` | Harness: submit a scenario, poll the job, pull the monthly series out of the returned page. |
| `mk.py`, `pf.py` | Builders for multi-row scenarios (extra income/expense rows, multiple portfolios). |
| `validate.py`, `compare.py` | Replay our engine against a fixture and report the worst per-series deviation. |
| `check_solver.py` | Checks our solver picks the same retirement month the reference published, across every applicable fixture. |
| `fit_decumulation.py` | Solves for the one quantity that could not be derived, per fixture. Writes `decumulation_rates.json`, which the parity tests use as a known constant. |
| `probe_trinity.py` | Measures that quantity directly on a grid. Produced `trinity_table.json`, shipped as `backend/services/fire/decumulation_table.json`. |

The fixtures are stored minified — they are read by tests, never diffed by
hand. Regenerating any of them re-queries a third-party server, so treat them
as the durable record and don't delete them casually.

The methodology generalises; it is written up as the
`black-box-model-extraction` skill.
