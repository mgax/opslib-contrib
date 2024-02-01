from collections.abc import Callable
from dataclasses import dataclass
import shlex

from opslib import Directory, evaluate, lazy_property
from opslib.components import TypedComponent

from opslib_contrib.backup_service import BackupPlan
from opslib_contrib.docker import DockerCompose
from opslib_contrib.localsecret import LocalSecret


@dataclass
class PaperlessProps:
    directory: Directory
    volumes: Directory
    env_vars: dict | None = None
    port: int | str | None = None
    create_tunnel_sidecar: Callable | None = None


class Paperless(TypedComponent(PaperlessProps)):
    def build(self):
        self.directory = self.props.directory
        self.volumes = self.props.volumes
        self.secret_key = LocalSecret()

        self.env_file = self.directory.file(
            name="env",
            content=self.env_file_content,
        )

        self.backup_volume = self.volumes / "backup"

        self.compose = DockerCompose(
            directory=self.directory,
            services=self.compose_services,
        )

        self.up = self.compose.up_command(run_after=[self.env_file])

    @lazy_property
    def env_file_content(self):
        vars = {
            "PAPERLESS_SECRET_KEY": evaluate(self.secret_key.value),
            **(self.props.env_vars or {}),
        }
        return "".join(f"{key}={value}\n" for key, value in vars.items())

    @lazy_property
    def compose_services(self):
        vol = self.volumes.path

        services = {
            "broker": {
                "image": "docker.io/library/redis:7",
                "restart": "unless-stopped",
                "volumes": [
                    f"{vol / 'redisdata'}:/data",
                ],
            },
            "db": {
                "image": "docker.io/library/postgres:15",
                "restart": "unless-stopped",
                "volumes": [
                    f"{vol / 'pgdata'}:/var/lib/postgresql/data",
                ],
                "environment": {
                    "POSTGRES_DB": "paperless",
                    "POSTGRES_USER": "paperless",
                    "POSTGRES_PASSWORD": "paperless",
                },
            },
            "webserver": {
                "image": "ghcr.io/paperless-ngx/paperless-ngx:2.4.0",
                "restart": "unless-stopped",
                "depends_on": [
                    "db",
                    "broker",
                    "gotenberg",
                    "tika",
                ],
                "volumes": [
                    f"{vol / 'data'}:/usr/src/paperless/data",
                    f"{vol / 'media'}:/usr/src/paperless/media",
                    f"{vol / 'export'}:/usr/src/paperless/export",
                    f"{vol / 'consume'}:/usr/src/paperless/consume",
                    f"{self.backup_volume.path}:/backup_volume",
                ],
                "env_file": self.env_file.path.name,
                "environment": {
                    "PAPERLESS_REDIS": "redis://broker:6379",
                    "PAPERLESS_DBHOST": "db",
                    "PAPERLESS_TIKA_ENABLED": 1,
                    "PAPERLESS_TIKA_GOTENBERG_ENDPOINT": "http://gotenberg:3000",
                    "PAPERLESS_TIKA_ENDPOINT": "http://tika:9998",
                },
            },
            "gotenberg": {
                "image": "docker.io/gotenberg/gotenberg:7.10",
                "restart": "unless-stopped",
                "command": [
                    "gotenberg",
                    "--chromium-disable-javascript=true",
                    "--chromium-allow-list=file:///tmp/.*",
                ],
            },
            "tika": {
                "image": "ghcr.io/paperless-ngx/tika:2.9.0-minimal",
                "restart": "unless-stopped",
            },
        }

        if self.props.port:
            services["webserver"]["ports"] = [
                f"{self.props.port}:8000",
            ]

        if self.props.create_tunnel_sidecar:
            services["sidecar"] = self.props.create_tunnel_sidecar(
                backend="webserver:8000",
            )

        return services

    def backup_to(self, plan: BackupPlan):
        plan.add_precommand(
            "("
            f"cd {shlex.quote(str(self.directory.path))}"
            " && docker compose exec -T webserver document_exporter /backup_volume"
            ")"
        )
        plan.add_path(self.backup_volume.path)
