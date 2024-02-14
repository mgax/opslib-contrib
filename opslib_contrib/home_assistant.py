from collections.abc import Callable
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

import yaml
from opslib import Directory, evaluate, lazy_property
from opslib.components import TypedComponent

from opslib_contrib.backup_service import BackupPlan
from opslib_contrib.upgradable import UpgradableMixin
from opslib_contrib.docker import DockerCompose, Sidecar
from opslib_contrib.localsecret import LocalSecret
from opslib_contrib.versions import Version
import requests


class HomeAssistantVersion(Version):
    def get_latest(self):
        resp = requests.get("https://www.home-assistant.io/version.json")
        resp.raise_for_status()
        return resp.json()["current_version"]


@dataclass
class HomeAssistantProps:
    directory: Directory
    volumes: Directory
    create_tunnel_sidecar: Callable[..., Sidecar] | None = None


class HomeAssistant(UpgradableMixin, TypedComponent(HomeAssistantProps)):
    def build(self):
        self.directory = self.props.directory

        self.version = HomeAssistantVersion()

        self.config_volume = self.props.volumes / "config"
        self.db_volume = self.props.volumes / "db"
        self.db_password = LocalSecret()

        self.hass_secrets_yaml = self.directory.file(
            name="secrets.yaml",
            content=self.hass_secrets_content,
        )

        compose_secrets: dict[str, Any] = {
            "DB_PASSWORD": self.db_password.value,
        }

        if self.props.create_tunnel_sidecar:
            self.sidecar = self.props.create_tunnel_sidecar(
                backend="127.0.0.1:8123",
                network_mode="host",
            )
            compose_secrets.update(self.sidecar.secrets)

        else:
            self.sidecar = None

        self.compose = DockerCompose(
            directory=self.directory,
            services=self.compose_services,
            secrets=compose_secrets,
        )

        self.pg_dump_script = self.directory.file(
            name="dump_db",
            mode="755",
            content=dedent(
                f"""\
                #!/bin/bash
                set -euo pipefail
                cd {self.directory.path}
                docker compose exec -T db pg_dump -Ox -U ha \\
                    > {self.config_volume.path}/db-backup.sql
                """
            ),
        )

        self.up = self.compose.up_command()

    @lazy_property
    def hass_secrets_content(self):
        db_password = evaluate(self.db_password.value)
        secrets = {
            "psql_string": f"postgresql://ha:{db_password}@127.0.0.1:20251/ha",
        }
        return yaml.dump(secrets)

    @lazy_property
    def compose_services(self):
        version = evaluate(self.version.current)

        image = f"ghcr.io/home-assistant/home-assistant:{version}"

        app_volumes = [
            f"{self.config_volume.path}:/config",
            "./secrets.yaml:/config/secrets.yaml",
        ]

        services = dict(
            app=dict(
                image=image,
                environment={
                    "TZ": "Europe/Bucharest",
                },
                volumes=app_volumes,
                network_mode="host",
                restart="unless-stopped",
            ),
            db=dict(
                image="postgres:14",
                environment={
                    "POSTGRES_USER": "ha",
                    "POSTGRES_PASSWORD": "$DB_PASSWORD",
                    "PGPORT": "20251",
                },
                volumes=[
                    f"{self.db_volume.path}:/var/lib/postgresql/data",
                ],
                command="postgres -c listen_addresses=localhost",
                network_mode="host",
                restart="unless-stopped",
            ),
        )
        if self.sidecar:
            services["sidecar"] = self.sidecar.service

        return services

    def backup_to(self, plan: BackupPlan):
        plan.add_precommand(self.pg_dump_script.path)
        plan.add_path(self.config_volume.path)

    def upgrade(self, *, dry_run=False, deploy=True):
        self.version.set_latest(dry_run=dry_run)
        return super().upgrade(dry_run=dry_run, deploy=deploy)
