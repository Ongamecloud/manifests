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
| `games/` | One manifest per game, named `<id>.yaml`. |
| `tests/<id>/console.yaml` | Real server output used to test each game's console patterns. |
| `schema/manifest.schema.json` | JSON Schema every manifest must pass (schema version 1). |
| `docs/manifest-format.md` | Reference for every key of the format. |
| `templates/example.yaml` | A complete, commented example of a fictional game. Start here. |
| `templates/example-steamcmd.yaml` | The same for a game installed through SteamCMD. |
| `tools/validate.py` | Validator run locally and in CI. |
| `.github/workflows/validate.yml` | CI that validates every manifest on each pull request. |

## Games

| Game | File | Linux | Windows | macOS |
| --- | --- | --- | --- | --- |
| Arma 3 (Steam account that owns the game) | [`games/arma-3.yaml`](games/arma-3.yaml) | yes | yes | no |
| BeamNG.drive (BeamMP server) | [`games/beamng-drive.yaml`](games/beamng-drive.yaml) | yes | yes | no |
| DayZ (Steam account that owns the game) | [`games/dayz.yaml`](games/dayz.yaml) | yes | yes | no |
| Factorio | [`games/factorio.yaml`](games/factorio.yaml) | yes | no | no |
| FiveM (Grand Theft Auto V) | [`games/fivem.yaml`](games/fivem.yaml) | yes | yes | no |
| Garry's Mod | [`games/garrys-mod.yaml`](games/garrys-mod.yaml) | yes | yes | no |
| Minecraft: Bedrock Edition | [`games/minecraft-bedrock.yaml`](games/minecraft-bedrock.yaml) | yes | yes | no |
| Minecraft: Java Edition | [`games/minecraft-java.yaml`](games/minecraft-java.yaml) | yes | yes | yes |
| RedM (Red Dead Redemption 2) | [`games/redm.yaml`](games/redm.yaml) | yes | yes | no |
| Rust | [`games/rust.yaml`](games/rust.yaml) | yes | yes | no |
| Terraria | [`games/terraria.yaml`](games/terraria.yaml) | yes | yes | no |
| Valheim | [`games/valheim.yaml`](games/valheim.yaml) | yes | yes | no |

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

[`docs/manifest-format.md`](docs/manifest-format.md) describes every key.

| Section | Purpose |
| --- | --- |
| `schema_version` | Version of the manifest format. Currently `1`. |
| `id`, `name`, `description` | Stable identifier (matches the file name), display name, short description. |
| `category` | `custom` (installed by its own steps) or `steamcmd` (installed through SteamCMD). |
| `steam` | SteamCMD games only: whether the server downloads anonymously or needs a Steam account that owns the game. |
| `terms` | Optional link to terms the user accepts, such as a server license. |
| `platforms` | One section per supported OS: `linux`, `windows`, `macos`. A missing platform means unsupported. |
| `versions` | Where the version list comes from, the default, and `notify_updates`. |
| `install` | Ordered install steps (bricks): `resolve_version`, `download`, `extract`, `set_executable`, `run_program`, `steamcmd`, `write_file`. |
| `runtime` | Runtimes the game needs, such as a Java version. |
| `launch`, `stop` | How to start the server (program, arguments, arguments added by a boolean setting, working directory) and how to stop it cleanly. |
| `network` | Every port the game uses, including ports derived from another one (game port + 1). |
| `resources` | How the game receives its memory limit, or `none`. |
| `variables` | User settings: name, type (`boolean`, `number`, `text`, `choice`), default, label, bounds. |
| `config_files`, `bindings` | Config files and their format (properties, INI, JSON, YAML, TOML, FiveM/RedM `server.cfg`, DayZ/Arma `.cfg`); where each setting is written. |
| `console` | Regular expressions for server ready, player join and player leave. |
| `backup` | `include` what is worth restoring, `exclude` logs, caches and lock files. |

## Built-in values

These can be used with `{{ ... }}` in install steps, `runtime`, `launch`,
`stop` and binding values; the probe fills them in. The full table, with
units, is in [`docs/manifest-format.md`](docs/manifest-format.md#placeholders).

| Value | Meaning |
| --- | --- |
| `platform` | `linux`, `windows` or `macos`. |
| `probe.kind` | Kind of probe running the server. |
| `server.id`, `server.name` | Identifier and display name of the server. |
| `server.version` | Version the user asked for, or `latest`. |
| `server.ip` | Address the server binds to. |
| `server.port`, `server.port.<name>` | First declared port; port declared with that name. |
| `resources.memory_max_mb`, `resources.memory_min_mb` | Memory to give the game, from the `resources` section. |
| `resources.memory_mb`, `resources.cpu_millis`, `resources.storage_bytes` | Limits applied to the server. |
| `versions.selected.<field>` | Fields of the version picked during install. |
| `variables.<name>` | Current value of a declared variable. |

## Validate locally

CI runs the same commands on every pull request. You need Python 3.9 or
newer.

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/validate.py                         # every manifest
.venv/bin/python tools/validate.py games/my-game.yaml      # one file
.venv/bin/python -m unittest discover -s tools             # the validator's own tests
```

The validator checks the schema, then what a schema cannot: the file name
matches the `id`, bindings refer to declared variables and files,
placeholders use known names, paths stay inside the server directory, and
console patterns match the sample lines in `tests/<id>/console.yaml`.

## Format stability

The probe, the API, the apps and the website all read these files, so
changing the format affects all of them. A change that keeps every existing
manifest valid stays in schema version 1; a breaking change increases
`schema_version` and is discussed in an issue first.

## License

Apache License 2.0. See [LICENSE](LICENSE).
