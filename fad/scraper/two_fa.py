import subprocess

from pathlib import Path
from threading import Event
from time import sleep


activate = {
    "onezero": "onezero_2fa.js",
}


class TwoFAHandler:
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

        if provider in activate:
            contact_info = self._handle_contact_info(provider, self.contact_info)
            js_script = str(Path(__file__).parent / 'node' / activate[provider])

            # Start the Node.js script
            self.process = subprocess.Popen(
                ['node', js_script, contact_info],
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

    @staticmethod
    def _handle_contact_info(provider: str, contact_info: str) -> str:
        """
        Handle the contact info based on the provider

        Parameters
        ----------
        provider : str
            The provider for which to handle the contact info
        contact_info : str
            The contact info to handle

        Returns
        -------
        str
            The handled contact info
        """
        if provider == 'onezero':  # phone number, should be in the format of +9725...
            if contact_info.startswith('05'):
                contact_info = '+972' + contact_info[1:]
            elif contact_info.startswith('972'):
                contact_info = '+' + contact_info

            if contact_info.startswith('+9720'):
                contact_info = contact_info.replace('+9720', '+972')
        else:
            raise NotImplementedError(f'Handling contact info for provider {provider} is not implemented')

        return contact_info

# if __name__ == '__main__':
#     contact_info = '+972543453167'
#     js_script = str(Path(__file__).parent / 'node' / activate['onezero'])
#     try:
#         # Start the Node.js script
#         process = subprocess.Popen(
#             ['node', js_script, contact_info],
#             stdin=subprocess.PIPE,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             text=True,
#             encoding='utf-8'
#         )
#
#         # Read stdout line by line until we see the OTP prompt
#         while True:
#             output = process.stdout.readline()
#             if output == '' and process.poll() is not None:
#                 break
#             if output:
#                 print(output.strip())
#                 if 'Enter OTP code: ' in output:
#                     otp_code = input("Enter OTP code: ")
#                     process.stdin.write(otp_code + '\n')
#                     process.stdin.flush()
#                     break
#
#         # Read the output and error streams
#         while process.poll() is None:
#             sleep(0.5)
#         stdout, stderr = process.communicate()
#     except Exception as e:
#         print(f"An error occurred: {e}")