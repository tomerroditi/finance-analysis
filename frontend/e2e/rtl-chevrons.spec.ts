import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

test.describe("RTL chevrons", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test.afterEach(async ({ page }) => {
    if (page.url().startsWith("http")) {
      await page.evaluate(() => localStorage.setItem("language", "en"));
    }
  });

  test("flips pagination chevron icons in Hebrew so arrows point the way the user navigates", async ({
    page,
  }) => {
    await navigateTo(page, "/transactions");
    await page.evaluate(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/transactions");

    await expect(page.getByText(/עמוד\s+\d+\s+מתוך/)).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const icons = await page.evaluate(() => {
      const pageSpan = Array.from(
        document.querySelectorAll("span.px-4.text-sm.whitespace-nowrap"),
      ).find((s) => /עמוד/.test(s.textContent ?? ""));
      if (!pageSpan) return null;
      const btns = Array.from(
        pageSpan.parentElement!.querySelectorAll("button"),
      );
      return btns.map((b) => {
        const svg = b.querySelector("svg");
        return svg ? svg.getAttribute("class") ?? "" : "";
      });
    });

    expect(icons).not.toBeNull();
    expect(icons!).toHaveLength(4);
    expect(icons![0]).toContain("lucide-chevrons-right");
    expect(icons![1]).toContain("lucide-chevron-right");
    expect(icons![1]).not.toContain("lucide-chevrons");
    expect(icons![2]).toContain("lucide-chevron-left");
    expect(icons![2]).not.toContain("lucide-chevrons");
    expect(icons![3]).toContain("lucide-chevrons-left");
  });

  test("Hebrew next-page button (chevron-left) advances the page", async ({ page }) => {
    await navigateTo(page, "/transactions");
    await page.evaluate(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/transactions");

    await expect(page.getByText("עמוד 1 מתוך", { exact: false })).toBeVisible({ timeout: 30_000 });

    const nextBtn = page
      .locator("span.px-4.text-sm.whitespace-nowrap", { hasText: /עמוד/ })
      .locator("..")
      .locator("button")
      .nth(2);
    await nextBtn.click();

    await expect(page.getByText("עמוד 2 מתוך", { exact: false })).toBeVisible();
  });

  test("English pagination still uses LTR chevrons", async ({ page }) => {
    await navigateTo(page, "/transactions");
    await page.evaluate(() => localStorage.setItem("language", "en"));
    await navigateTo(page, "/transactions");

    await expect(page.getByText(/Page\s+\d+\s+of/)).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");

    const icons = await page.evaluate(() => {
      const pageSpan = Array.from(
        document.querySelectorAll("span.px-4.text-sm.whitespace-nowrap"),
      ).find((s) => /Page/.test(s.textContent ?? ""));
      if (!pageSpan) return null;
      const btns = Array.from(
        pageSpan.parentElement!.querySelectorAll("button"),
      );
      return btns.map((b) => {
        const svg = b.querySelector("svg");
        return svg ? svg.getAttribute("class") ?? "" : "";
      });
    });

    expect(icons).not.toBeNull();
    expect(icons!).toHaveLength(4);
    expect(icons![0]).toContain("lucide-chevrons-left");
    expect(icons![1]).toContain("lucide-chevron-left");
    expect(icons![1]).not.toContain("lucide-chevrons");
    expect(icons![2]).toContain("lucide-chevron-right");
    expect(icons![2]).not.toContain("lucide-chevrons");
    expect(icons![3]).toContain("lucide-chevrons-right");
  });

  test("dashboard monthly-budget month switcher flips chevrons in Hebrew", async ({ page }) => {
    await navigateTo(page, "/");
    await page.evaluate(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/");

    const monthLabel = page.locator("p.w-36").first();
    await expect(monthLabel).toBeVisible({ timeout: 30_000 });

    const icons = await page.evaluate(() => {
      const label = document.querySelector("p.w-36");
      if (!label || !label.parentElement) return null;
      return Array.from(label.parentElement.querySelectorAll("button")).map(
        (b) => b.querySelector("svg")?.getAttribute("class") ?? "",
      );
    });

    expect(icons).not.toBeNull();
    expect(icons!).toHaveLength(2);
    // Previous month button (DOM-first) sits visually on the right in RTL — chevron-right.
    expect(icons![0]).toContain("lucide-chevron-right");
    // Next month button sits visually on the left in RTL — chevron-left.
    expect(icons![1]).toContain("lucide-chevron-left");
  });

  test("AutoTaggingPanel flips its chevron in Hebrew", async ({ page }) => {
    await navigateTo(page, "/transactions");
    await page.evaluate(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/transactions");

    const panel = page.locator('[class*="sticky top-4"]').first();
    await expect(panel).toBeVisible({ timeout: 30_000 });

    const state = await page.evaluate(() => {
      const p = document.querySelector('[class*="sticky top-4"]') as HTMLElement | null;
      if (!p) return null;
      const collapsed = p.getBoundingClientRect().width < 100;
      return {
        collapsed,
        icon: p.querySelector("svg")?.getAttribute("class") ?? "",
      };
    });

    expect(state).not.toBeNull();
    if (state!.collapsed) {
      // Collapsed strip on the LEFT in RTL — chevron points right (toward content area).
      expect(state!.icon).toContain("lucide-chevron-right");
    } else {
      // Open panel on the LEFT in RTL — chevron points left (collapse back to the wall).
      expect(state!.icon).toContain("lucide-chevron-left");
    }
  });

  test("DataSources connect-account flow flips proceed chevrons in Hebrew", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.evaluate(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/data-sources");

    await page.getByRole("button", { name: "חבר חשבון" }).click();

    // The three service-type buttons each carry a "proceed forward" chevron at
    // the end of the row. (Each button also contains an unrelated category
    // icon — Landmark / CreditCard / Shield — so we must pick the chevron
    // specifically, not the first SVG.)
    const proceedIcons = await page.evaluate(() => {
      const labels = ["חשבון בנק", "כרטיס אשראי", "ביטוח"];
      return labels.map((label) => {
        const heading = Array.from(document.querySelectorAll("p")).find(
          (p) => p.textContent?.trim() === label,
        );
        if (!heading) return null;
        const btn = heading.closest("button");
        if (!btn) return null;
        const chevron = btn.querySelector(
          "svg.lucide-chevron-left, svg.lucide-chevron-right",
        );
        return chevron?.getAttribute("class") ?? "";
      });
    });

    expect(proceedIcons).toHaveLength(3);
    for (const icon of proceedIcons) {
      expect(icon).not.toBeNull();
      expect(icon!).toContain("lucide-chevron-left");
    }
  });
});
