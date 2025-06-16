import os
import yaml

from fad import CREDENTIALS_PATH, SRC_PATH


class CredentialsRepository:
    def __init__(self):
        """
        Repository for managing credentials stored in a yaml file.
        The credentials are loaded from the yaml file and cached to prevent reloading the file in every rerun.
        """
        self.credentials = self.load_credentials()

    @staticmethod
    def load_credentials() -> dict:
        """
        Load the credentials from the yaml file and cache the result to prevent reloading the file in every rerun.
        all changes to the returned dictionary object are affecting the cached object.

        Returns
        -------
        dict
            The credentials dictionary
        """
        # make file if it doesn't exist
        if not os.path.exists(CREDENTIALS_PATH):
            os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
            with open(os.path.join(SRC_PATH, 'resources', 'default_credentials.yaml'), 'r') as file:
                default_credentials = yaml.safe_load(file)  # empty credentials
            with open(CREDENTIALS_PATH, 'w') as file:
                yaml.dump(default_credentials, file, sort_keys=False, indent=4)

        with open(CREDENTIALS_PATH, 'r') as file:
            return yaml.safe_load(file)
