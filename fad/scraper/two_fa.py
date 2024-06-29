import subprocess

from pathlib import Path
from threading import Event
from time import sleep


class TwoFAHandler:

    tfa_scripts = {
        "onezero": "onezero_2fa.js",
    }

    def __init__(self, provider, contact_info):
        self.provider = provider
        self.contact_info = contact_info
        self.process = None
        self.otp_code = None
        self.otp_event = Event()
        self.result = None
        self.error = None

    def handle_2fa(self):
        """
        Send the OTP code to the given contact info and get the long-term OTP token

        Returns
        -------
        str
            The long-term OTP token or error message if any error occurs
        """
        provider = self.provider.lower()

        if provider in TwoFAHandler.tfa_scripts:
            js_script = str(Path(__file__).parent / 'node' / TwoFAHandler.tfa_scripts[provider])

            # Start the Node.js script
            self.process = subprocess.Popen(
                ['node', js_script, self.contact_info],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )

            # wait for the OTP code to be requested, and then send it
            while True:
                output = self.process.stdout.readline()
                if output:
                    print(output.strip())
                    if 'Enter OTP code: ' in output:
                        print("Waiting for OTP code...")
                        self.otp_event.wait()  # Wait until the OTP code is set
                        self.process.stdin.write(self.otp_code + '\n')
                        self.process.stdin.flush()
                        break

            # wait for the process to finish
            while self.process.poll() is None:
                sleep(0.5)

            # Read the output and error streams
            stdout, stderr = self.process.communicate()
            self.result = stdout.rstrip()  # Remove the trailing newline
            self.error = stderr

    def set_otp_code(self, otp_code):
        self.otp_code = otp_code
        self.otp_event.set()  # Notify that the OTP code is available
