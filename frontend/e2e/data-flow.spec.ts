import { test, expect } from "@playwright/test";

test.describe("DataFlow diagram", () => {
  test("hovering over diagram without clicking does not scroll it", async ({ page }) => {
    await page.goto("/data-flow");
    await page.waitForLoadState("networkidle");

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
    await page.waitForLoadState("networkidle");

    const container = page.locator('[class*="cursor-grab"]').first();
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

    // Clicking a node should open the detail panel
    const firstNode = page.locator('[class*="cursor-pointer"]').first();
    await firstNode.click();
    // Detail panel slides up from the bottom (fixed, z-[200], bottom-0)
    await expect(page.locator('.fixed.bottom-0[class*="z-\\[200\\]"]')).toBeVisible();
  });
});
