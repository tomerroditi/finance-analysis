from threading import Thread
import time
import datetime
from fad.scraper.scrapers import OneZeroScraper
import yaml


def test_basic_tfa_flow():
    with open(r"/fad/resources/test_credentials.yaml", 'r') as stream:
        credentials = yaml.safe_load(stream)

    last_month = datetime.datetime.now() - datetime.timedelta(days=30)
    last_month_str = last_month.strftime('%Y-%m-%d')

    scraper = OneZeroScraper("test_account", credentials['banks']['onezero']['Tomer'])
    scraper.script_path = r"C:\Users\tomer\Desktop\finance-analysis\fad\scraper\node\onezero_testing_scraper.js"
    t1 = Thread(target=scraper.pull_data_to_db, args=(last_month_str, 'test.db'))
    t1.start()
    while True:
        print(f"otp code: {scraper.otp_code}", flush=True)
        if scraper.otp_code == "waiting for input":
            otp_code = input("Enter the OTP code: ")
            scraper.set_otp_code(otp_code)
            break
        time.sleep(2)

    print("waiting for thread to finish", flush=True)
    t1.join()
    print("thread finished", flush=True)