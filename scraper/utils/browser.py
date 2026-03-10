from playwright.async_api import Frame, Page

from scraper.utils.waiting import wait_until


async def wait_until_element_found(
    page_or_frame: Page | Frame,
    selector: str,
    only_visible: bool = False,
    timeout: float = 30000,
) -> None:
    """Wait for an element matching selector to appear."""
    state = "visible" if only_visible else "attached"
    await page_or_frame.wait_for_selector(selector, state=state, timeout=timeout)


async def wait_until_element_disappear(
    page_or_frame: Page | Frame, selector: str, timeout: float = 30000
) -> None:
    """Wait for an element to be removed or hidden."""
    await page_or_frame.wait_for_selector(selector, state="hidden", timeout=timeout)


async def wait_until_iframe_found(
    page: Page,
    frame_predicate: callable,
    description: str = "",
    timeout: float = 30.0,
) -> Frame:
    """Wait for an iframe matching a predicate to appear."""

    async def check() -> Frame | None:
        for frame in page.frames:
            if frame_predicate(frame):
                return frame
        return None

    return await wait_until(check, description, timeout, interval=1.0)


async def fill_input(
    page_or_frame: Page | Frame, selector: str, value: str
) -> None:
    """Clear an input field and type a value into it."""
    # Clear existing value via JS, then type new value
    await page_or_frame.evaluate(
        "(selector) => { const el = document.querySelector(selector); if (el) el.value = ''; }",
        selector,
    )
    await page_or_frame.type(selector, value)


async def set_value(
    page_or_frame: Page | Frame, selector: str, value: str
) -> None:
    """Set an input's value directly via JS (no keystrokes)."""
    await page_or_frame.evaluate(
        "([selector, value]) => { const el = document.querySelector(selector); if (el) el.value = value; }",
        [selector, value],
    )


async def click_button(page_or_frame: Page | Frame, selector: str) -> None:
    """Click an element via JS click()."""
    await page_or_frame.evaluate(
        "(selector) => { const el = document.querySelector(selector); if (el) el.click(); }",
        selector,
    )


async def click_link(page: Page, selector: str) -> None:
    """Click a link element if it exists."""
    await page.evaluate(
        "(selector) => { const el = document.querySelector(selector); if (el && typeof el.click !== 'undefined') el.click(); }",
        selector,
    )


async def page_eval_all(
    page_or_frame: Page | Frame,
    selector: str,
    expression: str,
    default_result=None,
):
    """Evaluate a JS expression on all elements matching selector."""
    try:
        return await page_or_frame.eval_on_selector_all(selector, expression)
    except Exception:
        return default_result


async def page_eval(
    page_or_frame: Page | Frame,
    selector: str,
    expression: str,
    default_result=None,
):
    """Evaluate a JS expression on first element matching selector."""
    try:
        return await page_or_frame.eval_on_selector(selector, expression)
    except Exception:
        return default_result


async def element_present_on_page(
    page_or_frame: Page | Frame, selector: str
) -> bool:
    """Check if an element exists in the DOM."""
    element = await page_or_frame.query_selector(selector)
    return element is not None


async def dropdown_select(page: Page, selector: str, value: str) -> None:
    """Select a value from a <select> dropdown."""
    await page.select_option(selector, value)


async def dropdown_elements(page: Page, selector: str) -> list[dict]:
    """Get all options from a <select> dropdown."""
    return await page.eval_on_selector_all(
        f"{selector} > option",
        "options => options.filter(o => o.value).map(o => ({ name: o.text, value: o.value }))",
    )
