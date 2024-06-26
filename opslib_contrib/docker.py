from dataclasses import dataclass
import shlex
from textwrap import dedent
from typing import Any, Optional

import click
import yaml
from opslib import Component, Directory, Lazy, MaybeLazy, Prop, evaluate


class DockerCompose(Component):
    class Props:
        directory = Prop(Directory)
        services = Prop(Optional[dict], lazy=True)
        networks = Prop(Optional[dict], lazy=True)
        secrets = Prop(Optional[dict], lazy=True)
        compose_command = Prop(str, default="docker compose")
        filename = Prop(str, default="docker-compose.yml")
        compose_file_version = Prop(Optional[str])

    def build(self):
        def compose_file_content():
            return yaml.dump(self.get_compose_file_content(), sort_keys=False)

        self.compose_file = self.props.directory.file(
            name=self.props.filename,
            content=Lazy(compose_file_content),
        )

        self._up_command_run_after = [self.compose_file]

        if self.props.secrets is not None:
            self.env_file = self.props.directory.file(
                name=".env",
                content=Lazy(
                    lambda: "".join(
                        f"{key}={shlex.quote(value)}\n"
                        for key, value in evaluate(self.props.secrets).items()
                    )
                ),
                mode="600",
            )
            self._up_command_run_after.append(self.env_file)

    def get_compose_file_content(self):
        compose = {}

        if self.props.compose_file_version is not None:
            compose["version"] = self.props.compose_file_version

        services = evaluate(self.props.services)
        if services:
            compose["services"] = services

        networks = evaluate(self.props.networks)
        if networks:
            compose["networks"] = networks

        return compose

    def command(self, command, run_after=[]):
        return self.props.directory.host.command(
            input=dedent(
                f"""
                set -euo pipefail
                set -x
                cd {self.props.directory.path}
                {self.props.compose_command} {command}
                """
            ),
            run_after=run_after,
        )

    def run_compose(self, *args, **kwargs):
        self.props.directory.host.run(
            input=(
                f"set -x "
                f"&& cd {shlex.quote(str(self.props.directory.path))} "
                f"&& {self.props.compose_command} {' '.join(args)}"
            ),
            **kwargs,
        )

    def run(self, *args, **kwargs):
        self.props.directory.run(*self.props.compose_command.split(), *args, **kwargs)

    def build_command(self, run_after=[]):
        build = self.command("build", run_after=[self.compose_file, *run_after])
        self._up_command_run_after.append(build)
        return build

    def pull_command(self):
        pull = self.command("pull", run_after=[self.compose_file])
        self._up_command_run_after.append(pull)
        return pull

    def up_command(self, run_after=[]):
        return self.command(
            "up -d", run_after=[*self._up_command_run_after, *run_after]
        )

    def add_commands(self, cli):
        @cli.command
        def up():
            self.run("up", "-d", capture_output=False, exit=True)

        @cli.command(context_settings=dict(ignore_unknown_options=True))
        @click.argument("args", nargs=-1, type=click.UNPROCESSED)
        def run(args):
            self.run(*args, capture_output=False, exit=True)


@dataclass
class Sidecar:
    service: dict[str, Any]
    secrets: dict[str, MaybeLazy[str]]
