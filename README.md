<div align="center">

# Finance Analysis

**The personal finance dashboard built for Israeli households.**

<p>
  <img alt="Auto-scraping" src="https://img.shields.io/badge/Auto--scraping_(18_providers)-5B21B6?style=flat-square" />
  <img alt="Auto-tagging" src="https://img.shields.io/badge/Auto--tagging-1E3A8A?style=flat-square" />
  <img alt="Monthly budgets" src="https://img.shields.io/badge/Monthly_budgets-1E3A8A?style=flat-square" />
  <img alt="Project budgets" src="https://img.shields.io/badge/Project_budgets-1E3A8A?style=flat-square" />
  <img alt="Investment tracking" src="https://img.shields.io/badge/Investment_tracking-166534?style=flat-square" />
  <img alt="FIRE calculator" src="https://img.shields.io/badge/FIRE_calculator-166534?style=flat-square" />
  <img alt="Liabilities" src="https://img.shields.io/badge/Liabilities-1E3A8A?style=flat-square" />
  <img alt="Split transactions" src="https://img.shields.io/badge/Split_transactions-1E3A8A?style=flat-square" />
  <img alt="Refund tracking" src="https://img.shields.io/badge/Refund_tracking-1E3A8A?style=flat-square" />
  <img alt="Hebrew / English" src="https://img.shields.io/badge/Hebrew_%2F_English-92400E?style=flat-square" />
</p>

<a href="https://github.com/tomerroditi/finance-analysis/releases/latest/download/FinanceAnalysis.dmg">
  <img alt="Download for macOS" src="https://img.shields.io/badge/⬇_Download_for_macOS-238636?style=for-the-badge" />
</a>
&nbsp;
<a href="https://github.com/tomerroditi/finance-analysis/releases/latest/download/FinanceAppInstaller.exe">
  <img alt="Download for Windows" src="https://img.shields.io/badge/⬇_Download_for_Windows-21262D?style=for-the-badge&labelColor=30363d" />
</a>

<p>or <a href="#build-from-source">build from source ↓</a></p>

<p>🌐 <strong><a href="https://finance-analysis-fawn.vercel.app">Live demo → finance-analysis-fawn.vercel.app</a></strong></p>

</div>

---

![Finance Analysis Dashboard](docs/screenshots/dashboard.png)

<p align="center"><em>Dashboard — net worth, budget overview, and recent transactions at a glance</em></p>

<br>

| Budget | Investments |
|--------|-------------|
| ![Budget](docs/screenshots/budget.png) | ![Investments](docs/screenshots/investments.png) |

---

## Build from source

```bash
# 1. Backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install poetry && poetry install --no-root

# 2. Frontend
cd frontend && npm install && cd ..

# 3. Run
poetry run uvicorn backend.main:app --reload   # http://localhost:8000
cd frontend && npm run dev                      # http://localhost:5173
```

> **Try demo mode first.** Toggle it in the sidebar to explore all features with sample data — the "Cohen family" — without connecting real accounts.

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + SQLAlchemy + SQLite + Pandas |
| Frontend | React 19 + Vite + TypeScript + Tailwind CSS 4 |
| Scraper | Playwright + httpx (18 Israeli providers) |
| State | TanStack Query + Zustand |
| Tests | pytest + vitest + Playwright e2e |
| Packaging | NSIS installer (Windows) · DMG (macOS) |

---

## Contributing

- Conventional Commits via Commitizen — `cz commit` is your friend
- PRs target `dev`, not `main`
- CI runs pytest + lint + build + vitest on every PR
- Read `.claude/rules/` before changing an architecture layer for the first time

Detailed architecture, conventions, and gotchas live in [`CLAUDE.md`](./CLAUDE.md) and `.claude/rules/`.
