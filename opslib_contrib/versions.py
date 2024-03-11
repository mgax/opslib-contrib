import logging

import click
from opslib import Component, Prop, lazy_property
from opslib.state import JsonState

from . import github

logger = logging.getLogger(__name__)


class Version(Component):
    state = JsonState()

    def get_latest(self):
        raise NotImplementedError

    def set_latest(self, confirm=True, dry_run=False):
        current = self.state.get("current_version")
        latest = self.get_latest()

        if current == latest:
            click.echo(f"Already at latest: {latest!r}")

        else:
            if (not confirm) or click.confirm(
                f"Upgrading {self} from {current!r} to {latest!r}"
            ):
                if dry_run:
                    click.echo("Dry-run: not updating state")

                else:
                    self.state["current_version"] = latest

    @lazy_property
    def current(self):
        return self.state.get("current_version", "")

    def add_commands(self, cli):
        @cli.command
        def show():
            print(self.state.get("current_version"))

        @cli.command
        def set_latest():
            self.set_latest()

        @cli.command
        @click.argument("target")
        def set(target):
            current = self.state.get("current_version")

            if current == target:
                print(f"Already at target: {target!r}")

            else:
                print(f"Upgrading from {current!r} to {target!r}")
                self.state["current_version"] = target


class GithubVersion(Version):
    class Props:
        repo = Prop(str)

    def get_latest(self):
        account, repo = self.props.repo.split("/")
        repo_api = github.API().account(account).repo(repo)
        return repo_api.latest_release()["tag_name"]
