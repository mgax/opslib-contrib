import requests


class API:
    endpoint = "https://api.github.com"

    def __init__(self):
        self.session = requests.Session()

    def account(self, name):
        return Account(self, name)

    def get(self, url):
        resp = self.session.get(f"{self.endpoint}{url}")
        resp.raise_for_status()
        return resp.json()


class Account:
    def __init__(self, api, name):
        self.api = api
        self.name = name

    def repo(self, name):
        return Repo(self, name)


class Repo:
    def __init__(self, account, name):
        self.account = account
        self.name = name

    @property
    def api(self):
        return self.account.api

    def latest_release(self):
        return self.api.get(f"/repos/{self.account.name}/{self.name}/releases/latest")
