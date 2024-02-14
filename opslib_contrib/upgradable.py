import click
from opslib import Component
from opslib.operations import apply, print_report


class UpgradableMixin(Component):
    def upgrade(self, *, dry_run=False, deploy=True):
        return apply(self, deploy=deploy, dry_run=dry_run)

    def add_commands(self, cli):
        @cli.command
        @click.option("-n", "--dry-run", is_flag=True)
        @click.option("--deploy/--no-deploy", default=True)
        def upgrade(dry_run, deploy):
            print_report(self.upgrade(dry_run=dry_run, deploy=deploy))
