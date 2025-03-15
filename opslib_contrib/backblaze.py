from functools import cached_property
import os
from tempfile import TemporaryDirectory
from dataclasses import dataclass
import click

from opslib import MaybeLazy, run
from opslib.components import TypedComponent
from opslib.terraform import TerraformProvider

B2_KEY_CAPABILITIES = [
    "deleteFiles",
    "listBuckets",
    "listFiles",
    "readBucketEncryption",
    "readBucketReplications",
    "readBuckets",
    "readFiles",
    "shareFiles",
    "writeBucketEncryption",
    "writeBucketReplications",
    "writeFiles",
]


@dataclass
class BackblazeProps:
    config: dict | None = None


class Backblaze(TypedComponent(BackblazeProps)):
    @cached_property
    def config(self):
        return self.props.config or {}

    def build(self):
        self.provider = TerraformProvider(
            name="b2",
            source="Backblaze/b2",
            version="~> 0.8.1",
            config=self.config,
        )

    def bucket(self, name):
        return BackblazeBucket(
            account=self,
            name=name,
        )

    @property
    def b2_key_id(self):
        return (
            self.config.get("application_key_id") or os.environ["B2_APPLICATION_KEY_ID"]
        )

    @property
    def b2_key(self):
        return self.config.get("application_key") or os.environ["B2_APPLICATION_KEY"]


@dataclass
class BackblazeBucketProps:
    account: Backblaze
    name: str


class BackblazeBucket(TypedComponent(BackblazeBucketProps)):
    def build(self):
        self.resource = self.props.account.provider.resource(
            type="b2_bucket",
            args=dict(
                bucket_name=self.name,
                bucket_type="allPrivate",
            ),
            output=["bucket_id"],
        )

    @property
    def name(self):
        return self.props.name

    @property
    def bucket_id(self):
        return self.resource.output["bucket_id"]

    def key(self):
        return BackblazeKey(
            account=self.props.account,
            name=self.name,
            bucket_id=self.bucket_id,
        )

    def run(self, *args, **kwargs):
        extra_env = kwargs.setdefault("extra_env", {})
        extra_env.update(
            B2_APPLICATION_KEY_ID=self.props.account.b2_key_id,
            B2_APPLICATION_KEY=self.props.account.b2_key,
        )
        run("b2", *args, **kwargs)

    def add_commands(self, cli):
        @cli.forward_command
        def run(args):
            self.run(*args, capture_output=False, exit=True)

        @cli.command()
        @click.argument("source", type=click.Path(file_okay=False))
        def sync_from(source):
            b2_uri = f"b2://{self.props.name}"
            self.run("sync", source, b2_uri, capture_output=False, exit=True)

        @cli.command()
        @click.argument("target", type=click.Path(file_okay=False))
        def sync_to(target):
            b2_uri = f"b2://{self.props.name}"
            self.run("sync", b2_uri, target, capture_output=False, exit=True)

        @cli.command()
        def empty_bucket():
            b2_uri = f"b2://{self.props.name}"
            resp = input(f"Are you sure you want to empty the bucket {b2_uri!r}? [y/N]")
            if resp.lower() != "y":
                return
            with TemporaryDirectory() as tmp:
                self.run(
                    "sync",
                    "--allow-empty-source",
                    "--delete",
                    tmp,
                    b2_uri,
                    capture_output=False,
                    exit=True,
                )


@dataclass
class BackblazeKeyProps:
    account: Backblaze
    name: str
    bucket_id: MaybeLazy[str]


class BackblazeKey(TypedComponent(BackblazeKeyProps)):
    def build(self):
        self.resource = self.props.account.provider.resource(
            type="b2_application_key",
            args=dict(
                capabilities=B2_KEY_CAPABILITIES,
                key_name=self.props.name,
                bucket_id=self.props.bucket_id,
            ),
            output=["application_key_id", "application_key"],
        )

    @property
    def key_id(self):
        return self.resource.output["application_key_id"]

    @property
    def key(self):
        return self.resource.output["application_key"]
