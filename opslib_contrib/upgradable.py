import click
from opslib import Component
from opslib.operations import AbortOperation, apply, print_report


class UpgradableMixin(Component):
    def upgrade(self, *, dry_run=False, deploy=True):
        return apply(self, deploy=deploy, dry_run=dry_run)

    def add_commands(self, cli):
        @cli.command
        @click.option("-n", "--dry-run", is_flag=True)
        @click.option("--deploy/--no-deploy", default=True)
        def upgrade(dry_run, deploy):
            try:
                results = self.upgrade(dry_run=dry_run, deploy=deploy)

            except AbortOperation:
                # opslib handled and printed the error and then aborted
                pass

            else:
                print_report(results)
