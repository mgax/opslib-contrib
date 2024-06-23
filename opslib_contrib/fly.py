from dataclasses import dataclass

from opslib import run
from opslib.components import TypedComponent
from opslib.terraform import TerraformProvider


@dataclass
class FlyProps:
    pass


class Fly(TypedComponent(FlyProps)):
    def build(self):
        self.provider = TerraformProvider(
            name="fly",
            source="andrewbaxter/fly",
            version="~> 0.1.13",
            config={
                "fly_api_token": run("flyctl", "auth", "token").stdout.strip(),
            },
        )

    def app(self, **props):
        return FlyApp(fly=self, **props)


@dataclass
class FlyAppProps:
    fly: Fly
    name: str


class FlyApp(TypedComponent(FlyAppProps)):
    def build(self):
        self.resource = self.props.fly.provider.resource(
            type="fly_app",
            args={
                "name": self.props.name,
            },
            output=["id", "app_url"],
        )

    @property
    def id(self):
        return self.resource.output["id"]

    def volume(self, **props):
        return FlyVolume(fly=self.props.fly, app=self, **props)


@dataclass
class FlyVolumeProps:
    fly: Fly
    app: FlyApp
    name: str
    region: str
    size: int


class FlyVolume(TypedComponent(FlyVolumeProps)):
    def build(self):
        self.resource = self.props.fly.provider.resource(
            type="fly_volume",
            args={
                "app": self.props.app.id,
                "name": self.props.name,
                "region": self.props.region,
                "size": self.props.size,
            },
        )
