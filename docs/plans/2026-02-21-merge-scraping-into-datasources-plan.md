# Merge Scraping Into Data Sources — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move all scraping controls from the dashboard ScrapingWidget into the Data Sources page, with a "Scrape All" header button and per-card scrape/status/2FA UI.

**Architecture:** Extract scraping state management into a `useScraping` hook. Integrate the hook into `DataSources.tsx` — header gets Scrape All + timeframe dropdown, each card gets scrape button + inline status + inline 2FA. Remove ScrapingWidget from dashboard.

**Tech Stack:** React 19, TanStack Query, Zustand (not needed here), Lucide icons, Tailwind CSS 4

---

### Task 1: Create `useScraping` Hook

**Files:**
- Create: `frontend/src/hooks/useScraping.ts`

**Step 1: Create the hook file**

Extract all scraping state and logic from `ScrapingWidget.tsx` into a reusable hook. The hook manages running scrapers, polling, and mutations.

```typescript
import { useState, useEffect, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";

interface Account {
  service: string;
  provider: string;
  account_name: string;
}

interface ScraperState {
  process_id: number;
  account: Account;
  status: string; // 'in_progress', 'waiting_for_2fa', 'success', 'failed'
  last_updated: number;
  error_message?: string;
}

export function useScraping() {
  const queryClient = useQueryClient();
  const [runningScrapers, setRunningScrapers] = useState<
    Record<number, ScraperState>
  >({});

  // Start a single scraper
  const startScraper = useCallback(
    async (acc: Account, scrapingPeriodDays: number | null) => {
      try {
        const res = await scrapingApi.start({
          service: acc.service,
          provider: acc.provider,
          account: acc.account_name,
          ...(scrapingPeriodDays !== null && {
            scraping_period_days: scrapingPeriodDays,
          }),
        });
        const processId = res.data;
        setRunningScrapers((prev) => ({
          ...prev,
          [processId]: {
            process_id: processId,
            account: acc,
            status: "in_progress",
            last_updated: Date.now(),
          },
        }));
      } catch (e) {
        console.error("Failed to start scraper:", e);
      }
    },
    [],
  );

  // Start all accounts
  const scrapeAll = useCallback(
    (accounts: Account[], scrapingPeriodDays: number | null) => {
      accounts.forEach((acc) => startScraper(acc, scrapingPeriodDays));
    },
    [startScraper],
  );

  // 2FA mutation
  const tfaMutation = useMutation({
    mutationFn: ({
      service,
      provider,
      account,
      code,
    }: {
      service: string;
      provider: string;
      account: string;
      code: string;
    }) => scrapingApi.submit2fa(service, provider, account, code),
  });

  // Submit 2FA with optimistic update
  const submitTfa = useCallback(
    (scraper: ScraperState, code: string) => {
      setRunningScrapers((prev) => ({
        ...prev,
        [scraper.process_id]: {
          ...scraper,
          status: "in_progress",
          last_updated: Date.now(),
        },
      }));
      tfaMutation.mutate({
        service: scraper.account.service,
        provider: scraper.account.provider,
        account: scraper.account.account_name,
        code,
      });
    },
    [tfaMutation],
  );

  // Resend 2FA (abort + restart)
  const resendTfa = useCallback(
    async (scraper: ScraperState, scrapingPeriodDays: number | null) => {
      setRunningScrapers((prev) => {
        const newState = { ...prev };
        delete newState[scraper.process_id];
        return newState;
      });
      try {
        await scrapingApi.abort(scraper.process_id);
        startScraper(scraper.account, scrapingPeriodDays);
      } catch (e) {
        console.error("Failed to resend code:", e);
      }
    },
    [startScraper],
  );

  // Abort a scraper
  const abortScraper = useCallback(async (scraper: ScraperState) => {
    try {
      await scrapingApi.abort(scraper.process_id);
      setRunningScrapers((prev) => ({
        ...prev,
        [scraper.process_id]: {
          ...scraper,
          status: "failed",
          error_message: "Aborted by user",
          last_updated: Date.now(),
        },
      }));
    } catch (e) {
      console.error("Failed to abort:", e);
    }
  }, []);

  // Get scraper state for a specific account
  const getScraperForAccount = useCallback(
    (acc: Account): ScraperState | undefined => {
      return Object.values(runningScrapers)
        .filter(
          (s) =>
            s.account.service === acc.service &&
            s.account.provider === acc.provider &&
            s.account.account_name === acc.account_name,
        )
        .sort((a, b) => b.process_id - a.process_id)[0];
    },
    [runningScrapers],
  );

  // Check if any scraper is actively running
  const isAnyScraping = Object.values(runningScrapers).some(
    (s) => s.status === "in_progress" || s.status === "waiting_for_2fa",
  );

  // Polling effect
  useEffect(() => {
    const activeScrapers = Object.values(runningScrapers).filter(
      (s) => s.status === "in_progress" || s.status === "waiting_for_2fa",
    );
    if (activeScrapers.length === 0) return;

    const checkStatus = async () => {
      for (const scraper of activeScrapers) {
        try {
          const res = await scrapingApi.getStatus(scraper.process_id);
          const newStatus = res.data.status;
          const errorMessage = res.data.error_message;

          if (
            newStatus !== scraper.status ||
            Date.now() - scraper.last_updated > 5000
          ) {
            if (newStatus === "success" && scraper.status !== "success") {
              queryClient.invalidateQueries({ queryKey: ["last-scrapes"] });
              queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
            }
            setRunningScrapers((prev) => ({
              ...prev,
              [scraper.process_id]: {
                ...scraper,
                status: newStatus,
                error_message: errorMessage,
                last_updated: Date.now(),
              },
            }));
          }
        } catch (e) {
          console.error("Failed to check status for", scraper.process_id, e);
        }
      }
    };

    const interval = setInterval(checkStatus, 2000);
    return () => clearInterval(interval);
  }, [runningScrapers, queryClient]);

  return {
    startScraper,
    scrapeAll,
    submitTfa,
    resendTfa,
    abortScraper,
    getScraperForAccount,
    isAnyScraping,
    tfaIsPending: tfaMutation.isPending,
  };
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to `useScraping.ts`

**Step 3: Commit**

```bash
git add frontend/src/hooks/useScraping.ts
git commit -m "feat: extract useScraping hook from ScrapingWidget"
```

---

### Task 2: Integrate Scraping Into DataSources Page Header

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx` (lines 1-226, header area)

**Step 1: Add imports and hook usage**

Add new icon imports and wire up the `useScraping` hook plus scraping period state.

At the top of the file, add to lucide imports: `RefreshCw`, `PlayCircle`, `ChevronDown`, `Smartphone`, `XCircle`, `Info`, `CheckCircle2`, `Clock`

Add import: `import { useScraping } from "../hooks/useScraping";`

Inside the component, add:

```typescript
const {
  startScraper,
  scrapeAll,
  submitTfa,
  resendTfa,
  abortScraper,
  getScraperForAccount,
  isAnyScraping,
  tfaIsPending,
} = useScraping();

const [scrapingPeriodDays, setScrapingPeriodDays] = useState<number | null>(null);

const SCRAPING_PERIODS = [
  { label: "Auto", days: null },
  { label: "2 Weeks", days: 14 },
  { label: "1 Month", days: 30 },
  { label: "2 Months", days: 60 },
  { label: "3 Months", days: 90 },
  { label: "6 Months", days: 180 },
  { label: "12 Months", days: 365 },
] as const;
```

Also add helper functions (copied from ScrapingWidget):

```typescript
function formatRelativeDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
```

**Step 2: Update the header to include timeframe dropdown + Scrape All button**

Replace the header section (the `<div className="flex items-center justify-between">` block) with:

```tsx
<div className="flex items-center justify-between">
  <div>
    <h1 className="text-3xl font-bold">Data Sources</h1>
    <p className="text-[var(--text-muted)] mt-1">
      Securely manage your connected financial institutions and credentials
    </p>
  </div>
  <div className="flex items-center gap-3">
    {/* Scraping Period Selector */}
    <div className="relative">
      <select
        value={scrapingPeriodDays ?? "auto"}
        onChange={(e) =>
          setScrapingPeriodDays(
            e.target.value === "auto" ? null : Number(e.target.value),
          )
        }
        disabled={isAnyScraping}
        className="appearance-none bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl px-3 pr-7 py-2.5 text-xs font-bold text-white outline-none focus:border-[var(--primary)]/50 transition-colors disabled:opacity-50 cursor-pointer"
      >
        {SCRAPING_PERIODS.map((p) => (
          <option key={p.label} value={p.days ?? "auto"}>
            {p.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={12}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none"
      />
    </div>

    {/* Scrape All Button */}
    <button
      onClick={() => accounts && scrapeAll(accounts, scrapingPeriodDays)}
      disabled={isAnyScraping || !accounts?.length}
      className="flex items-center gap-2 px-5 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] text-white rounded-xl font-bold hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <RefreshCw size={16} className={isAnyScraping ? "animate-spin" : ""} />
      {isAnyScraping ? "Scraping..." : "Scrape All"}
    </button>

    {/* Connect Account Button */}
    <button
      onClick={() => setIsAddOpen(true)}
      className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20"
    >
      <Plus size={18} /> Connect Account
    </button>
  </div>
</div>
```

**Step 3: Verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/pages/DataSources.tsx
git commit -m "feat: add scrape all button and timeframe selector to data sources header"
```

---

### Task 3: Add Per-Card Scraping Status, Scrape Button, and 2FA UI

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx` (card rendering, lines ~248-409)

**Step 1: Add scraping status and controls to each card**

Inside the `accounts?.map()` loop, before the card JSX, compute the scraper state:

```tsx
const scraper = getScraperForAccount(acc);
const isActive = scraper && (scraper.status === "in_progress" || scraper.status === "waiting_for_2fa");
const lastScrape = lastScrapes?.find(
  (s: any) => s.service === acc.service && s.provider === acc.provider && s.account_name === acc.account_name,
);
```

Then modify the right side of the card (`<div className="flex items-center gap-4">`) to include a **status area** between the balance section and the action buttons:

```tsx
{/* Scraping Status */}
<div className="flex items-center gap-2 min-w-[100px] justify-end">
  {scraper?.status === "in_progress" && (
    <div className="flex items-center gap-1.5">
      <RefreshCw size={14} className="animate-spin text-blue-400" />
      <span className="text-xs font-semibold text-blue-400">Scraping...</span>
    </div>
  )}
  {scraper?.status === "waiting_for_2fa" && (
    <div className="flex items-center gap-1.5">
      <Smartphone size={14} className="text-amber-400 animate-pulse" />
      <span className="text-xs font-semibold text-amber-400">2FA Required</span>
    </div>
  )}
  {scraper?.status === "success" && (
    <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
      <CheckCircle2 size={12} className="text-emerald-400" />
      <span className="text-[10px] font-semibold text-emerald-400">Synced</span>
    </div>
  )}
  {scraper?.status === "failed" && (
    <div className="flex items-center gap-1.5">
      <span className="text-xs font-semibold text-red-400">Failed</span>
      {scraper.error_message && (
        <div className="relative group/err">
          <Info size={12} className="text-red-400 cursor-help" />
          <div className="absolute bottom-full right-0 mb-1 hidden group-hover/err:block z-50">
            <div className="bg-gray-900 text-white text-[10px] p-2 rounded shadow-lg max-w-[200px] whitespace-normal border border-gray-700">
              {scraper.error_message}
            </div>
          </div>
        </div>
      )}
    </div>
  )}
  {/* Show last sync time when no active scraper status */}
  {(!scraper || !["in_progress", "waiting_for_2fa", "success", "failed"].includes(scraper.status)) && (
    <>
      {!lastScrape?.last_scrape_date ? (
        <span className="text-[10px] text-[var(--text-muted)] italic">Never synced</span>
      ) : isScrapedToday(acc.provider, acc.account_name) ? (
        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
          <CheckCircle2 size={12} className="text-emerald-400" />
          <span className="text-[10px] font-semibold text-emerald-400">Synced</span>
        </div>
      ) : (
        <div className="flex items-center gap-1 text-[var(--text-muted)]">
          <Clock size={12} />
          <span className="text-[10px]">{formatRelativeDate(lastScrape.last_scrape_date)}</span>
        </div>
      )}
    </>
  )}
</div>
```

Add a **scrape/abort button** to the action buttons div (before the view button):

```tsx
{/* Scrape / Abort Button */}
{isActive ? (
  <button
    onClick={() => abortScraper(scraper!)}
    className="p-2.5 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-300 transition-all"
    title="Abort Scraping"
  >
    <XCircle size={20} />
  </button>
) : (
  <button
    onClick={() => startScraper(acc, scrapingPeriodDays)}
    disabled={isAnyScraping && !isActive}
    className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    title="Scrape This Source"
  >
    <PlayCircle size={20} />
  </button>
)}
```

**Step 2: Add inline 2FA UI that expands below the card**

When a scraper is waiting for 2FA, show an expandable section below the main card content. Wrap each card in a container and add the 2FA section conditionally. Each card needs its own `tfaCode` state — use a `Record<string, string>` state at the component level:

```typescript
const [tfaCodes, setTfaCodes] = useState<Record<string, string>>({});
```

After the main card row (the flex row with icon, name, balance, buttons), conditionally render the 2FA inline section:

```tsx
{scraper?.status === "waiting_for_2fa" && (
  <div className="mt-4 pt-4 border-t border-amber-500/20">
    <div className="flex items-center gap-3">
      <Smartphone className="text-amber-400 shrink-0" size={18} />
      <span className="text-xs text-amber-100/70">
        Enter 2FA code for <span className="text-white font-bold">{acc.provider}</span>
      </span>
      <div className="flex items-center gap-2 ml-auto">
        <input
          type="text"
          placeholder="Code"
          maxLength={10}
          className="w-28 bg-black/40 border border-amber-500/30 rounded-lg px-3 py-1.5 text-sm font-mono text-center outline-none focus:border-amber-400 text-white"
          value={tfaCodes[`${acc.service}_${acc.provider}_${acc.account_name}`] || ""}
          onChange={(e) =>
            setTfaCodes((prev) => ({
              ...prev,
              [`${acc.service}_${acc.provider}_${acc.account_name}`]: e.target.value,
            }))
          }
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const code = tfaCodes[`${acc.service}_${acc.provider}_${acc.account_name}`];
              if (code) {
                submitTfa(scraper, code);
                setTfaCodes((prev) => ({
                  ...prev,
                  [`${acc.service}_${acc.provider}_${acc.account_name}`]: "",
                }));
              }
            }
          }}
        />
        <button
          onClick={() => {
            const code = tfaCodes[`${acc.service}_${acc.provider}_${acc.account_name}`];
            if (code) {
              submitTfa(scraper, code);
              setTfaCodes((prev) => ({
                ...prev,
                [`${acc.service}_${acc.provider}_${acc.account_name}`]: "",
              }));
            }
          }}
          disabled={!tfaCodes[`${acc.service}_${acc.provider}_${acc.account_name}`] || tfaIsPending}
          className="px-3 py-1.5 rounded-lg bg-amber-500 text-black text-xs font-bold hover:bg-amber-400 transition-all disabled:opacity-50"
        >
          Verify
        </button>
        <button
          onClick={() => resendTfa(scraper, scrapingPeriodDays)}
          disabled={tfaIsPending}
          className="px-3 py-1.5 rounded-lg bg-white/10 text-white text-xs font-bold hover:bg-white/20 transition-all disabled:opacity-50"
        >
          Resend
        </button>
      </div>
    </div>
  </div>
)}
```

The card's outer div needs to change from `flex items-center justify-between` to a column layout when 2FA is active. Wrap the existing card content in an inner flex row:

```tsx
<div
  key={idx}
  className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-5 hover:border-[var(--primary)]/30 hover:shadow-xl transition-all"
>
  <div className="flex items-center justify-between">
    {/* ...existing left side (icon + name) and right side (balance + status + buttons)... */}
  </div>
  {/* 2FA inline section (conditional) */}
</div>
```

**Step 3: Verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/pages/DataSources.tsx
git commit -m "feat: add per-card scraping status, scrape button, and inline 2FA to data sources"
```

---

### Task 4: Remove ScrapingWidget From Dashboard

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` (lines 6, 250)
- Delete: `frontend/src/components/dashboard/ScrapingWidget.tsx`

**Step 1: Remove ScrapingWidget import and usage from Dashboard**

In `frontend/src/pages/Dashboard.tsx`:
- Remove line 6: `import { ScrapingWidget } from "../components/dashboard/ScrapingWidget";`
- Remove lines 249-251: the `<div><ScrapingWidget /></div>` wrapper

**Step 2: Delete ScrapingWidget file**

```bash
rm frontend/src/components/dashboard/ScrapingWidget.tsx
```

**Step 3: Verify no TypeScript errors and build succeeds**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

Run: `cd frontend && npm run build 2>&1 | tail -10`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git rm frontend/src/components/dashboard/ScrapingWidget.tsx
git commit -m "feat: remove ScrapingWidget from dashboard"
```

---

### Task 5: Visual QA and Polish

**Files:**
- Possibly modify: `frontend/src/pages/DataSources.tsx`

**Step 1: Start both servers and visually inspect**

Run: `python .claude/scripts/with_server.py -- sleep 120`

Navigate to `http://localhost:5173` → Data Sources page.

**Step 2: Verify the following in the browser:**

1. Header shows: `[Data Sources title] ... [Timeframe dropdown] [Scrape All] [Connect Account]`
2. Each card shows last sync status (e.g., "Synced", "3d ago", "Never synced")
3. Each card has scrape button (play icon) alongside view/edit/delete
4. Clicking "Scrape All" starts all accounts and shows spinner
5. Per-card scrape button starts individual scrape
6. 2FA-required accounts expand inline with code input
7. Abort button replaces play button during active scrape
8. Failed status shows with error tooltip
9. Dashboard no longer shows ScrapingWidget

**Step 3: Fix any visual issues found**

Adjust spacing, alignment, or styling as needed.

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: polish data sources scraping UI"
```
