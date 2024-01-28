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
