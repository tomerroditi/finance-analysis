import { test, expect, type Page } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * The dashboard's budget card, driven the way a phone user drives it.
 *
 * Six behaviours that only show up in a real browser: the tab strip has to
 * scroll on its own (the card sits in an `overflow-y-auto` grid cell, which
 * makes any horizontal overflow drag the whole card — figures and all —
 * sideways), the one-line rule rows have to survive a phone-width card
 * without wrapping or overflowing, the total bar's "spent / ceiling" pair has
 * to stay in one left-to-right run under RTL, "open budget" has to land on
 * the tab the card was showing, closing a project from the card has to reach
 * the backend, and a yearly rule's row has to expand into a panel whose
 * edit, close and delete all do.
 *
 * Its own file rather than a block in `dashboard.spec.ts`: it needs a mobile
 * viewport (set before the page boots), it navigates off the dashboard, and
 * the closing tests write.
 */
test.describe("dashboard budget card", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  const budgetCard = (page: Page) => page.locator('[data-card-id="budget"]');

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("the tabs scroll inside the card, and the card itself does not", async ({
      page,
    }) => {
      await navigateTo(page, "/");
      const card = budgetCard(page);
      await card.scrollIntoViewIfNeeded();
      const strip = card.getByTestId("dashboard-budget-tabs");
      await expect(strip).toBeVisible({ timeout: 30_000 });

      const geometry = await card.evaluate((el) => {
        const tabs = el.querySelector<HTMLElement>(
          '[data-testid="dashboard-budget-tabs"]',
        )!;
        return {
          cardOverflow: el.scrollWidth - el.clientWidth,
          stripOverflow: tabs.scrollWidth - tabs.clientWidth,
          stripWidth: tabs.clientWidth,
          cardWidth: el.clientWidth,
        };
      });

      // The four tabs don't fit a 390px card — that's the whole point of the
      // strip. They overflow it, not the card.
      expect(geometry.stripOverflow).toBeGreaterThan(0);
      expect(geometry.cardOverflow).toBe(0);
      expect(geometry.stripWidth).toBeLessThanOrEqual(geometry.cardWidth);

      // And the strip is genuinely scrollable: the last tab can be reached.
      const projectsTab = card.getByRole("button", {
        name: /Project Budgets/i,
      });
      await projectsTab.scrollIntoViewIfNeeded();
      await projectsTab.click();
      await expect(projectsTab).toHaveAttribute("aria-pressed", "true");

      // Rule rows: one line each, even at 390px. The row packs a name, a
      // bar and two figures onto a single line, so a phone is exactly where it
      // would wrap to two lines or push the card sideways.
      const monthlyTab = card.getByRole("button", { name: /Monthly Budget/i });
      await monthlyTab.scrollIntoViewIfNeeded();
      await monthlyTab.click();
      const rows = card.getByTestId("budget-rule-row");
      await expect(rows.first()).toBeVisible({ timeout: 30_000 });

      const rowGeometry = await card.evaluate((el) => {
        const list = [
          ...el.querySelectorAll<HTMLElement>(
            '[data-testid="budget-rule-row"]',
          ),
        ];
        return {
          count: list.length,
          maxHeight: Math.max(
            ...list.map((r) => r.getBoundingClientRect().height),
          ),
          maxOverflow: Math.max(
            ...list.map((r) => r.scrollWidth - r.clientWidth),
          ),
          cardOverflow: el.scrollWidth - el.clientWidth,
        };
      });

      // A phone's budget card shows a month's rules, not a handful: the
      // single-column line replaced a four-row tile precisely to fit them.
      expect(rowGeometry.count).toBeGreaterThanOrEqual(5);
      // Two lines of 10-12px text plus padding clears 44px; one does not.
      expect(rowGeometry.maxHeight).toBeLessThan(44);
      expect(rowGeometry.maxOverflow).toBe(0);
      expect(rowGeometry.cardOverflow).toBe(0);

      // The trailing figure keeps its word at every width — an unlabelled
      // number beside "spent / budget" is a guess. The percentage is what the
      // phone drops, since the bar already draws it.
      const firstRow = await rows.first().innerText();
      expect(firstRow).toMatch(/left|over/);
      expect(firstRow).not.toContain("%");
    });
  });

  // Hebrew gets its own boot: the language is read from localStorage before
  // the app mounts, and the document direction is the whole subject here.
  test("keeps the total bar's spent/ceiling pair in one left-to-right run under RTL", async ({
    page,
  }) => {
    await page.addInitScript(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const card = budgetCard(page);
    await card.scrollIntoViewIfNeeded();
    await card.getByRole("button", { name: /תקציב חודשי/ }).click();
    const bar = card.getByTestId("budget-total-bar");
    await expect(bar).toBeVisible({ timeout: 30_000 });

    // Read the line the way a person does: leaves sorted by where they paint.
    const painted = await bar.evaluate((el) =>
      [...el.querySelectorAll("span")]
        .filter((s) => s.children.length === 0 && s.textContent!.trim())
        .sort(
          (a, b) =>
            a.getBoundingClientRect().left - b.getBoundingClientRect().left,
        )
        .map((s) => s.textContent!.trim()),
    );

    const ceiling = painted.findIndex((t) => t.includes("/"));
    const pill = painted.findIndex((t) => /[\u0590-\u05FF]/.test(t));
    const spent = painted.findIndex((_t, i) => i !== ceiling && i !== pill);
    expect(spent).toBeGreaterThanOrEqual(0);
    expect(ceiling).toBeGreaterThanOrEqual(0);
    expect(pill).toBeGreaterThanOrEqual(0);

    // Spent sits left of the slash-and-ceiling. As two flex items the pair
    // was laid out in the container's RTL direction, so they swapped and the
    // slash landed at the far left of the line, divorced from both figures
    // ("/ 28,000 ₪ … 11,185"). Geometry is the only way to catch it — the DOM
    // order is identical either way.
    expect(ceiling).toBeGreaterThan(spent);
    // The remainder pill is a sibling of the pair, so RTL puts it outside,
    // to the pair's left — never between the two figures.
    expect(pill).toBeLessThan(spent);

    // The Overview tab's headline is the same shape and had the same bug.
    // Checked on this load rather than in its own test: it is one more tab
    // click, against a card that is already booted in Hebrew.
    await card.getByRole("button", { name: /^סקירה$/ }).click();
    const headline = card.getByTestId("overview-headline");
    await expect(headline).toBeVisible({ timeout: 30_000 });

    const headlineParts = await headline.evaluate((el) =>
      [...el.querySelectorAll("span")]
        .filter((s) => s.children.length === 0 && s.textContent!.trim())
        .sort(
          (a, b) =>
            a.getBoundingClientRect().left - b.getBoundingClientRect().left,
        )
        .map((s) => s.textContent!.trim()),
    );
    expect(headlineParts).toHaveLength(2);
    // Spend first, then the slash and the ceiling — mirrored, the slash sat
    // at the line's left edge, next to the pill instead of between figures.
    expect(headlineParts[1]).toContain("/");
    expect(headlineParts[0]).not.toContain("/");
  });

  // Both halves boot the same English desktop dashboard, so they share one
  // load: the project round trip stays on the dashboard, then "open budget"
  // navigates away.
  test("closes and reopens a project in place, and 'open budget' lands on the card's tab", async ({
    page,
  }) => {
    await navigateTo(page, "/");
    const card = budgetCard(page);
    await card.scrollIntoViewIfNeeded();

    // --- Closing a project from the card reaches the backend ---
    await card.getByRole("button", { name: /Project Budgets/i }).click();
    const toggle = card.getByTestId("card-project-closed-toggle");
    await expect(toggle).toBeVisible({ timeout: 30_000 });
    await expect(toggle).toHaveAttribute("aria-label", /close project/i);

    await toggle.click();
    const dialog = page.locator("div.modal-overlay", {
      hasText: /stops appearing in the budget overview/i,
    });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^Close project$/i }).click();

    // The card keeps the project — closing is not a delete — and says why it
    // left the Overview.
    await expect(card.getByTestId("card-project-closed-notice")).toBeVisible({
      timeout: 15_000,
    });
    await expect(toggle).toHaveAttribute("aria-label", /reopen project/i);

    // Reopening is a plain undo, with no confirmation step.
    await toggle.click();
    await expect(card.getByTestId("card-project-closed-notice")).toBeHidden({
      timeout: 15_000,
    });
    await expect(toggle).toHaveAttribute("aria-label", /close project/i);

    // --- 'Open budget' lands on the tab the card was showing ---
    await card.getByRole("button", { name: /Monthly Budget/i }).click();
    await expect(card.getByTestId("budget-total-bar")).toBeVisible({
      timeout: 30_000,
    });

    // Desktop keeps the percentage the phone drops, as a muted suffix on the
    // remainder rather than the pill the four-row tile used to carry.
    const firstRow = card.getByTestId("budget-rule-row").first();
    await expect(firstRow).toBeVisible({ timeout: 30_000 });
    await expect(firstRow).toContainText("%");
    await expect(firstRow).toContainText(/left|over/);

    await card.getByRole("link", { name: /View All Budget Rules/i }).click();

    await expect(page).toHaveURL(/\/budget\?tab=monthly/);
    // The page's own tab group: the Monthly tab is the pressed one, not the
    // Overview it used to fall back to.
    const pageTabs = page.getByRole("button", { name: /Monthly Budget/i });
    await expect(pageTabs.first()).toHaveAttribute("aria-pressed", "true", {
      timeout: 30_000,
    });

    // Yearly takes the same route, and carries its own year cursor.
    await page.goBack();
    await card.scrollIntoViewIfNeeded();
    await card.getByRole("button", { name: /^Yearly$/i }).click();
    const yearlyLink = card.getByRole("link").last();
    await expect(yearlyLink).toBeVisible({ timeout: 30_000 });
    await yearlyLink.click();
    await expect(page).toHaveURL(
      new RegExp(`/budget\\?tab=yearly&year=${new Date().getFullYear()}`),
    );
    await expect(
      page.getByRole("button", { name: /^Yearly$/i }).first(),
    ).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
  });

  test("edits, closes and reopens a yearly rule from its row panel", async ({
    page,
  }) => {
    const year = new Date().getFullYear();
    const ruleName = `E2E Card Close ${Date.now()}`;

    // Its own rule on a category no budget rule of any kind claims: the
    // yearly/project category exclusion would reject anything already taken,
    // and a demo rule would make the assertions depend on the seed data.
    const [rulesRes, categoriesRes] = await Promise.all([
      page.request.get(`${API_BASE}/budget/rules`, {
        headers: { "X-FAD-Demo": "1" },
      }),
      page.request.get(`${API_BASE}/tagging/categories`, {
        headers: { "X-FAD-Demo": "1" },
      }),
    ]);
    const claimed = new Set(
      (await rulesRes.json()).map((r: { category: string }) => r.category),
    );
    const categoriesMap: Record<string, string[]> = await categoriesRes.json();
    // Two rules, not one: the column-alignment guard below needs a collapsed
    // sibling to measure the expanded row against, and the demo data carries
    // no yearly rule of its own for the current year.
    const freeCategories = Object.entries(categoriesMap)
      .filter(([name, tags]) => !claimed.has(name) && tags.length > 0)
      .slice(0, 2);
    expect(
      freeCategories.length,
      "expected two categories with no budget rule of any kind",
    ).toBe(2);

    // A name that does not contain `ruleName`: the row locator filters by
    // text, and a superstring would make it match two rows.
    const siblingName = `E2E Card Sibling ${Date.now()}`;
    for (const [name, [category, tags]] of [
      [ruleName, freeCategories[0]],
      [siblingName, freeCategories[1]],
    ] as [string, [string, string[]]][]) {
      const created = await page.request.post(
        `${API_BASE}/budget/yearly/rules`,
        {
          headers: { "X-FAD-Demo": "1" },
          data: { name, amount: 12000, category, tags, year },
        },
      );
      expect(created.ok()).toBeTruthy();
    }

    const analysisUrl = `${API_BASE}/budget/yearly/${year}/analysis`;
    const readAnalysis = async () =>
      (await (
        await page.request.get(analysisUrl, { headers: { "X-FAD-Demo": "1" } })
      ).json()) as {
        rules: {
          rule: { id: number; name: string; amount: number };
          closed: boolean;
        }[];
      };
    const ruleId = (await readAnalysis()).rules.find(
      (r) => r.rule.name === ruleName,
    )!.rule.id;

    await navigateTo(page, "/");
    const card = budgetCard(page);
    await card.scrollIntoViewIfNeeded();
    await card.getByRole("button", { name: /^Yearly$/i }).click();

    const row = card
      .getByTestId("budget-rule-row")
      .filter({ hasText: ruleName });
    await expect(row).toBeVisible({ timeout: 30_000 });

    // The actions are behind the row, not permanently in it — the line is
    // already four cells wide at 390px.
    const panel = card.getByTestId(`card-rule-actions-${ruleId}`);
    await expect(panel).toBeHidden();
    await expect(row).toHaveAttribute("aria-expanded", "false");
    await row.click();
    await expect(panel).toBeVisible();
    await expect(row).toHaveAttribute("aria-expanded", "true");

    // A second tap on the row is what dismisses it.
    await row.click();
    await expect(panel).toBeHidden();
    await row.click();
    await expect(panel).toBeVisible();

    // The expanded row keeps the subgrid's columns. Rendering it as a real
    // `<button>` silently broke this: Chromium wraps a button's children in
    // an anonymous box, `grid-cols-subgrid` never reached them, and the open
    // row sized its own columns — its bar collapsed to a dot and its figures
    // drifted right of every collapsed sibling. Only geometry catches it;
    // the DOM is identical either way.
    const columnLefts = await card.evaluate((el) => {
      const rows = [
        ...el.querySelectorAll<HTMLElement>('[data-testid="budget-rule-row"]'),
      ];
      const cellLefts = (r: HTMLElement) =>
        [...r.children].map((c) => Math.round(c.getBoundingClientRect().left));
      return {
        expanded: cellLefts(
          rows.find((r) => r.getAttribute("aria-expanded") === "true")!,
        ),
        collapsed: rows
          .filter((r) => r.getAttribute("aria-expanded") === "false")
          .map(cellLefts),
      };
    });
    expect(columnLefts.collapsed.length).toBeGreaterThan(0);
    for (const row of columnLefts.collapsed) {
      expect(row).toEqual(columnLefts.expanded);
    }

    // ---- Edit: the panel opens the same modal the Budget page uses. ----
    await panel.getByTestId(`card-rule-edit-${ruleId}`).click();
    const editDialog = page.getByRole("dialog");
    await expect(editDialog).toBeVisible();
    await editDialog.getByRole("textbox").first().fill(`${ruleName} v2`);
    await editDialog.getByRole("button", { name: /^save$/i }).click();
    await expect(editDialog).toBeHidden({ timeout: 15_000 });
    await expect(
      card.getByTestId("budget-rule-row").filter({ hasText: `${ruleName} v2` }),
    ).toBeVisible({ timeout: 15_000 });
    expect(
      (await readAnalysis()).rules.find((r) => r.rule.id === ruleId)!.rule.name,
    ).toBe(`${ruleName} v2`);

    // ---- Close: asks first, then keeps the row and marks it. ----
    // The panel is keyed by the rule, not by what the row says, so it rides
    // the rename and the refetch that followed the save — an action does not
    // dismiss it, only another tap does.
    const renamedRow = card
      .getByTestId("budget-rule-row")
      .filter({ hasText: `${ruleName} v2` });
    await expect(panel).toBeVisible();
    await panel.getByTestId(`card-rule-closed-toggle-${ruleId}`).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(`${ruleName} v2`);
    await dialog.getByRole("button", { name: /^Close rule$/i }).click();

    // The card keeps the row — closing is not a delete — and its allocation
    // survives.
    await expect(renamedRow).toHaveAttribute("data-closed", "true", {
      timeout: 15_000,
    });
    await expect(renamedRow).toContainText("12,000");
    expect(
      (await readAnalysis()).rules.find((r) => r.rule.id === ruleId)!.closed,
    ).toBe(true);

    // ---- Reopen: a plain undo, with no confirmation step. ----
    // Still the same open panel: closing a rule sinks its row to the
    // bottom of the list, and the undo travels with it.
    await expect(
      panel.getByTestId(`card-rule-closed-toggle-${ruleId}`),
    ).toHaveAttribute("aria-label", /reopen rule/i, { timeout: 15_000 });
    await panel.getByTestId(`card-rule-closed-toggle-${ruleId}`).click();
    await expect(renamedRow).not.toHaveAttribute("data-closed", "true", {
      timeout: 15_000,
    });

    // ---- Delete: destructive, confirmed, and the row goes for good. ----
    await panel.getByTestId(`card-rule-delete-${ruleId}`).click();
    const deleteDialog = page.getByRole("alertdialog");
    await expect(deleteDialog).toBeVisible();
    await deleteDialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(renamedRow).toHaveCount(0, { timeout: 15_000 });
    // And the panel goes with it, rather than stranding an id no row can close.
    await expect(panel).toHaveCount(0);
    expect(
      (await readAnalysis()).rules.find((r) => r.rule.id === ruleId),
    ).toBeUndefined();

    const siblingId = (await readAnalysis()).rules.find(
      (r) => r.rule.name === siblingName,
    )?.rule.id;
    if (siblingId !== undefined) {
      await page.request.delete(
        `${API_BASE}/budget/yearly/rules/${siblingId}`,
        { headers: { "X-FAD-Demo": "1" } },
      );
    }
  });
});
