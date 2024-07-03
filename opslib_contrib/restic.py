from dataclasses import dataclass
from opslib import Lazy, MaybeLazy, evaluate, run
from opslib.components import TypedComponent
from opslib.results import OperationError, Result
from opslib.state import JsonState, StatefulMixin


@dataclass
class ResticProps:
    repository: str
    password: MaybeLazy[str]
    env: MaybeLazy[dict | None]
    restic_binary: str = "restic"


class Restic(StatefulMixin, TypedComponent(ResticProps)):
    state = JsonState()

    @property
    def initialized(self):
        return self.state.get("initialized")

    @property
    def extra_env(self):
        return dict(
            RESTIC_REPOSITORY=self.props.repository,
            RESTIC_PASSWORD=evaluate(self.props.password),
            **(evaluate(self.props.env) or {}),
        )

    def run(self, *args, **kwargs):
        return run(self.props.restic_binary, *args, **kwargs, extra_env=self.extra_env)

    def refresh(self):
        try:
            self.run("list", "index")
            self.state["initialized"] = True

        except OperationError as error:
            marker = "Is there a repository at the following location?"
            if marker not in error.result.output:
                raise

            self.state["initialized"] = False

        return Result(changed=not self.state["initialized"])

    def deploy(self, dry_run=False):
        if self.initialized:
            return Result()

        if dry_run:
            return Result(changed=True)

        def _run():
            result = self.run("init", "--repository-version=1", capture_output=False)
            self.state["initialized"] = True
            return result

        return Lazy(_run)

    def add_commands(self, cli):
        @cli.forward_command
        def run(args):
            self.run(*args, capture_output=False, exit=True)
