/**
 * Programmatic responsive / RTL UI auditor.
 *
 * Drives every page across the four-cell matrix documented in
 * `.claude/rules/testing.md` (desktop|mobile x English|Hebrew) and reports
 * layout defects that static analysis cannot see:
 *
 *   - document-level horizontal overflow (the page scrolls sideways)
 *   - individual elements wider than the viewport
 *   - elements overflowing their own scroll container
 *   - untranslated i18n key leaks (e.g. "transactions.envelopeNamePlaceholder")
 *   - NaN in SVG path data (broken charts)
 *   - touch targets below the 24px minimum on mobile
 *
 * Run via the orchestrator so both servers are up:
 *   python .claude/scripts/with_server.py -- bash -c \
 *     "cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npx tsx e2e/ui-audit.audit.ts"
 *
 * This is a diagnostic tool, not a spec — it is deliberately excluded from
 * the Playwright suite (`.audit.ts`, not `.spec.ts`) so it never gates CI.
 */
import { chromium, type Page } from "@playwright/test";

const API_BASE = process.env.E2E_API_BASE ?? "http://localhost:8000/api";
const BASE_URL = process.env.BASE_URL ?? "http://localhost:5173";

const PAGES = [
  "/",
  "/transactions",
  "/budget",
  "/categories",
  "/investments",
  "/liabilities",
  "/insurances",
  "/early-retirement",
  "/data-sources",
  "/data-flow",
];

const CELLS = [
  { name: "desktop-en", width: 1440, height: 900, lang: "en" },
  { name: "desktop-he", width: 1440, height: 900, lang: "he" },
  { name: "mobile-en", width: 375, height: 812, lang: "en" },
  { name: "mobile-he", width: 375, height: 812, lang: "he" },
];

type Finding = {
  cell: string;
  page: string;
  kind: string;
  detail: string;
};

const findings: Finding[] = [];

function record(cell: string, page: string, kind: string, detail: string) {
  findings.push({ cell, page, kind, detail });
}

/** Collect layout defects from the live DOM. */
async function auditPage(page: Page, cell: string, path: string) {
  const result = await page.evaluate(() => {
    const out: { kind: string; detail: string }[] = [];
    const vw = document.documentElement.clientWidth;

    // 1. Document-level horizontal overflow.
    const scrollW = document.documentElement.scrollWidth;
    if (scrollW > vw + 1) {
      out.push({
        kind: "doc-overflow",
        detail: `document scrollWidth ${scrollW} > viewport ${vw} (+${scrollW - vw}px)`,
      });
    }

    const describe = (el: Element) => {
      const e = el as HTMLElement;
      const cls = (e.className || "").toString().slice(0, 80);
      const txt = (e.textContent || "").trim().slice(0, 40);
      const tid = e.getAttribute("data-testid") || e.getAttribute("data-card-id") || "";
      return `<${e.tagName.toLowerCase()}${tid ? ` testid=${tid}` : ""} class="${cls}">${txt ? ` "${txt}"` : ""}`;
    };

    const all = Array.from(document.body.querySelectorAll("*"));

    // 2. Elements wider than the viewport (the usual cause of doc overflow).
    for (const el of all) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const style = getComputedStyle(el);
      if (style.position === "fixed") continue;
      if (r.width > vw + 1) {
        // Ignore elements that are themselves horizontally scrollable —
        // those are intentional (wide tables in an overflow-x container).
        const parent = el.parentElement;
        const parentScrolls =
          parent &&
          ["auto", "scroll"].includes(getComputedStyle(parent).overflowX);
        if (!parentScrolls) {
          out.push({
            kind: "element-wider-than-viewport",
            detail: `${describe(el)} width=${Math.round(r.width)} vw=${vw}`,
          });
        }
      }
      // 3. Element visually escaping the right/left edge of the viewport.
      if (r.right > vw + 1 && r.left >= 0 && r.width < vw) {
        const parent = el.parentElement;
        const parentScrolls =
          parent &&
          ["auto", "scroll"].includes(getComputedStyle(parent).overflowX);
        if (!parentScrolls) {
          out.push({
            kind: "element-past-right-edge",
            detail: `${describe(el)} right=${Math.round(r.right)} vw=${vw}`,
          });
        }
      }
    }

    // 4. i18n key leaks — raw dotted keys rendered as visible text.
    const keyLeak = /^[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9_]*){1,}$/;
    for (const el of all) {
      if (el.children.length > 0) continue;
      const t = (el.textContent || "").trim();
      if (t.length > 3 && t.length < 60 && keyLeak.test(t)) {
        out.push({ kind: "i18n-key-leak", detail: `"${t}" in ${describe(el)}` });
      }
    }

    // 5. NaN in SVG geometry — a broken chart.
    for (const p of Array.from(document.querySelectorAll("path, line, rect, circle"))) {
      for (const attr of ["d", "x1", "x2", "y1", "y2", "x", "y", "cx", "cy", "r", "width", "height"]) {
        const v = p.getAttribute(attr);
        if (v && v.includes("NaN")) {
          out.push({ kind: "svg-nan", detail: `${p.tagName} ${attr}="${v.slice(0, 60)}"` });
          break;
        }
      }
    }

    return { out, vw };
  });

  for (const f of result.out) record(cell, path, f.kind, f.detail);

  // 6. Mobile touch-target sizes (interactive elements under 24px).
  if (cell.startsWith("mobile")) {
    const small = await page.evaluate(() => {
      const out: string[] = [];
      const els = Array.from(
        document.querySelectorAll("button, a, [role=button], input[type=checkbox]"),
      );
      for (const el of els) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (getComputedStyle(el).visibility === "hidden") continue;
        if (r.height < 24 || r.width < 24) {
          const e = el as HTMLElement;
          const label =
            e.getAttribute("aria-label") ||
            (e.textContent || "").trim().slice(0, 30) ||
            e.className.toString().slice(0, 40);
          out.push(`${Math.round(r.width)}x${Math.round(r.height)} "${label}"`);
        }
      }
      return out;
    });
    for (const s of small) record(cell, path, "small-touch-target", s);
  }
}

async function main() {
  // Enable demo mode so every page has data to lay out.
  const ctx = await (await import("@playwright/test")).request.newContext();
  await ctx.post(`${API_BASE}/testing/toggle_demo_mode`, { data: { enabled: true } });
  await ctx.dispose();

  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  });

  for (const cell of CELLS) {
    const context = await browser.newContext({
      viewport: { width: cell.width, height: cell.height },
    });
    const page = await context.newPage();
    await page.addInitScript((lang) => {
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
      localStorage.setItem("i18nextLng", lang);
    }, cell.lang);

    for (const path of PAGES) {
      try {
        await page.goto(`${BASE_URL}${path}`, { waitUntil: "domcontentloaded" });
        // Let charts/data settle; these pages are query-heavy on cold load.
        await page.waitForTimeout(6000);
        await auditPage(page, cell.name, path);
        process.stderr.write(`  ok ${cell.name} ${path}\n`);
      } catch (err) {
        record(cell.name, path, "navigation-error", String(err).slice(0, 200));
        process.stderr.write(`  ERR ${cell.name} ${path}: ${err}\n`);
      }
    }
    await context.close();
  }

  await browser.close();

  // --- Report, grouped and de-duplicated ---
  const grouped = new Map<string, Finding[]>();
  for (const f of findings) {
    const k = `${f.kind}`;
    if (!grouped.has(k)) grouped.set(k, []);
    grouped.get(k)!.push(f);
  }

  console.log("\n================ UI AUDIT REPORT ================\n");
  for (const [kind, items] of [...grouped.entries()].sort(
    (a, b) => b[1].length - a[1].length,
  )) {
    console.log(`### ${kind} — ${items.length} occurrence(s)`);
    const seen = new Set<string>();
    for (const it of items) {
      const key = `${it.cell}|${it.page}|${it.detail}`;
      if (seen.has(key)) continue;
      seen.add(key);
      console.log(`  [${it.cell}] ${it.page}\n      ${it.detail}`);
    }
    console.log("");
  }
  console.log(`TOTAL FINDINGS: ${findings.length}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
