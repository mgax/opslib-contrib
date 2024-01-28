from tempfile import TemporaryDirectory

from opslib import Component, Prop, run
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


class Backblaze(Component):
    class Props:
        config = Prop(dict, default={})

    def build(self):
        self.provider = TerraformProvider(
            name="b2",
            source="Backblaze/b2",
            version="~> 0.8.1",
            config=self.props.config,
        )

    def bucket(self, name):
        return BackblazeBucket(
            account=self,
            name=name,
        )


class BackblazeBucket(Component):
    class Props:
        account = Prop(Backblaze)
        name = Prop(str)

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
        run("b2", *args, **kwargs)

    def add_commands(self, cli):
        @cli.forward_command
        def b2(args):
            self.run(*args, capture_output=False, exit=True)

        @cli.command()
        def empty_bucket():
            b2_uri = f"b2://{self.props.name}"
            resp = input(f"Are you sure you want to empty the bucket {b2_uri!r}? [y/N]")
            if resp.lower() != "y":
                return
            with TemporaryDirectory() as tmp:
                self.run(
                    "sync",
                    "--allowEmptySource",
                    "--delete",
                    tmp,
                    b2_uri,
                    capture_output=False,
                    exit=True,
                )


class BackblazeKey(Component):
    class Props:
        account = Prop(Backblaze)
        name = Prop(str)
        bucket_id = Prop(str, lazy=True)

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
