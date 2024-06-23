import json
from base64 import b64encode
from dataclasses import dataclass
from typing import cast

from opslib import Lazy, MaybeLazy, evaluate, lazy_property
from opslib.cli import ComponentGroup
from opslib.components import TypedComponent
from opslib.terraform import TerraformProvider

from .docker import Sidecar
from .localsecret import LocalSecret


class Cloudflare(TypedComponent()):
    def build(self):
        self.provider = TerraformProvider(
            name="cloudflare",
            source="cloudflare/cloudflare",
            version="~> 4.0",
        )

        self.accounts = self.provider.data(
            type="cloudflare_accounts",
            output=["accounts"],
        )

    def account(self, name, **kwargs):
        def get_account_id():
            for account in cast(list, evaluate(self.accounts.output["accounts"])):
                if account["name"] == name:
                    return account["id"]
            raise RuntimeError("Account not found")

        return CloudflareAccount(
            cloudflare=self,
            name=name,
            account_id=Lazy(get_account_id),
            **kwargs,
        )

    def add_commands(self, cli: ComponentGroup):
        @cli.command()
        def accounts():
            for account in cast(list, evaluate(self.accounts.output["accounts"])):
                print(account["id"], account["name"])


@dataclass
class CloudflareAccountProps:
    cloudflare: Cloudflare
    name: str
    account_id: MaybeLazy[str]


class CloudflareAccount(TypedComponent(CloudflareAccountProps)):
    def build(self):
        self.zones = self.props.cloudflare.provider.data(
            type="cloudflare_zones",
            args={
                "filter": {
                    "account_id": self.props.account_id,
                },
            },
            output=["zones"],
        )

    def add_commands(self, cli: ComponentGroup):
        @cli.command()
        def zones():
            for zone in cast(list, evaluate(self.zones.output["zones"])):
                print(zone["id"], zone["name"])

    def zone(self, name, **kwargs):
        def get_zone_id():
            for zone in cast(list, evaluate(self.zones.output["zones"])):
                if zone["name"] == name:
                    return zone["id"]

        return CloudflareZone(
            cloudflare=self.props.cloudflare,
            name=name,
            zone_id=Lazy(get_zone_id),
            **kwargs,
        )

    def tunnel(self, **kwargs):
        return CloudflareTunnel(
            cloudflare=self.props.cloudflare,
            account_id=self.props.account_id,
            **kwargs,
        )


@dataclass
class CloudflareZoneProps:
    cloudflare: Cloudflare
    name: str
    zone_id: MaybeLazy[str]


class CloudflareZone(TypedComponent(CloudflareZoneProps)):
    @property
    def zone_id(self):
        return self.props.zone_id

    def record(self, **kwargs):
        return CloudflareRecord(
            cloudflare=self.props.cloudflare,
            zone=self,
            **kwargs,
        )

    def access_application(self, **kwargs):
        return CloudflareAccessApplication(
            cloudflare=self.props.cloudflare,
            zone=self,
            **kwargs,
        )

    def create_ruleset(self, **kwargs):
        return CloudflareZoneRuleset(
            cloudflare=self.props.cloudflare,
            zone=self,
            **kwargs,
        )


@dataclass
class CloudflareRecordProps:
    cloudflare: Cloudflare
    zone: CloudflareZone
    args: dict


class CloudflareRecord(TypedComponent(CloudflareRecordProps)):
    def build(self):
        self.record = self.props.cloudflare.provider.resource(
            type="cloudflare_record",
            args=dict(
                zone_id=self.props.zone.zone_id,
                **self.props.args,
            ),
        )


@dataclass
class CloudflareZoneRulesetProps:
    cloudflare: Cloudflare
    zone: CloudflareZone
    args: dict


class CloudflareZoneRuleset(TypedComponent(CloudflareZoneRulesetProps)):
    def build(self):
        self.ruleset = self.props.cloudflare.provider.resource(
            type="cloudflare_ruleset",
            args=dict(
                zone_id=self.props.zone.zone_id,
                kind="zone",
                **self.props.args,
            ),
        )


@dataclass
class CloudflareAccessApplicationProps:
    cloudflare: Cloudflare
    zone: CloudflareZone
    name: str
    domain: str
    session_duration: str = "720h"


class CloudflareAccessApplication(TypedComponent(CloudflareAccessApplicationProps)):
    def build(self):
        self.access_application = self.props.cloudflare.provider.resource(
            type="cloudflare_access_application",
            args=dict(
                zone_id=self.props.zone.zone_id,
                name=self.props.name,
                domain=self.props.domain,
                session_duration=self.props.session_duration,
            ),
            output=["id"],
        )

    def access_policy(self, precedence, name, include, decision="allow"):
        return self.props.cloudflare.provider.resource(
            type="cloudflare_access_policy",
            args=dict(
                application_id=self.access_application.output["id"],
                zone_id=self.props.zone.zone_id,
                precedence=precedence,
                name=name,
                include=include,
                decision=decision,
            ),
        )


@dataclass
class CloudflareTunnelProps:
    cloudflare: Cloudflare
    account_id: MaybeLazy[str]
    name: str
    secret: MaybeLazy[str | None] = None


class CloudflareTunnel(TypedComponent(CloudflareTunnelProps)):
    def build(self):
        if self.props.secret is None:
            self.secret = LocalSecret()

        self.tunnel = self.props.cloudflare.provider.resource(
            type="cloudflare_tunnel",
            args=dict(
                account_id=self.props.account_id,
                name=self.props.name,
                secret=self._secret,
            ),
            output=["id"],
        )

    @lazy_property
    def _secret(self):
        if self.props.secret:
            return self.props.secret

        else:
            value = cast(str, evaluate(self.secret.value))
            return b64encode(value.encode("utf8")).decode("utf8")

    @lazy_property
    def cloudflared_token(self):
        payload = {
            "a": evaluate(self.props.account_id),
            "t": evaluate(self.tunnel.output["id"]),
            "s": evaluate(self._secret),
        }
        return b64encode(json.dumps(payload).encode("utf8")).decode("utf8")

    @lazy_property
    def cname_value(self):
        return f"{evaluate(self.tunnel.output['id'])}.cfargotunnel.com"

    def cname_record(self, zone, name):
        return zone.record(
            args=dict(
                name=name,
                type="CNAME",
                value=self.cname_value,
                proxied=True,
            ),
        )


@dataclass
class SimpleTunnelProps:
    cloudflare_account: CloudflareAccount
    zone_name: str
    hostname: str
    emails: list[str]


class SimpleTunnel(TypedComponent(SimpleTunnelProps)):
    def build(self):
        fqdn = f"{self.props.hostname}.{self.props.zone_name}"

        self.zone = self.props.cloudflare_account.zone(
            name=self.props.zone_name,
        )

        self.tunnel = self.props.cloudflare_account.tunnel(
            name=fqdn,
        )

        self.cname = self.tunnel.cname_record(
            zone=self.zone,
            name=self.props.hostname,
        )

        self.access_application = self.zone.access_application(
            name=fqdn,
            domain=fqdn,
        )

        self.access_policy = self.access_application.access_policy(
            precedence=1,
            name="Log in with email",
            include=dict(
                email=self.props.emails,
            ),
        )

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
                f"{name_prefix}_TUNNEL_TOKEN": self.tunnel.cloudflared_token,
            },
        )
