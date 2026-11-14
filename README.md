# Ongamecloud game manifests

This repository describes, game by game, how a dedicated game server is
installed, launched and configured. Each game is one file, called a
**manifest**.

The Ongamecloud probe (the agent that runs game servers on a PC or a server)
reads these files to install and run a game. The Ongamecloud apps and website
read them too, to build the game library and the settings form for each game.
This repository is the single source of truth for which games exist and how
they behave. Manifests are synced through the user's account, so a new game or
a fix reaches every probe without reinstalling anything.

The repository is public and open to contributions. See
[CONTRIBUTING.md](CONTRIBUTING.md) to add or fix a game.

## Repository layout

| Path | What it contains |
| --- | --- |
| `games/` | One manifest per game, named `<id>.yaml`. Empty for now. |
| `schema/manifest.schema.json` | JSON Schema every manifest must pass. |
| `templates/example.yaml` | A complete, commented example of a fictional game. Start here. |
| `.github/workflows/validate.yml` | CI that validates every manifest against the schema. |

## Manifests contain data, never code

A manifest only declares data. Install steps are a list of **bricks**: each
step has a `type` naming an operation (for example downloading a file or
extracting an archive) that is implemented once in the probe and behaves the
same on Windows, Linux and macOS. A manifest never contains scripts, shell
commands or anything that is executed as-is.

If a game needs an operation no brick provides, the brick is added to the
probe first, and the manifest uses it afterwards.

## File format: YAML

Manifests are written in YAML, and validated against a JSON Schema.

- YAML allows comments, so a manifest can explain why a value is what it is.
- It is easy to read and review in a pull request, with less punctuation than
  JSON.
- Any YAML file is checked with standard JSON Schema tools, so the rules are
  the same for every consumer.

Use the `.yaml` extension, two-space indentation and quote strings that contain
`{{ ... }}` or special characters.

## Manifest sections

| Section | Purpose |
| --- | --- |
| `format_version` | Version of the manifest format. Currently `1`. |
| `id`, `name` | Stable identifier (matches the file name) and display name. |
| `category` | `custom` (installed by its own steps) or `steamcmd` (installed through SteamCMD). |
| `platforms` | One section per supported OS: `linux`, `windows`, `macos`. A missing platform means unsupported. |
| `versions` | Where the version list comes from, the default, and `notify_updates`. |
| `install` | Ordered list of install steps (bricks), and `requires_owned_game` for SteamCMD games that need an owning account. |
| `runtime` | Runtimes the game needs, such as a Java version. |
| `launch`, `stop` | How to start the server and how to stop it cleanly. |
| `network` | Network binding and every port the game uses. |
| `resources` | How the game receives its memory and CPU limits, or `none`. |
| `variables` | User settings: name, type (`boolean`, `number`, `text`, `choice`), default, label, bounds. |
| `bindings` | Where each variable is written: launch argument, properties key, JSON/YAML/INI path. |
| `config_files` | Config files the probe reads and writes, and their format. |
| `console` | Regular expressions for server ready, player join and player leave. |
| `backup` | `include` what is worth restoring, `exclude` logs and caches. |

The schema is a first skeleton: it fixes these top-level sections and checks a
few key fields. The inside of most sections will be specified in later
versions. `templates/example.yaml` shows the current shape of each one.

## Built-in values

These can be used in any string with `{{ ... }}`; the probe fills them in.

| Value | Meaning |
| --- | --- |
| `server.ip` | Address the server binds to. |
| `server.port` | First declared port. |
| `server.port.<name>` | Port declared under `network.ports` with that name. |
| `server.id`, `server.name` | Identifier and display name of the server. |
| `server.dir` | Folder the server is installed in. |
| `resources.memory_max`, `resources.memory_min` | Memory limits chosen by the user. |
| `resources.cpu`, `resources.disk` | CPU and disk limits. |
| `versions.selected.*` | Fields of the version the user selected. |
| `variables.<name>` | Current value of a declared variable. |
| `platform` | `linux`, `windows` or `macos`. |
| `probe.kind` | Kind of probe running the server. |

## Validate locally

CI runs the same commands on every pull request. You need Python 3.

```sh
python3 -m venv .venv
.venv/bin/pip install check-jsonschema==0.29.4
.venv/bin/check-jsonschema --check-metaschema schema/manifest.schema.json
find games templates -type f \( -name '*.yaml' -o -name '*.yml' \) -print0 \
  | xargs -0 .venv/bin/check-jsonschema --schemafile schema/manifest.schema.json
```

## Format stability

The probe, the apps and the website all read these files, so changing the
format affects all of them. Changes to the schema are made carefully, and a
breaking change increases `format_version`.

## License

Apache License 2.0. See [LICENSE](LICENSE).
