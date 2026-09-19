"""Tests for Max's ID-number login challenge and its optional credential."""

import asyncio

import pytest

from backend.constants.providers import LoginFields
from scraper.exceptions import CredentialsError
from scraper.models.credentials import PROVIDER_CONFIGS
from scraper.providers.credit_cards import max as max_module


class _FakeMaxLogin:
    """Stand-in for the Max login page's waits and inputs.

    ``id_prompts`` is how many times the ID input shows up before the page
    redirects: each submit either reveals the ID input (while prompts remain)
    or redirects.
    """

    def __init__(self, id_prompts: int):
        self.id_prompts = id_prompts
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []

    async def wait_for_redirect(self, page, timeout=20.0, ignore_list=None):
        if self.id_prompts > 0:
            await asyncio.sleep(3600)

    async def wait_until_element_found(self, page, selector, only_visible=False, timeout=30000):
        if selector == max_module.ID_INPUT_SELECTOR and self.id_prompts > 0:
            return
        await asyncio.sleep(3600)

    async def fill_input(self, page, selector, value):
        self.filled.append((selector, value))

    async def click_button(self, page, selector):
        self.clicked.append(selector)
        self.id_prompts -= 1


@pytest.fixture
def fake_login(monkeypatch):
    """Patch the Max module's page helpers with a scripted fake."""

    def install(id_prompts: int) -> _FakeMaxLogin:
        fake = _FakeMaxLogin(id_prompts)
        for name in ("wait_for_redirect", "wait_until_element_found", "fill_input", "click_button"):
            monkeypatch.setattr(max_module, name, getattr(fake, name))
        return fake

    return install


class TestMaxIdChallenge:
    """``_complete_login`` answers Max's ID prompt only when it appears."""

    def test_plain_redirect_never_touches_id_input(self, fake_login):
        """A login that redirects straight away neither fills nor resubmits."""
        fake = fake_login(id_prompts=0)
        asyncio.run(max_module._complete_login(object(), "123456789"))
        assert fake.filled == []
        assert fake.clicked == []

    def test_id_prompt_is_filled_and_resubmitted(self, fake_login):
        """When Max asks for the ID, the stored ID is typed and the form resubmitted."""
        fake = fake_login(id_prompts=1)
        asyncio.run(max_module._complete_login(object(), " 123456789 "))
        assert fake.filled == [(max_module.ID_INPUT_SELECTOR, "123456789")]
        assert fake.clicked == [max_module.LOGIN_SUBMIT_SELECTOR]

    @pytest.mark.parametrize("user_id", [None, "", "   "])
    def test_id_prompt_without_stored_id_fails_clearly(self, fake_login, user_id):
        """Without a stored ID the login fails fast with a credentials error naming the ID."""
        fake = fake_login(id_prompts=1)
        with pytest.raises(CredentialsError, match="ID number"):
            asyncio.run(max_module._complete_login(object(), user_id))
        assert fake.clicked == []


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
