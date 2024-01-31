from opslib import Component, Prop, evaluate
from opslib.terraform import TerraformProvider


class Healthchecks(Component):
    class Props:
        api_key = Prop(str)

    def build(self):
        self.provider = TerraformProvider(
            name="healthchecksio",
            source="kristofferahl/healthchecksio",
            version="~> 1.10.0",
            config=dict(
                api_key=self.props.api_key,
            ),
        )

    def channel(self, **props):
        return HealthchecksChannel(
            project=self,
            **props,
        )

    def check(self, **props):
        return HealthchecksCheck(
            project=self,
            **props,
        )


class HealthchecksChannel(Component):
    class Props:
        project = Prop(Healthchecks)
        kind = Prop(str)

    def build(self):
        self.channel = self.props.project.provider.data(
            type="healthchecksio_channel",
            args=dict(
                kind=self.props.kind,
            ),
            output=["id"],
        )

    @property
    def id(self):
        return self.channel.output["id"]


class HealthchecksCheck(Component):
    class Props:
        project = Prop(Healthchecks)
        name = Prop(str)
        extra = Prop.remainder

    def build(self):
        self.check = self.props.project.provider.resource(
            type="healthchecksio_check",
            args=dict(
                name=self.props.name,
                **self.props.extra,
            ),
            output=["ping_url"],
        )

    @property
    def url(self):
        return self.check.output["ping_url"]

    def wrap_command(self, command):
        url = evaluate(self.url)
        return (
            f"(\n"
            f"curl -s {url}/start -o /dev/null\n"
            f"healthchecks_exit_code=0\n"
            f"{command} || healthchecks_exit_code=$?\n"
            f"curl -s {url}/$healthchecks_exit_code -o /dev/null\n"
            f"exit $healthchecks_exit_code\n"
            f")\n"
        )
