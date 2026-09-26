"""Which API routers the app mounts, where, and in what order."""

import importlib
from typing import NamedTuple

from fastapi import FastAPI


class RouterMount(NamedTuple):
    """One router module and where it is mounted.

    Attributes
    ----------
    module : str
        Module under ``backend.routes`` exposing ``router``.
    prefix : str
        URL prefix the router is mounted at.
    tag : str
        OpenAPI tag for its operations.
    optional : bool
        Skip the router when its module cannot be imported — keyring and
        Playwright are absent on the serverless deployment.
    """

    module: str
    prefix: str
    tag: str
    optional: bool = False


# Mount order is route-matching order.
ROUTERS: tuple[RouterMount, ...] = (
    RouterMount("transactions", "/api/transactions", "Transactions"),
    RouterMount("budget", "/api/budget", "Budget"),
    RouterMount(
        "budget_month_overrides",
        "/api/budget-month-overrides",
        "Budget Month Overrides",
    ),
    RouterMount("tagging", "/api/tagging", "Tagging"),
    RouterMount("investments", "/api/investments", "Investments"),
    RouterMount("liabilities", "/api/liabilities", "Liabilities"),
    RouterMount("analytics", "/api/analytics", "Analytics"),
    RouterMount("fire", "/api/fire", "Early Retirement"),
    RouterMount("rates", "/api/rates", "Rates"),
    RouterMount("backup", "/api/backups", "Backups"),
    RouterMount("pending_refunds", "/api/pending-refunds", "Pending Refunds"),
    RouterMount("tagging_rules", "/api/tagging-rules", "Tagging Rules"),
    RouterMount("bank_balances", "/api/bank-balances", "Bank Balances"),
    RouterMount("cash_balances", "/api/cash-balances", "Cash Balances"),
    RouterMount("insurance_accounts", "/api/insurance-accounts", "Insurance Accounts"),
    RouterMount("retirement", "/api/retirement", "Retirement"),
    RouterMount("savings_goals", "/api/savings-goals", "Savings Goals"),
    RouterMount("onboarding", "/api/onboarding", "Onboarding"),
    RouterMount("version", "/api/version", "Version"),
    RouterMount("updates", "/api/updates", "Updates"),
    # In-app uninstall is macOS-only. The route file itself is platform-aware
    # and 400s on non-darwin, but it is registered everywhere so the OpenAPI
    # schema is stable across platforms.
    RouterMount("uninstall", "/api/uninstall", "Uninstall", optional=True),
    RouterMount("credentials", "/api/credentials", "Credentials", optional=True),
    # Scrape history is a plain DB read and must stay available even where the
    # scraper itself cannot be imported (serverless has no Playwright) —
    # otherwise every data source on the hosted demo reports "never synced".
    # Mounted before the gated router below so that one can override nothing
    # it owns.
    RouterMount("scraping_readonly", "/api/scraping", "Scraping"),
    RouterMount("scraping", "/api/scraping", "Scraping", optional=True),
)

# Demo-mode toggling and DB reset helpers — never mounted in production
# unless explicitly enabled (see ``backend.main``).
TESTING_ROUTER = RouterMount("testing", "/api/testing", "Testing", optional=True)


def include_router_mount(app: FastAPI, mount: RouterMount) -> None:
    """Import one router module and mount its ``router`` on ``app``.

    Parameters
    ----------
    app : FastAPI
        Application to mount the router on.
    mount : RouterMount
        The router to mount.

    Raises
    ------
    ImportError
        When a required router's module cannot be imported; an optional
        router is skipped instead.
    """
    try:
        module = importlib.import_module(f"backend.routes.{mount.module}")
    except ImportError:
        if mount.optional:
            return
        raise
    app.include_router(module.router, prefix=mount.prefix, tags=[mount.tag])


def register_routers(app: FastAPI, *, include_testing: bool) -> None:
    """Mount every API router on ``app`` in :data:`ROUTERS` order.

    Parameters
    ----------
    app : FastAPI
        Application to mount the routers on.
    include_testing : bool
        Also mount the testing router, last.
    """
    mounts = (*ROUTERS, TESTING_ROUTER) if include_testing else ROUTERS
    for mount in mounts:
        include_router_mount(app, mount)
