"""Tests for Max's ID-number login challenge and its failure screens."""

import asyncio

import pytest

from backend.constants.providers import LoginFields
from scraper.exceptions import CredentialsError
from scraper.models.credentials import PROVIDER_CONFIGS
from scraper.models.result import LoginResult
from scraper.providers.credit_cards import max as max_module

ID_REQUEST_TEXT = "בשל מספר ניסיונות לא טובים, נבקש למלא את מספר תעודת הזהות שלך"
LOCKED_TEXT = "אופס בגלל מספר ניסיונות שגויים, פרטי המשתמש שלך ננעלו"


class _FakeElement:
    """The two things the Max module asks of an element: its text and visibility."""

    def __init__(self, text: str):
        self._text = text

    async def inner_text(self) -> str:
        return self._text

    async def is_visible(self) -> bool:
        return True


class _FakePage:
    """A login page defined by which selectors are on screen and their text."""

    def __init__(self, elements: dict[str, str]):
        self.elements = dict(elements)

    async def query_selector(self, selector):
        if selector not in self.elements:
            return None
        return _FakeElement(self.elements[selector])


class _FakeMaxLogin:
    """Scripts the Max login page's responses to submits.

    ``id_prompts`` is how many submits Max answers by asking for the ID number
    (as both an inline message and the ID input, exactly as the real site
    does) before it lets the login through.
    """

    def __init__(self, id_prompts: int, elements: dict[str, str] | None = None):
        self.id_prompts = id_prompts
        self.page = _FakePage(elements or {})
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        self._apply_id_prompt()

    def _apply_id_prompt(self) -> None:
        if self.id_prompts > 0:
            self.page.elements[max_module.ID_INPUT_SELECTOR] = ""
            self.page.elements[max_module.INLINE_ERROR_SELECTOR] = ID_REQUEST_TEXT
        else:
            self.page.elements.pop(max_module.ID_INPUT_SELECTOR, None)

    async def wait_for_redirect(self, page, timeout=20.0, ignore_list=None):
        if self.id_prompts > 0:
            await asyncio.sleep(3600)

    async def wait_until_element_found(self, page, selector, only_visible=False, timeout=30000):
        if selector in page.elements:
            return
        await asyncio.sleep(3600)

    async def fill_input(self, page, selector, value):
        self.filled.append((selector, value))

    async def click_button(self, page, selector):
        self.clicked.append(selector)
        self.id_prompts -= 1
        self._apply_id_prompt()


@pytest.fixture
def fake_login(monkeypatch):
    """Patch the Max module's page helpers with a scripted fake login page."""

    def install(id_prompts: int, elements: dict[str, str] | None = None) -> _FakeMaxLogin:
        fake = _FakeMaxLogin(id_prompts, elements)
        for name in ("wait_for_redirect", "wait_until_element_found", "fill_input", "click_button"):
            monkeypatch.setattr(max_module, name, getattr(fake, name))
        return fake

    return install


@pytest.fixture
def classify(monkeypatch):
    """Return a helper that classifies a page state via Max's login-result checks."""

    async def _present(page, selector):
        return selector in page.elements

    monkeypatch.setattr(max_module, "element_present_on_page", _present)

    async def run(elements: dict[str, str]):
        page = _FakePage(elements)
        for result, checks in max_module._get_possible_login_results(page).items():
            for check in checks:
                if callable(check) and await check(page=page, value=""):
                    return result
        return None

    return lambda elements: asyncio.run(run(elements))


class TestMaxIdChallenge:
    """``_complete_login`` answers Max's ID prompt only when it appears."""

    def test_plain_redirect_never_touches_id_input(self, fake_login):
        """A login that redirects straight away neither fills nor resubmits."""
        fake = fake_login(id_prompts=0)
        asyncio.run(max_module._complete_login(fake.page, "123456789"))
        assert fake.filled == []
        assert fake.clicked == []

    def test_id_prompt_is_filled_and_resubmitted(self, fake_login):
        """When Max asks for the ID, the stored ID is typed and the form resubmitted."""
        fake = fake_login(id_prompts=1)
        asyncio.run(max_module._complete_login(fake.page, " 123456789 "))
        assert fake.filled == [(max_module.ID_INPUT_SELECTOR, "123456789")]
        assert fake.clicked == [max_module.LOGIN_SUBMIT_SELECTOR]

    @pytest.mark.parametrize("user_id", [None, "", "   "])
    def test_id_prompt_without_stored_id_fails_clearly(self, fake_login, user_id):
        """Without a stored ID the login fails fast with a credentials error naming the ID."""
        fake = fake_login(id_prompts=1)
        with pytest.raises(CredentialsError, match="ID number"):
            asyncio.run(max_module._complete_login(fake.page, user_id))
        assert fake.clicked == []

    def test_id_request_is_not_mistaken_for_a_rejected_login(self, fake_login):
        """Max words the ID request as an inline error; it must still take the ID path."""
        fake = fake_login(id_prompts=1)
        assert (
            asyncio.run(max_module._await_login_outcome(fake.page, True, "")) is True
        )

    def test_stale_id_request_does_not_end_the_resubmit_wait(self, fake_login):
        """After the ID is submitted, the leftover ID-request message is ignored."""
        fake = fake_login(id_prompts=1)
        fake.page.elements[max_module.ERROR_SCREEN_SELECTOR] = LOCKED_TEXT
        asyncio.run(max_module._complete_login(fake.page, "123456789"))
        # The resubmit waited for the lock screen, not the stale inline message.
        assert fake.clicked == [max_module.LOGIN_SUBMIT_SELECTOR]


class TestMaxLoginFailureScreens:
    """Max reports failures as an error screen or an inline message, not only popups."""

    def test_lock_screen_is_reported_as_blocked(self, classify):
        """The "your details have been locked" screen maps to ACCOUNT_BLOCKED."""
        assert (
            classify({max_module.ERROR_SCREEN_SELECTOR: LOCKED_TEXT})
            is LoginResult.ACCOUNT_BLOCKED
        )

    def test_other_error_screen_is_an_unknown_error(self, classify):
        """An error screen without lock wording is not misreported as a lockout."""
        assert (
            classify({max_module.ERROR_SCREEN_SELECTOR: "אירעה תקלה טכנית"})
            is LoginResult.UNKNOWN_ERROR
        )

    def test_inline_error_is_reported_as_invalid_password(self, classify):
        """The inline wrong-details message maps to INVALID_PASSWORD."""
        assert (
            classify({max_module.INLINE_ERROR_SELECTOR: "הפרטים שהוזנו שגויים"})
            is LoginResult.INVALID_PASSWORD
        )

    @pytest.mark.parametrize(
        "selector,text",
        [
            ("ERROR_SCREEN_SELECTOR", LOCKED_TEXT),
            ("INLINE_ERROR_SELECTOR", "הפרטים שהוזנו שגויים"),
            ("INVALID_DETAILS_SELECTOR", ""),
            ("LOGIN_ERROR_SELECTOR", ""),
        ],
    )
    def test_each_failure_surface_ends_the_wait(self, fake_login, selector, text):
        """Every failure surface ends the post-submit wait instead of timing out."""
        fake = fake_login(id_prompts=0, elements={getattr(max_module, selector): text})
        assert asyncio.run(max_module._await_login_outcome(fake.page, True, "")) is False


class TestMaxOptionalIdField:
    """The ID number is an optional Max credential, listed after the required ones."""

    def test_provider_config_marks_id_optional(self):
        """Max keeps username/password required and ID optional."""
        config = PROVIDER_CONFIGS["max"]
        assert config.required_fields == ["username", "password"]
        assert config.optional_fields == ["id"]

    def test_login_fields_include_optional_id_last(self):
        """The credentials form lists the ID field after the required fields."""
        assert LoginFields.get_fields("max") == ["username", "password", "id"]

    def test_providers_without_optional_fields_are_unchanged(self):
        """Providers that declare no optional fields list only their required ones."""
        assert LoginFields.get_fields("visa cal") == ["username", "password"]
