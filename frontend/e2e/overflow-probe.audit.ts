/**
 * Focused diagnostic: find the exact element(s) causing horizontal overflow.
 *
 * Walks every element, skips anything inside an ancestor that legitimately
 * scrolls horizontally (`overflow-x: auto|scroll`), and reports the narrowest
 * offenders together with their ancestor chain so the culprit CSS is obvious.
 */
import { chromium, request } from "@playwright/test";

const API_BASE = process.env.E2E_API_BASE ?? "http://localhost:8000/api";
const BASE_URL = process.env.BASE_URL ?? "http://localhost:5173";
const TARGETS = (process.env.PROBE_PAGES ?? "/budget").split(",");

async function main() {
  const ctx = await request.newContext();
  await ctx.post(`${API_BASE}/testing/toggle_demo_mode`, { data: { enabled: true } });
  await ctx.dispose();

  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  });

  for (const lang of ["en", "he"]) {
    const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const page = await context.newPage();
    await page.addInitScript((l) => {
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
      localStorage.setItem("i18nextLng", l);
    }, lang);

    for (const target of TARGETS) {
      await page.goto(`${BASE_URL}${target}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(7000);

      const report = await page.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const docW = document.documentElement.scrollWidth;
        const offenders: string[] = [];

        const scrollsX = (el: Element) =>
          ["auto", "scroll"].includes(getComputedStyle(el).overflowX);

        // True if any ancestor is a horizontal scroll container — those are
        // intentional (wide tables), so their children aren't page offenders.
        const insideScroller = (el: Element) => {
          let p = el.parentElement;
          while (p && p !== document.body) {
            if (scrollsX(p)) return true;
            p = p.parentElement;
          }
          return false;
        };

        const describe = (el: Element) => {
          const e = el as HTMLElement;
          const cls = (e.className || "").toString();
          const tid = e.getAttribute("data-testid") || e.getAttribute("data-card-id") || "";
          return `<${e.tagName.toLowerCase()}${tid ? ` testid="${tid}"` : ""} class="${cls.slice(0, 140)}">`;
        };

        const chain = (el: Element) => {
          const out: string[] = [];
          let p: Element | null = el;
          let depth = 0;
          while (p && p !== document.body && depth < 5) {
            out.push(describe(p));
            p = p.parentElement;
            depth++;
          }
          return out;
        };

        for (const el of Array.from(document.body.querySelectorAll("*"))) {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          if (getComputedStyle(el).position === "fixed") continue;
          if (insideScroller(el)) continue;
          // An element that pushes past the viewport edge and is not itself
          // a scroll container is what actually widens the document.
          if (r.right > vw + 1 && !scrollsX(el)) {
            const txt = (el.textContent || "").trim().slice(0, 60);
            offenders.push(
              `right=${Math.round(r.right)} width=${Math.round(r.width)} left=${Math.round(r.left)}\n` +
                `      text: "${txt}"\n` +
                `      chain:\n        ${chain(el).join("\n        ")}`,
            );
          }
        }
        return { vw, docW, offenders };
      });

      console.log(`\n===== ${target} [${lang}] viewport=${report.vw} documentScrollWidth=${report.docW} =====`);
      if (report.docW <= report.vw + 1) {
        console.log("  no document-level horizontal overflow");
      }
      // Deepest offenders first — the innermost element is the true culprit.
      const uniq = [...new Set(report.offenders)];
      console.log(`  ${uniq.length} offending element(s); showing last 6 (deepest):`);
      for (const o of uniq.slice(-6)) console.log(`  - ${o}`);
    }
    await context.close();
  }
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
