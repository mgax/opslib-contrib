# Paperless component

[Paperless-NGX](https://docs.paperless-ngx.com)

> **Paperless-ngx** is a _community-supported_ open-source document management
> system that transforms your physical documents into a searchable online
> archive so you can keep, well, _less paper_.

This component wraps the Docker Compose installation of Paperless.

## Setup

Create a file named `stack.py`:

```py
from opslib import Component, Directory, LocalHost, Prop, Stack
from opslib_contrib.paperless import Paperless


class MyPaperless(Component):
    class Props:
        directory = Prop(Directory)
        volumes = Prop(Directory)

    def build(self):
        self.app = Paperless(
            directory=self.props.directory,
            volumes=self.props.volumes,
            env_vars={
                "USERMAP_UID": "1000",
                "USERMAP_GID": "1000",
                "PAPERLESS_TIME_ZONE": "Europe/Bucharest",
                "PAPERLESS_OCR_LANGUAGES": "eng ron",
                "PAPERLESS_OCR_LANGUAGE": "ron",
                "PAPERLESS_OCR_MODE": "skip",
            },
            port="127.0.0.1:8000",
        )


class MyStack(Stack):
    def build(self):
        self.host = LocalHost()
        self.directory = self.host.directory("/opt/apps")
        self.volumes = self.host.directory("/opt/volumes")

        self.paperless = MyPaperless(
            directory=self.directory / "paperless",
            volumes=self.volumes / "paperless",
        )


stack = MyStack(__name__)
```

Review what will be deployed:

```shell
opslib - diff
```

Deploy the stack:

```shell
opslib - deploy
```

Create an admin user:

```shell
opslib paperless.app.compose run exec webserver ./manage.py createsuperuser
```

Then go to http://localhost:8000 and log in.

## Backups

You can set up daily backups using [Restic](https://restic.net), to a [Backblaze
B2](https://www.backblaze.com/cloud-storage) bucket, with
[Healthchecks.io](https://healthchecks.io/about/) monitoring.

Add the following to `stack.py`:

```diff
--- a/stack.py
+++ b/stack.py
@@ -1,4 +1,9 @@
+import os
 from opslib import Component, Directory, LocalHost, Prop, Stack
+from opslib.extras.systemd import SystemdTimerService
+from opslib_contrib.backup_service import BackupPlan, BackupService
+from opslib_contrib.backblaze import Backblaze
+from opslib_contrib.healthchecks import Healthchecks
 from opslib_contrib.paperless import Paperless


@@ -6,6 +11,7 @@ class MyPaperless(Component):
     class Props:
         directory = Prop(Directory)
         volumes = Prop(Directory)
+        backup_service = Prop(BackupService)

     def build(self):
         self.app = Paperless(
@@ -22,6 +28,21 @@ class MyPaperless(Component):
             port="127.0.0.1:8000",
         )

+        self.backup_plan: BackupPlan = self.props.backup_service.create_plan(
+            directory=self.props.directory / "backups",
+            name="marmota-paperless",
+        )
+
+        self.app.backup_to(self.backup_plan)
+
+        self.backup_timer = SystemdTimerService(
+            host=self.props.directory.host.sudo(),
+            name="paperless-backups",
+            exec_start=self.backup_plan.daily.path,
+            on_calendar="02:30",
+            timeout_start_sec="1h",
+        )
+

 class MyStack(Stack):
     def build(self):
@@ -29,9 +50,22 @@ class MyStack(Stack):
         self.directory = self.host.directory("/opt/apps")
         self.volumes = self.host.directory("/opt/volumes")

+        self.backblaze = Backblaze()
+
+        self.healthchecks = Healthchecks(
+            api_key=os.environ["HEALTHCHECKS_API_KEY"],
+        )
+
+        self.backup_service = BackupService(
+            name_prefix="opslibdemo-backups-",
+            backblaze=self.backblaze,
+            healthchecks=self.healthchecks,
+        )
+
         self.paperless = MyPaperless(
             directory=self.directory / "paperless",
             volumes=self.volumes / "paperless",
+            backup_service=self.backup_service,
         )


```

Get API keys for Backblaze and Healthchecks and set them as environment
variables:

```shell
export B2_APPLICATION_KEY_ID=...
export B2_APPLICATION_KEY=...
export HEALTHCHECKS_API_KEY=...
```

Review changes and deploy:

```shell
opslib - diff
opslib - deploy
```

To run a manual backup:

```shell
opslib host run sudo systemctl start paperless-backups
```

To list existing snapshots:

```shell
# Any arguments after `run` are forwarded to the `restic` command.
opslib paperless.backup_plan.repo run snapshots
```
