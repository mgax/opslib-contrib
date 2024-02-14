import json
from base64 import b64encode
from dataclasses import dataclass
from itertools import count

from opslib import MaybeLazy, evaluate, lazy_property
from opslib.components import TypedComponent
from opslib.terraform import TerraformProvider
from opslib_contrib.docker import Sidecar
from opslib_contrib.localsecret import LocalSecret


@dataclass
class CloudflareProps:
    account_name: str
    zone_name: str


class Cloudflare(TypedComponent(CloudflareProps)):
    def build(self):
        self.provider = TerraformProvider(
            name="cloudflare",
            source="cloudflare/cloudflare",
            version="~> 4.2",
        )

        self.accounts = self.provider.data(
            type="cloudflare_accounts",
            args=dict(
                name=self.props.account_name,
            ),
            output=["accounts"],
        )

        self.zones = self.provider.data(
            type="cloudflare_zones",
            args=dict(
                filter=dict(
                    name=self.props.zone_name,
                ),
            ),
            output=["zones"],
        )

    @lazy_property
    def account_id(self):
        accounts = evaluate(self.accounts.output["accounts"])
        assert (
            len(accounts) == 1
        ), f"Expected one account, found {len(accounts)}: {accounts!r}"
        return accounts[0]["id"]

    @lazy_property
    def zone_id(self):
        zones = evaluate(self.zones.output["zones"])
        assert len(zones) == 1, f"Expected one zone, found {len(zones)}: {zones!r}"
        return zones[0]["id"]

    def tunnel(self, name, secret=None):
        return CloudflareTunnel(
            name=name,
            secret=secret,
            provider=self.provider,
            account_id=self.account_id,
            zone_id=self.zone_id,
            zone_name=self.props.zone_name,
        )

    def access_application(self, name, domain, **kwargs):
        return CloudflareAccessApplication(
            provider=self.provider,
            zone_id=self.zone_id,
            name=name,
            domain=domain,
            **kwargs,
        )

    def record(self, name, type, value, proxied=False, **args):
        return self.provider.resource(
            type="cloudflare_record",
            args=dict(
                zone_id=self.zone_id,
                name=name,
                type=type,
                value=value,
                proxied=proxied,
                **args,
            ),
        )


@dataclass
class CloudflareTunnelProps:
    name: str
    secret: MaybeLazy[str | None]
    provider: TerraformProvider
    account_id: MaybeLazy[str]
    zone_id: MaybeLazy[str]
    zone_name: MaybeLazy[str]


class CloudflareTunnel(TypedComponent(CloudflareTunnelProps)):
    @lazy_property
    def _secret(self):
        if self.props.secret:
            return self.props.secret

        else:
            return b64encode(evaluate(self.secret.value).encode("utf8")).decode("utf8")

    def build(self):
        if self.props.secret is None:
            self.secret = LocalSecret()

        self.tunnel = self.props.provider.resource(
            type="cloudflare_tunnel",
            args=dict(
                account_id=self.props.account_id,
                name=self.props.name,
                secret=self._secret,
            ),
            output=["id"],
        )

        self.cname = self.props.provider.resource(
            type="cloudflare_record",
            args=dict(
                zone_id=self.props.zone_id,
                name=self.record_name,
                type="CNAME",
                value=self.cname_value,
                proxied=True,
            ),
        )

    @lazy_property
    def cname_value(self):
        return f"{evaluate(self.tunnel.output['id'])}.cfargotunnel.com"

    @lazy_property
    def record_name(self):
        name = self.props.name
        suffix = f".{self.props.zone_name}"
        return name[: -len(suffix)] if name.endswith(suffix) else name

    def token(self):
        payload = {
            "a": evaluate(self.props.account_id),
            "t": evaluate(self.tunnel.output["id"]),
            "s": evaluate(self._secret),
        }
        return b64encode(json.dumps(payload).encode("utf8")).decode("utf8")

    def sidecar(self, backend, name_prefix="CLOUDFLARED", **kwargs) -> Sidecar:
        return Sidecar(
            service=dict(
                image="cloudflare/cloudflared",
                command=f"tunnel --no-autoupdate run --url http://{backend}",
                environment={
                    "TUNNEL_TOKEN": f"${name_prefix}_TUNNEL_TOKEN",
                },
                restart="unless-stopped",
                **kwargs,
            ),
            secrets={
                f"{name_prefix}_TUNNEL_TOKEN": self.token(),
            },
        )


@dataclass
class CloudflareAccessApplicationProps:
    name: str
    provider: TerraformProvider
    zone_id: MaybeLazy[str]
    domain: str
    session_duration: str = "720h"


class CloudflareAccessApplication(TypedComponent(CloudflareAccessApplicationProps)):
    def build(self):
        self.application = self.props.provider.resource(
            type="cloudflare_access_application",
            args=dict(
                zone_id=self.props.zone_id,
                name=self.props.name,
                domain=self.props.domain,
                session_duration=self.props.session_duration,
            ),
            output=["id"],
        )

        self._precedence = count(1)

    def policy(self, name, include, decision="allow"):
        return self.props.provider.resource(
            type="cloudflare_access_policy",
            args=dict(
                application_id=self.application.output["id"],
                zone_id=self.props.zone_id,
                name=name,
                include=include,
                decision=decision,
                precedence=next(self._precedence),
            ),
        )
