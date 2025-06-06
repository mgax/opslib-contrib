import shlex
from dataclasses import dataclass
from functools import cached_property
from io import StringIO

from opslib import Directory, evaluate, lazy_property
from opslib.components import TypedComponent
from opslib.extras.systemd import SystemdTimerService
from opslib_contrib.backblaze import Backblaze, BackblazeBucket, BackblazeKey
from opslib_contrib.healthchecks import Healthchecks
from opslib_contrib.localsecret import LocalSecret
from opslib_contrib.restic import Restic

BASH_PREAMBLE = """\
#!/bin/bash
set -euo pipefail
"""


class BackupStorage:
    @lazy_property
    def restic_repository(self) -> str:
        ...

    @lazy_property
    def restic_env(self) -> dict[str, str]:
        ...


@dataclass
class BackupServiceProps:
    name_prefix: str
    healthchecks: Healthchecks
    backblaze: Backblaze | None = None


class BackupService(TypedComponent(BackupServiceProps)):
    def create_plan(self, **kwargs):
        return BackupPlan(
            service=self,
            **kwargs,
        )

    def full_name(self, name):
        return f"{self.props.name_prefix}{name}"


@dataclass
class B2Storage(BackupStorage):
    b2_bucket: BackblazeBucket
    b2_key: BackblazeKey

    @lazy_property
    def restic_repository(self):
        return f"b2:{self.b2_bucket.name}:"

    @lazy_property
    def restic_env(self):
        return dict(
            B2_ACCOUNT_ID=evaluate(self.b2_key.key_id),
            B2_ACCOUNT_KEY=evaluate(self.b2_key.key),
        )


@dataclass
class BackupPlanProps:
    service: BackupService
    name: str
    directory: Directory
    shell: str = "/bin/bash"
    restic_binary: str = "restic"
    backup_script_preamble: str = BASH_PREAMBLE
    storage: BackupStorage | None = None
    setup_healthcheck: bool = True


class BackupPlan(TypedComponent(BackupPlanProps)):
    @cached_property
    def full_name(self):
        return self.props.service.full_name(self.props.name)

    def build(self):
        self.backup_precommands = []
        self.backup_paths = []
        self.backup_exclude = []

        self.directory = self.props.directory

        if self.props.storage:
            self._storage = self.props.storage

        else:
            self.b2_bucket = self.props.service.props.backblaze.bucket(
                name=self.full_name,
            )

            self.b2_key = self.b2_bucket.key()

            self._storage = B2Storage(self.b2_bucket, self.b2_key)

        self.password = LocalSecret()

        self.repo = Restic(
            repository=self._storage.restic_repository,
            password=self.password.value,
            env=self._storage.restic_env,
            restic_binary=self.props.restic_binary,
        )

        self.script = self.directory.file(
            name="backup",
            content=self.backup_script_content,
            mode="700",
        )

        if self.props.setup_healthcheck:
            self.healthcheck_channels = self.props.service.props.healthchecks.channel(
                kind="email",
            )

            self.healthcheck = self.props.service.props.healthchecks.check(
                name=f"{self.full_name}-daily",
                channels=[self.healthcheck_channels.id],
                timeout=86400,
            )

        self.daily = self.directory.file(
            name="daily",
            mode="700",
            content=self.daily_content,
        )

    @lazy_property
    def backup_script_content(self):
        out = StringIO()
        out.write(self.props.backup_script_preamble)

        for cmd in self.backup_precommands:
            out.write(f"{cmd}\n")

        for key, value in self.repo.extra_env.items():
            out.write(f"export {key}={shlex.quote(evaluate(value))}\n")

        cmd = ["exec", self.props.restic_binary, "backup"]
        cmd += [shlex.quote(str(path)) for path in evaluate(self.backup_paths)]
        cmd += [
            f"--exclude={shlex.quote(str(path))}"
            for path in evaluate(self.backup_exclude)
        ]
        out.write(f"{' '.join(cmd)}\n")

        return out.getvalue()

    def systemd_timer_service(self, **props):
        props.setdefault("name", f"{self.full_name}-daily")

        return SystemdTimerService(
            host=self.directory.host.sudo(),
            exec_start=self.daily.path,
            **props,
        )

    @lazy_property
    def daily_content(self):
        backup_cmd = str(self.script.path)

        if self.props.setup_healthcheck:
            backup_cmd = self.healthcheck.wrap_command(backup_cmd)

        return f"#!{self.props.shell}\nset -euo pipefail\n\n{backup_cmd}"

    def add_precommand(self, cmd):
        self.backup_precommands.append(cmd)

    def add_path(self, path):
        self.backup_paths.append(path)
