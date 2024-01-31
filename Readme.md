# Opslib Contrib

This is a collection of useful components for
[Opsilb](https://github.com/mgax/opslib). They wrap a particular tool,
technology, or service, and are not part of the core Opslib framework.

At the moment, it's a collection of components pulled from my own stack, that
feel stable enough to share. Contributions are most welcome, either for more
integrations, or making things more configurable.

## Setup

```shell
pip install git+https://github.com/mgax/opslib-contrib
```

## Highlights

* [paperless](docs/paperless.md) will set up a
  [Paperless-NGX](https://docs.paperless-ngx.com) service, with optional
  backups.
* [home_assistant](opslib_contrib/home_assistant.py) will set up [Home
  Assistant](https://www.home-assistant.io) server.
* [docker](opslib_contrib/docker.py) is a wrapper for Docker Compose that will,
  among other things, run `docker compose up` only when the configuration
  changes.
* [versions](oslib_contrib/versions.py) and
  [upgradable](oslib_contrib/upgradable.py) help keep apps up to date.
