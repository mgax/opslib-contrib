import click
from opslib import Component
from opslib.operations import apply, print_report


class UpgradableMixin(Component):
    def upgrade(self, dry_run=False):
        return apply(self, deploy=True, dry_run=dry_run)

    def add_commands(self, cli):
        @cli.command
        @click.option("-n", "--dry-run", is_flag=True)
        def upgrade(dry_run):
            print_report(self.upgrade(dry_run=dry_run))
