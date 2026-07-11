import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Regression coverage for the dashboard "recent transactions" inline
 * category/tag editor when the user creates a brand-new category or tag:
 *
 *  Bug #1 — the option list must stay alphabetically sorted, so a freshly
 *           created category/tag lands in its sorted position instead of
 *           being appended at the bottom (backend insert order).
 *  Bug #2 — the select box must be filled with the value the user just
 *           created, instead of falling back to the placeholder.
 *
 * Both are fixed centrally (sorting in `useCategories`, value-fill in the
 * section's `onCreateNew` handlers), but this drives the real user flow.
 */
test.describe("Recent transactions — inline create category/tag", () => {
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

  test("creating a category/tag fills the select and keeps options sorted", async ({
    page,
  }) => {
    await navigateTo(page, "/");

    // Open the inline category/tag editor on the first recent transaction.
    const editButton = page
      .getByRole("button", { name: "Edit category / tag" })
      .first();
    await expect(editButton).toBeVisible({ timeout: 15_000 });
    await editButton.click();

    // The editor panel is the flex row that hosts the "Done" button; the two
    // SelectDropdown triggers are the first two buttons inside it.
    const doneButton = page.getByRole("button", { name: "Done" });
    await expect(doneButton).toBeVisible();
    const panel = page.locator("div", { has: doneButton }).last();
    const categoryDropdown = panel.getByRole("button").nth(0);
    const tagDropdown = panel.getByRole("button").nth(1);

    const uniqueCategory = `Aaa E2E Cat ${Date.now()}`;

    // The create UI (search, options, "Create new", the name input and its
    // Save/Cancel) all live inside the open dropdown's listbox. Scope every
    // create interaction to it so a stray same-named button elsewhere can't
    // steal the click and dismiss the dropdown via outside-click.
    const listbox = page.getByRole("listbox");

    // --- Create a new category ------------------------------------------
    await categoryDropdown.click();
    await expect(listbox).toBeVisible();
    await listbox.getByRole("button", { name: "Create new" }).click();
    await listbox.getByPlaceholder("Enter name...").fill(uniqueCategory);
    await listbox.getByRole("button", { name: "Save" }).click();

    // Bug #2: the category select is now filled with the created value.
    // Case-insensitive: the backend title-cases the name (E2E → E2e).
    await expect(categoryDropdown).toHaveText(new RegExp(uniqueCategory, "i"));

    // Bug #1: re-open the dropdown; the option list is alphabetically sorted,
    // so the "Aaa …" category sits first, not appended at the bottom.
    await categoryDropdown.click();
    await expect(listbox).toBeVisible();
    const optionLabels = (await page.getByRole("option").allInnerTexts()).map(
      (s) => s.trim(),
    );
    const sortedLabels = [...optionLabels].sort((a, b) => a.localeCompare(b));
    expect(optionLabels).toEqual(sortedLabels);
    expect(optionLabels[0].toLowerCase()).toContain(uniqueCategory.toLowerCase());
    await page.keyboard.press("Escape");

    // --- Create a new tag under the fresh category ----------------------
    const uniqueTag = `Zzz E2E Tag ${Date.now()}`;
    await tagDropdown.click();
    await listbox.getByRole("button", { name: "Create new" }).click();
    await listbox.getByPlaceholder("Enter name...").fill(uniqueTag);
    await listbox.getByRole("button", { name: "Save" }).click();

    // Bug #2 for tags: the tag select is filled with the created value.
    await expect(tagDropdown).toHaveText(new RegExp(uniqueTag, "i"));
  });
});
