from datetime import date, datetime, timedelta
from threading import Thread
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.database import get_db_context
from backend.errors import EntityNotFoundException
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.scraper import Scraper, get_scraper, is_2fa_required

# Providers where 2FA is completed in the bank's browser window (not via OTP code in the app)
BROWSER_2FA_PROVIDERS = {"hapoalim"}

_tfa_scrapers_waiting: Dict[str, Tuple[Scraper, Thread]] = {}


class ScrapingService:
    """
    Service for managing data scraping operations.

    Handles launching scrapers in background threads, tracking 2FA wait
    states, recording scraping history, and computing start dates from
    the last successful scrape. Scrapers that require 2FA are kept in
    the module-level ``_tfa_scrapers_waiting`` dict until a code is submitted
    or the process is aborted.
    """

    def __init__(self, db: Session):
        """
        Initialize the scraping service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.scraping_history_repo = ScrapingHistoryRepository(db)
        self.credentials_repo = CredentialsRepository(db)

    def get_scraping_status(self, scraping_process_id: int) -> Dict[str, str | int]:
        """
        Get the current status of a scraping process.

        Parameters
        ----------
        scraping_process_id : int
            ID of the scraping history record to query.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``status`` – status string (e.g. ``"IN_PROGRESS"``, ``"SUCCESS"``,
              ``"FAILED"``, ``"WAITING_FOR_2FA"``) or ``"unknown"`` if not found.
            - ``process_id`` – echoed back ``scraping_process_id``.
            - ``error_message`` – error detail if status is ``"FAILED"``, else ``None``.
        """
        status = self.scraping_history_repo.get_scraping_status(
            int(scraping_process_id)
        )
        error_message = self.scraping_history_repo.get_error_message(
            int(scraping_process_id)
        )
        result = {
            "status": status or "unknown",
            "process_id": scraping_process_id,
            "error_message": error_message,
        }
        # Include tfa_type so the frontend knows which 2FA UI to show
        if status == ScrapingHistoryRepository.WAITING_FOR_2FA:
            provider = self.scraping_history_repo.get_provider_name(
                int(scraping_process_id)
            )
            result["tfa_type"] = (
                "browser" if provider in BROWSER_2FA_PROVIDERS else "otp"
            )
        return result

    def get_last_scrape_dates(self) -> List[Dict]:
        """
        Get last successful scrape dates for all configured accounts.
        Returns a list of dicts with service, provider, account_name, and last_scrape_date.
        """
        accounts = self.credentials_repo.list_accounts()
        result = []
        for acc in accounts:
            last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
                acc["service"], acc["provider"], acc["account_name"]
            )
            result.append(
                {
                    "service": acc["service"],
                    "provider": acc["provider"],
                    "account_name": acc["account_name"],
                    "last_scrape_date": last_scrape,
                }
            )
        return result

    def start_scraping_single(
        self,
        service: str,
        provider: str,
        account: str,
        scraping_period_days: Optional[int] = None,
    ) -> int:
        """
        Start the scraping process for a single account in a background thread.

        Records a new scraping history entry, creates the appropriate scraper,
        and starts it in a background thread. If the provider requires 2FA,
        the scraper is stored in ``_tfa_scrapers_waiting`` until an OTP is submitted.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"credit_cards"``, ``"banks"``).
        provider : str
            Provider identifier (e.g. ``"isracard"``, ``"hapoalim"``).
        account : str
            Account name used to look up credentials.
        scraping_period_days : int, optional
            Number of days to scrape back from today. If ``None``, falls back
            to the automatic start date based on last scrape history.

        Returns
        -------
        int
            The ``process_id`` of the new scraping history record.
        """
        if scraping_period_days is not None:
            start_date = date.today() - timedelta(days=scraping_period_days)
        else:
            start_date = self._get_scraper_start_date(service, provider, account)
        creds = self.credentials_repo.get_credentials(service, provider, account)
        requires_2fa = is_2fa_required(service, provider)

        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            status = (
                history_repo.WAITING_FOR_2FA
                if requires_2fa
                else history_repo.IN_PROGRESS
            )
            process_id = history_repo.record_scrape_start(
                service, provider, account, start_date, status
            )

        scraper = get_scraper(service, provider, account, creds, start_date, process_id)
        thread = Thread(target=scraper.pull_data_to_db)
        thread.start()

        if requires_2fa:
            name = f"{service} - {provider} - {account}"
            _tfa_scrapers_waiting[name] = (scraper, thread)

        return process_id

    def submit_2fa_code(
        self, service: str, provider: str, account: str, code: str
    ) -> None:
        """
        Submit a 2FA OTP code to an awaiting scraper.

        Pass the string ``"cancel"`` (via the scraper's ``CANCEL`` constant)
        to abort the scraping process instead.

        Parameters
        ----------
        service : str
            Service type of the waiting scraper.
        provider : str
            Provider identifier of the waiting scraper.
        account : str
            Account name of the waiting scraper.
        code : str
            OTP code to forward to the scraper, or the scraper's cancel sentinel.

        Raises
        ------
        EntityNotFoundException
            If no 2FA-waiting scraper is found for the given service/provider/account.
        """
        name = f"{service} - {provider} - {account}"
        if name not in _tfa_scrapers_waiting:
            raise EntityNotFoundException("Scraping process not found")

        scraper, thread = _tfa_scrapers_waiting[name]
        scraper.set_otp_code(code)

    def abort_scraping_process(self, process_id: int) -> None:
        """
        Abort an in-progress or 2FA-waiting scraping process.

        If the process is waiting for a 2FA code, the scraper is cancelled
        via its OTP channel and removed from ``_tfa_scrapers_waiting``.
        The history record is always marked ``FAILED`` regardless.

        Parameters
        ----------
        process_id : int
            ID of the scraping history record to abort.
        """
        # Check if it's a 2FA-waiting scraper
        target_name = None
        for name, (scraper, _) in _tfa_scrapers_waiting.items():
            if scraper.process_id == process_id:
                target_name = name
                break

        if target_name:
            # Cancel the 2FA scraper
            scraper, _ = _tfa_scrapers_waiting.pop(target_name)
            scraper.set_otp_code(scraper.CANCEL)

        # Mark as failed in the database regardless
        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            history_repo.record_scrape_end(process_id, history_repo.FAILED)

    def _get_scraper_start_date(
        self, service: str, provider: str, account: str
    ) -> datetime.date:
        """
        Calculate the start date for a scraping run.

        Uses the last successful scrape date minus 7 days as a buffer to
        catch any late-posted transactions. Falls back to 365 days ago if
        no prior successful scrape exists or the stored date cannot be parsed.

        Parameters
        ----------
        service : str
            Service type of the account.
        provider : str
            Provider identifier of the account.
        account : str
            Account name.

        Returns
        -------
        datetime.date
            Earliest date from which to fetch transactions.
        """
        last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
            service, provider, account
        )
        if last_scrape:
            try:
                start_date = datetime.fromisoformat(last_scrape).date() - timedelta(
                    days=7
                )
            except:
                start_date = date.today() - timedelta(days=365)
        else:
            start_date = date.today() - timedelta(days=365)
        return start_date

    def _collect_scrapers(self, credentials: Dict) -> Tuple[Dict, Dict]:
        """
        Build scraper instances for all accounts in a credentials dict.

        Parameters
        ----------
        credentials : dict
            Nested credentials dict in the form
            ``{service: {provider: {account: creds}}}``.

        Returns
        -------
        tuple[dict, dict]
            A ``(normal, tfa)`` pair where ``normal`` maps account name strings
            to scrapers that do not require 2FA, and ``tfa`` maps to scrapers
            that do require 2FA.

        Notes
        -----
        This method is not called by the current scraping flow (which creates
        scrapers one at a time via ``start_scraping_single``) and may be unused.
        """
        normal = {}
        tfa = {}
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, acc_creds in accounts.items():
                    name = f"{service} - {provider} - {account}"
                    scraper = get_scraper(service, provider, account, acc_creds)
                    if scraper.requires_2fa:
                        tfa[name] = scraper
                    else:
                        normal[name] = scraper
        return normal, tfa
