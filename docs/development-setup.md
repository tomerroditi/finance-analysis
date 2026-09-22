# Development Setup

How to get the app running from source on **Windows** or **macOS**: a FastAPI backend on
<http://localhost:8000> and a Vite frontend on <http://localhost:5173>.

You need:

| Tool | Version | Why |
|------|---------|-----|
| Python | **3.12** exactly (`>=3.12,<3.13`) | backend |
| Node.js | current LTS (24.x) | frontend |
| Git | any recent | source, plus **Git Bash** on Windows to run `start.sh` |
| GitHub CLI (`gh`) | optional | PRs, CI status |

---

## 1. Install the tools

### Windows

From PowerShell:

```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12 --scope user
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id GitHub.cli
```

The Node.js installer asks for administrator rights; approve the UAC prompt.

**Then close and reopen every terminal and VS Code window.** Programs that were already
open keep the old `PATH` and won't find `python`, `node` or `npm`.

Run the project scripts from **Git Bash**, not PowerShell or cmd, because `start.sh` is a
bash script.

### macOS

With [Homebrew](https://brew.sh):

```bash
brew install python@3.12 node gh
```

Git ships with the Xcode Command Line Tools (`xcode-select --install`).

---

## 2. Install project dependencies

From the repo root (Git Bash on Windows, Terminal on macOS):

```bash
git clone https://github.com/tomerroditi/finance-analysis.git
cd finance-analysis

# Frontend
cd frontend && npm install && cd ..
```

You don't have to set up the backend by hand. The first `./start.sh` creates `.venv/` and
installs the Python dependencies (about 90 seconds, once). It re-syncs them whenever
`poetry.lock` changes. To set it up now without starting the servers:

```bash
./.claude/scripts/bootstrap_venv.sh
```

Scraping bank and credit-card accounts uses Playwright's Chromium. Install it once:

```bash
.venv/Scripts/python -m playwright install chromium   # Windows
.venv/bin/python -m playwright install chromium       # macOS
```

> **npm `allow-scripts` warning for `msw`:** newer npm versions skip package install
> scripts by default. `msw` is only used to mock requests in frontend unit tests, and the dev
> servers don't need it. If you run `npm test`, allow it with `npm approve-scripts msw`.

---

## 3. Run

```bash
./start.sh           # dev: backend :8000 (hot reload) + frontend :5173
./start.sh prod      # build the frontend and serve everything from the backend on :8080
```

Open <http://localhost:5173>. Press **Ctrl+C** to stop.

### Prod: phone access and auto-update

`./start.sh prod` is meant to be left running as your everyday copy of the app:

- **Tailnet access.** If Tailscale is connected, it runs `tailscale serve` for as long as
  the server is up and prints the URL (`https://<machine>.<tailnet>.ts.net`). Open it on
  any device signed in to your Tailscale account, such as your phone — no password or
  token: `tailscale serve` tells the backend which tailnet user is calling, and only the
  account that owns this machine is let in (`TAILNET_ALLOWED_USERS` overrides that, as
  a comma-separated list of logins). Other tailnet users and shared-in devices still need
  the API token. The server itself only listens on this machine, so nothing is exposed to
  your local network. `tailscale serve` is pointed at a loopback port of its own, and the
  tailnet identity is only believed there — so don't put another reverse proxy in front
  of it, and never forward the app with a raw TCP tunnel (`ssh -L`, socat,
  `tailscale serve --tcp`): those carry no proxy headers, so the backend would take
  every relayed client for a local one. Without tailnet
  HTTPS certificates (admin console → DNS → HTTPS Certificates) it shares over plain
  HTTP, which works but can't install the app as a PWA.
- **Auto-update.** Whenever the checked-out commit changes (you `git pull`), it
  rebuilds the frontend in the background, re-syncs dependencies if the lock files
  changed, and restarts the server (a couple of seconds of downtime). A failed build
  keeps the current version running. `PROD_AUTO_PULL=1` also makes it fast-forward from
  the upstream branch on every check — off by default, because it then runs whatever
  lands on that branch (including `npm ci` install scripts) unreviewed, on the machine
  that holds your bank passwords. It skips the pull while you have uncommitted changes
  or the branch has diverged. `PROD_POLL_SECONDS` changes the interval.
- **Self-healing.** It checks `/health` every 10 seconds and restarts the server if it
  crashes or stops answering three checks in a row, so an unreachable backend comes back
  on its own within about 30 seconds.

Turn on **Demo Mode** (in Settings) to explore the app with sample data, without connecting
real accounts.

Your real data lives in `~/.finance-analysis/` (`%USERPROFILE%\.finance-analysis\` on
Windows). The installed Windows app uses the same folder. The backend migrates the
database to the current schema on startup, so an older installed build may not open it
afterwards.

### From VS Code

**Run and Debug** offers *Dev (Backend + Frontend)* and
*Prod (Single Server + Tailscale, auto-update)*. The tasks behind them are in `.vscode/tasks.json`.

On Windows, VS Code runs tasks in PowerShell by default, which can't run `start.sh`.
Point it at Git Bash in `.vscode/settings.json`. That file is git-ignored, so each machine
keeps its own copy:

```json
{
  "terminal.integrated.defaultProfile.windows": "Git Bash",
  "terminal.integrated.automationProfile.windows": {
    "path": "C:\\Program Files\\Git\\bin\\bash.exe"
  }
}
```

---

## 4. GitHub CLI (optional)

```bash
gh auth login
```

Choose *GitHub.com → HTTPS → Login with a web browser*.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python` opens the Microsoft Store, or says "Python was not found" | That's the Windows Store alias. Install Python 3.12 as above, reopen the terminal, and optionally turn off the aliases in *Settings → Apps → Advanced app settings → App execution aliases*. |
| `node: command not found` / `npm: command not found` right after installing | The terminal or VS Code was open before the install. Restart it. |
| `[bootstrap] ERROR: python3.12 not found on PATH` | macOS: `brew install python@3.12`. Windows: install Python 3.12; the script finds it through the `py` launcher. |
| VS Code: *"The task … has not exited and doesn't have a 'problemMatcher' defined"* | Pull the latest `.vscode/tasks.json`. On Windows, also add the Git Bash settings above and restart VS Code. |
| `npm run backend` fails on Windows | npm runs its scripts through cmd.exe, which can't run the bash bootstrap. Use `./start.sh` or the VS Code *Backend* task instead. |
| Port already in use | Another run is still alive. On Windows, `taskkill /F /IM node.exe` or check `netstat -ano \| findstr :8000`. On macOS, `lsof -i :8000`. Or pick other ports: `BACKEND_PORT=8010 FRONTEND_PORT=5180 ./start.sh`. |
| Scraper fails with "Executable doesn't exist" | Install Playwright's Chromium (step 2). |

For tests and the pre-PR checklist, see [`CLAUDE.md`](../CLAUDE.md).
