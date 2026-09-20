import { test, expect } from "@playwright/test";

test.describe("DataFlow diagram", () => {
  test("hovering over diagram without clicking does not scroll it", async ({ page }) => {
    await page.goto("/data-flow");

    const container = page.locator('[class*="cursor-grab"]').first();
    await expect(container).toBeVisible();

    // Record scroll position before any mouse movement
    const scrollBefore = await container.evaluate((el) => ({
      left: el.scrollLeft,
      top: el.scrollTop,
    }));

    // Move the mouse across the diagram without clicking
    const box = await container.boundingBox();
    if (!box) throw new Error("container not found");
    await page.mouse.move(box.x + box.width * 0.25, box.y + box.height * 0.5);
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.5);

    const scrollAfter = await container.evaluate((el) => ({
      left: el.scrollLeft,
      top: el.scrollTop,
    }));

    // Diagram must not have scrolled from hover alone
    expect(scrollAfter.left).toBe(scrollBefore.left);
    expect(scrollAfter.top).toBe(scrollBefore.top);
  });

  test("diagram does not scroll after mouse button is released", async ({ page }) => {
    await page.goto("/data-flow");

    const container = page.locator('[class*="cursor-grab"]').first();
    await expect(container).toBeVisible();
    const box = await container.boundingBox();
    if (!box) throw new Error("container not found");

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;

    // Click and drag to pan
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    await page.mouse.move(cx - 30, cy - 15);
    await page.mouse.up();

    const scrollAfterDrag = await container.evaluate((el) => ({
      left: el.scrollLeft,
      top: el.scrollTop,
    }));

    // Move mouse further without button held — scroll must stay the same
    await page.mouse.move(cx + 60, cy + 30);
    await page.mouse.move(cx + 120, cy + 60);

    const scrollAfterHover = await container.evaluate((el) => ({
      left: el.scrollLeft,
      top: el.scrollTop,
    }));

    expect(scrollAfterHover.left).toBe(scrollAfterDrag.left);
    expect(scrollAfterHover.top).toBe(scrollAfterDrag.top);
  });

  test("diagram nodes are visible and clickable", async ({ page }) => {
    await page.goto("/data-flow");

    // Column headers should render
    await expect(page.getByText(/Data Sources/i).first()).toBeVisible();
    await expect(page.getByText(/Frontend/i).first()).toBeVisible();

    // Clicking a node should open the detail panel. The panel is always in
    // the DOM — closed it is merely translated off-screen — so `toBeVisible`
    // on it passes whether or not the click landed. Assert on its content
    // instead: `details[activeNode] ?? null` means a panel with a heading in
    // it is a panel that genuinely opened.
    const detailPanel = page.locator('.fixed.bottom-0[class*="z-\\[200\\]"]');
    const firstNode = page.locator('[class*="cursor-pointer"]').first();
    await firstNode.click();
    await expect(detailPanel.getByRole("heading").first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(detailPanel).toHaveClass(/translate-y-full/);

    // --- The subsystems the map has to account for ---------------------
    // A node whose content file is missing its entry renders its raw id as
    // the card title, which no type-check or build catches. Assert the
    // human labels of the newer subsystems, one per layer.
    for (const label of [
      "Bank of Israel", // sources
      "Keren Hishtalmut Sync", // processing
      "Savings Goal Tables", // storage
      "Credential Vault", // storage
      "Savings Goals", // management
      "Recurring Review", // management
      "Budget Month Override", // management
      "Cash-Flow Forecast", // analytics
      "Recurring Detection", // analytics
      "Insights", // analytics
      "PWA & Offline", // frontend
    ]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // --- A newer node's detail panel actually opens ---------------------
    // `details[activeNode] ?? null` leaves the panel closed when a node has
    // no detail entry, so clicking is the only way to know it has one.
    await page.getByText("Savings Goals Engine", { exact: true }).first().click();
    await expect(detailPanel.getByText("Surplus Waterfall")).toBeVisible();
    await expect(detailPanel.getByText("The Waterfall")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(detailPanel).toHaveClass(/translate-y-full/);

    // --- Panning still pans, and does not open whatever it ends on ------
    // Drag-to-pan only captures the pointer once the drag threshold is
    // passed, precisely so a plain click keeps reaching the node card. The
    // capture still has to happen, or a pan that leaves the viewport box
    // stops tracking, and it must not turn into a node click.
    const container = page.locator('[class*="cursor-grab"]').first();
    const box = await container.boundingBox();
    if (!box) throw new Error("container not found");
    const scrollBefore = await container.evaluate((el) => el.scrollTop);
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.8);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.5, box.y - 150, { steps: 12 });
    await page.mouse.up();
    await expect
      .poll(() => container.evaluate((el) => el.scrollTop))
      .not.toBe(scrollBefore);
    await expect(detailPanel).toHaveClass(/translate-y-full/);

    // --- Feature cards and callouts render below the diagram ------------
    await expect(page.getByText(/Recurring Charges, Confirmed By You/i)).toBeVisible();
    await expect(page.getByText(/Nothing is decided behind your back/i)).toBeVisible();
  });
});
