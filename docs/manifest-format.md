# Manifest format, schema version 1

This is the reference for every key of a manifest. The machine-readable
version is [`schema/manifest.schema.json`](../schema/manifest.schema.json);
[`tools/validate.py`](../tools/validate.py) applies it together with the
rules a JSON Schema cannot express. [`templates/example.yaml`](../templates/example.yaml)
uses every section, and [`games/minecraft-java.yaml`](../games/minecraft-java.yaml)
is a real manifest.

- [General rules](#general-rules)
- [Probe support](#probe-support)
- [Identity](#identity)
- [Platforms](#platforms)
- [Versions](#versions)
- [Install steps](#install-steps)
- [SteamCMD games](#steamcmd-games)
- [Placeholders](#placeholders)
- [Runtime](#runtime)
- [Launch and stop](#launch-and-stop)
- [Network](#network)
- [Resources](#resources)
- [Variables](#variables)
- [Config files and bindings](#config-files-and-bindings)
- [Console](#console)
- [Backup](#backup)
- [Format changes](#format-changes)

## General rules

- A manifest is one YAML document in `games/<id>.yaml`. It contains data
  only: no scripts, no shell commands, no expressions.
- Unknown keys are an error everywhere, so a typo never goes unnoticed. A key
  written twice in the same mapping is an error too.
- Write booleans as `true` and `false`. Quote strings that contain `{{ ... }}`,
  a colon followed by a space, or start with a special character.
- YAML anchors (`&name` / `*name`) are allowed.
- Every path is relative to the server directory, written with forward
  slashes: no leading `/`, no `..`, no backslash, no drive letter or colon,
  and no Windows reserved name such as `NUL`, `CON` or `COM1`. The same
  manifest then works on every platform, and nothing can reach outside the
  server directory.

## Probe support

Schema version 1 is the contract the probe, the API and the apps implement.
Some sections are already used by the probe today; the others are declared
now so manifests can be written against a stable format, and the probe
picks them up in its next releases. A manifest that uses them is valid
today.

| Section | Used by the probe |
| --- | --- |
| `id`, `name`, `platforms`, `install` (every brick listed below) | Yes |
| `steam` and the `steamcmd` brick | Yes |
| Placeholders `platform`, `probe.kind`, `server.id`, `server.name`, `server.version`, `resources.memory_mb`, `resources.memory_bytes`, `resources.cpu_millis`, `resources.storage_bytes`, `versions.selected.*`, `variables.*` | Yes |
| `schema_version`, `category`, shared `install` with platform overrides | Yes |
| `launch` (with `working_dir` and argument groups), `stop`, `network` (with derived ports) and its placeholders, `variables`, `bindings`, `config_files` (every format), `console` | Yes |
| `runtime`, `resources` and its placeholders, `backup` | Declared as data; probe support comes later |

`description`, `terms` and `versions` are read by the API and the apps, which
build the game library and the version list from them.

## Identity

| Key | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | Always `1` for this version of the format. |
| `id` | yes | Lowercase letters, digits and single hyphens, at most 64 characters. Matches the file name. Never changes once published. |
| `name` | yes | Display name. |
| `description` | no | One or two sentences for the game library. |
| `category` | yes | `custom`: installed by the manifest's own steps. `steamcmd`: distributed through SteamCMD and installed by a [`steamcmd`](#steamcmd) step. |
| `steam` | no | SteamCMD settings, only with `category: steamcmd`. See [SteamCMD games](#steamcmd-games). |
| `terms` | no | `label` and `url` (https) of terms the user accepts when creating the server, such as a server license. The apps show the link before the server is created. |

## Platforms

```yaml
platforms:
  linux: {}
  windows:
    launch:
      executable: bin/server.exe
```

One section per supported platform: `linux`, `windows`, `macos`. A missing
section means the game is **not supported** there; the apps and the website
show it as unavailable. Only declare a platform on which you have run the
server.

An empty section (`{}`) uses the shared values. A section may set `install`
or `launch`; the value replaces the shared key of the same name as a whole
(lists and mappings are not merged). `install` and `launch` are required
either at the top level or in every declared platform.

## Versions

```yaml
versions:
  source:
    url: https://example.com/versions.json
    list: versions
    latest: latest.stable
    where:
      channel: stable
  default: latest
  notify_updates: true
```

| Key | Required | Meaning |
| --- | --- | --- |
| `source` | yes | The JSON document listing versions. `url` (https), `list`, `id`, `latest` and `where` mean the same as in the [`resolve_version`](#resolve_version) step. |
| `default` | yes | `latest`, or a version id. |
| `notify_updates` | yes | `true`: a newer version is offered to the user as a pending update. `false`: choosing a version is a deliberate act (for example Minecraft, where worlds and clients follow the version). |

The version the user picks reaches the install steps as
`{{ server.version }}` (`latest` when they keep the default).

`source` takes only the keys above: not `id_pattern`, `elements` or
`list: "."`. When a vendor's version list needs them, leave `versions` out;
the install steps then resolve the version themselves, and `latest` is
installed (Terraria and BeamNG.drive do this).

## Install steps

`install` is a list of steps run in order. Each step has a `type` naming a
**brick** (an operation implemented once in the probe) and that brick's
parameters. Unknown types and unknown parameters are rejected. If one step
fails, the install stops there.

String parameters may hold [placeholders](#placeholders), except `format` of
`extract`. Number parameters cannot.

### `resolve_version`

Fetches a JSON document and picks a version from it.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `url` | yes | http or https URL of the JSON document. |
| `list` | no | Dotted path to the array of versions, or `.` when the document itself is an array (the GitHub releases API, for example). Without it, the whole document is the selected version. |
| `select` | with `list` | Version id to pick, or `latest`. Usually `"{{ server.version }}"`. |
| `id` | no | Field holding each version's id; `id` by default. |
| `latest` | no | Dotted path to the latest version's id. Without it, `latest` is the first matching entry. |
| `where` | no | Fields an entry must have, with their exact text values. |
| `id_pattern` | no | [RE2](#console) expression with a group named `id`. Entries whose id does not match are skipped, and the id becomes the text of the group. Other named groups become fields. |
| `elements` | no | Named picks inside the selected version: `<name>: { list: <path>, where: { field: value } }` picks the first item of that array whose fields have those values, and exposes its fields as `{{ versions.selected.<name>.<field> }}`. |

Every scalar field of the picked entry becomes
`{{ versions.selected.<dotted.path> }}`, and `{{ versions.selected.id }}` is
always set. A dotted path is keys separated by dots, and a number selects an
array element (`builds.0.url`). A second `resolve_version` replaces the
selection: that is how a manifest follows a vendor that publishes one
document per version (see Minecraft).

An entry may be plain text, such as a file name: it is its own id and is
exposed as `{{ versions.selected.value }}` (`where` and `id` do not apply).
With `id_pattern: '^terraria-server-(?P<id>[0-9]+)\.zip$'` the entry
`terraria-server-1458.zip` has the id `1458` (see Terraria). For a GitHub
release, `elements` picks a file by its name (see BeamNG.drive):

```yaml
- type: resolve_version
  url: https://api.github.com/repos/example/server/releases
  list: "."
  id: tag_name
  select: "{{ server.version }}"
  where: { prerelease: "false" }
  elements:
    asset: { list: assets, where: { name: server-linux-x86_64 } }
- type: download
  url: "{{ versions.selected.asset.browser_download_url }}"
  dest: server
```

A selected version with no matching item fails the step.

### `download`

| Parameter | Required | Meaning |
| --- | --- | --- |
| `url` | yes | http or https URL. |
| `dest` | yes | File path. |
| `checksum` | no | `sha1:<hex>`, `sha256:<hex>` or `sha512:<hex>`. |

The file is moved into place only once complete and verified. Always give a
checksum when the vendor publishes one.

### `extract`

| Parameter | Required | Meaning |
| --- | --- | --- |
| `archive` | yes | Archive path, already in the server directory. |
| `dest` | no | Directory to unpack into; `.` by default. |
| `format` | no | `zip`, `tar.gz` or `tar.xz`; guessed from the archive name. |
| `strip_components` | no | Number of leading path elements to drop from every entry. |
| `subfolder` | no | Extract only the entries below this folder of the archive, without the folder itself. Applied after `strip_components`. |
| `keep` | no | Files, or folders ending with `/`, relative to `dest`, left as they are when they already exist. |
| `keep_existing` | no | `true` to leave every existing file as it is and only add missing ones. Not with `keep`. |
| `skip_outside_links` | no | `true` to skip symbolic links whose target is absolute or leaves `dest`, instead of failing the step. `false` by default. |

With `strip_components: 1` and `subfolder: Linux`, the entry
`1458/Linux/server` becomes `server` and every other entry is skipped; an
archive without that folder fails the step. `keep` lets an update replace a
server's files without overwriting the default configuration files its
archive also ships (`keep: [server.properties]`); a kept file that does not
exist yet is extracted.

Entries that would land outside `dest`, absolute names and special files are
refused. A symbolic link is only created when its target stays inside
`dest`; an archive holding a link that points elsewhere fails the step.

Some archives hold links the server never uses, for example a whole Linux
root file system with links such as `bin/sh -> /bin/busybox` (the Linux
FiveM and RedM builds). With `skip_outside_links: true`, a symbolic link
whose target is absolute or leaves `dest` is not created and the step goes
on; the step's progress says how many links were skipped. A skipped link is
never followed. Every other rule stays: a link inside a linked folder, a
target that is not portable, or a hard link leaving `dest` still fails the
step. Only set it when the server does not need those links.

### `steamcmd`

Installs or updates a Steam app with SteamCMD. Only allowed in a
`category: steamcmd` manifest; see [SteamCMD games](#steamcmd-games).

| Parameter | Required | Meaning |
| --- | --- | --- |
| `app_id` | yes | Steam app id of the dedicated server, written as text (`"896660"`). 1 to 10 digits. |
| `branch` | no | Beta branch: letters, digits, `_`, `.` and `-`, at most 64 characters. The default branch when left out. |
| `branch_password` | with `branch` | Password of a beta branch, when the vendor publishes one. Printable text without spaces, not starting with `+` or `-`. |
| `validate` | no | `true` to check every installed file and repair it. |
| `dest` | no | Directory to install into; `.` by default. |

Running the step again updates the app; SteamCMD only downloads what
changed. `validate` also puts back any file the server ships with that the
owner changed, such as a default config file, so leave it out for servers
configured by editing their own files.

### `write_file`

| Parameter | Required | Meaning |
| --- | --- | --- |
| `dest` | yes | File path. |
| `content` | no | Text to write. Placeholders are rendered. |
| `if_missing` | no | `true` to write the file only when it does not exist yet. |

With `if_missing: true` a default configuration file is created once and
never overwritten by an update, so the owner's edits stay.

### `set_executable`

| Parameter | Required | Meaning |
| --- | --- | --- |
| `paths` | yes | Files to mark as programs, relative to the server directory. |

A program downloaded on its own, or extracted from an archive built on
Windows, has no execute permission on Linux and macOS. The step gives each
file the permissions `rwxr-xr-x`. On Windows it only checks that the files
exist. A missing file, a folder or a symbolic link fails the step.

### `run_program`

Runs a program of the server directory once during the install, for a
server that must prepare something before its first start.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `executable` | yes | Program, relative to the server directory. |
| `arguments` | no | List of arguments, one item each. Placeholders are rendered. |
| `working_dir` | no | Directory it runs in, relative to the server directory. |
| `unless_exists` | no | Path that, when it exists, skips the step. |
| `timeout_seconds` | no | 1 to 3600; 600 by default. |

The manifest names a program and its arguments, never a script: nothing goes
through a shell. The program runs with the same isolation and limits as the
server. An exit code other than 0, or a program still running after
`timeout_seconds`, fails the step. Set `unless_exists` to the file the
program creates, so later installs and updates never run it again over the
owner's data. Factorio creates its first save this way:

```yaml
- type: run_program
  executable: bin/x64/factorio
  arguments: [--create, saves/world.zip]
  unless_exists: saves/world.zip
```

### Missing an operation?

If a game needs something no brick does, do not work around it. Open an
issue describing the operation; the brick is added to the probe first, then
to this format.

## SteamCMD games

Many dedicated servers are distributed through Steam. Their manifest has
`category: steamcmd` and installs through one [`steamcmd`](#steamcmd) step
on every platform:

```yaml
category: steamcmd
steam:
  login: anonymous
install:
  - type: steamcmd
    app_id: "896660"
```

| Key | Required | Meaning |
| --- | --- | --- |
| `steam.login` | with `steam` | `anonymous`: anyone can download the server. `account`: only a Steam account that owns the game can (DayZ and Arma 3, for example). Without a `steam` section the mode is `anonymous`. |

The login mode is part of the manifest, not of the step, so the apps can
tell before anything is installed that the user must log in to Steam on the
probe and own the game. The probe runs SteamCMD from its own directory and
never touches a Steam client installed on the same machine.

The validator also checks that a `steamcmd` step only appears in a
`category: steamcmd` manifest, and that every platform of such a manifest
installs through one. Most SteamCMD servers have no macOS build: leave
`macos` out unless the server really runs there.
[`templates/example-steamcmd.yaml`](../templates/example-steamcmd.yaml) is
a commented starting point.

## Placeholders

`{{ name }}` is replaced by a value. It is plain substitution: no filters,
conditions or functions, and an unknown name is an error. Placeholders are
rendered in `install`, `runtime`, `launch`, `stop`, platform sections and the
`value` of bindings; anywhere else `{{` is an error.

| Name | Value |
| --- | --- |
| `platform` | `linux`, `windows` or `macos`. |
| `probe.kind` | The kind of probe running the server, as told by the API. |
| `server.id`, `server.name` | Identifier and display name of the server. |
| `server.version` | The version the user asked for, or `latest`. |
| `server.ip` | Address the server must bind to. |
| `server.port` | The first port declared in `network.ports`. |
| `server.port.<name>` | The port declared with that name. |
| `resources.memory_max_mb`, `resources.memory_min_mb` | Memory to give the game, in MiB. Only with `resources.memory`; see [Resources](#resources). |
| `resources.memory_mb`, `resources.memory_bytes` | Memory limit applied to the server process, in MiB and bytes (`0`: no limit). |
| `resources.cpu_millis` | CPU limit in thousandths of a core (`0`: no limit). |
| `resources.storage_bytes` | Storage limit in bytes (`0`: no limit). |
| `versions.selected.<path>` | A field of the version picked by the last `resolve_version`. Kept with the server, so `runtime` and `launch` can use it too. |
| `variables.<name>` | Current value of a declared variable, as text. |

There is no placeholder for the server directory: every path is already
relative to it, and the server is launched from it.

## Runtime

```yaml
runtime:
  java:
    version: "{{ versions.selected.javaVersion.majorVersion }}"
```

Runtimes the server needs. The probe installs them in its own folder, never
system-wide. Version 1 knows one runtime:

| Key | Meaning |
| --- | --- |
| `java.version` | Java major version (an integer such as `21`), or a placeholder that renders to one. |

Leave `runtime` out when the server is a native program.

## Launch and stop

```yaml
launch:
  runtime: java
  arguments: ["-Xmx{{ resources.memory_max_mb }}M", -jar, server.jar, nogui]

stop:
  command: stop
  timeout_seconds: 60
```

| Key | Meaning |
| --- | --- |
| `launch.runtime` | Run the main program of a declared runtime (`java`). |
| `launch.executable` | Or run this file from the server directory. Exactly one of the two. |
| `launch.arguments` | Arguments, one list item each, passed as they are: no shell, no quoting, no word splitting. An item may also be a [group](#argument-groups). |
| `launch.environment` | Environment variables for the server process. |
| `launch.working_dir` | Directory the server runs in, relative to the server directory. The server directory by default. |
| `stop.command` | Text written to the server console to stop it cleanly. Without it, the probe asks the process to exit. |
| `stop.timeout_seconds` | Required. After this many seconds the process is terminated. Leave time for the game to save. |

The server runs from its own directory, unless `working_dir` names one of
its folders (for a server that must be started from there). `executable`
stays relative to the server directory either way; relative paths in
arguments are read by the game from its working directory.

### Argument groups

```yaml
launch:
  arguments:
    - -port
    - "{{ server.port }}"
    - when: crossplay        # a boolean variable
      arguments: [-crossplay]
    - unless: public         # added when the variable is false
      arguments: [-password, "{{ variables.password }}"]
```

A group is a mapping with `when` or `unless` (exactly one), naming a
declared `boolean` variable, and `arguments`, a non-empty list of text. Its
arguments are added in place when the variable is `true` (`when`) or
`false` (`unless`). Use it for a flag the game reads by its presence alone,
such as Valheim's `-crossplay`.

## Network

```yaml
network:
  ports:
    - name: game
      protocol: udp
      default: 7777
      label: Game
```

Declare **every** port the game uses, not only the main one: each gets a
public address through the proxy. A port that the game leaves disabled by
default is not declared.

| Key | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Lowercase letters, digits and underscores. Becomes `{{ server.port.<name> }}`. |
| `protocol` | yes | `tcp`, `udp` or `tcp+udp`. |
| `default` | no | The port the game uses out of the box. The probe uses it when it is free; the server may be given another one, so always pass the port through a placeholder. Not set on a derived port. |
| `from` | no | Name of another declared port this one is [derived](#derived-ports) from. |
| `offset` | with `from` | Difference with that port: a whole number from -1000 to 1000, not 0. |
| `label` | no | Name shown in the apps. |

### Derived ports

Some games take one port and choose the others themselves, such as a Steam
query port always at the game port + 1. Declare those as derived:

```yaml
network:
  ports:
    - { name: game, protocol: udp, default: 2456 }
    - { name: query, protocol: udp, from: game, offset: 1 }
```

A derived port has no `default`: its number is always the number of the
port it comes from plus its offset, whatever number that port was given, so
the proxy exposes the port the game really uses. It is derived from a port
that is not derived itself. A result outside 1-65535 fails the start.

## Resources

The user sets one memory limit. The operating system enforces it on the
server process, and the game is told about it, so the two always match.

```yaml
resources:
  memory:
    default_mb: 2048
    minimum_mb: 1536
    reserve_mb: 512
    min_ratio: 0.5
```

| Key | Required | Meaning |
| --- | --- | --- |
| `memory.default_mb` | yes | Limit used when the user sets none. |
| `memory.minimum_mb` | yes | Smallest limit the user may set. |
| `memory.reserve_mb` | no | Part of the limit kept for what the game does not manage itself, such as the Java runtime's own memory. `0` by default. |
| `memory.min_ratio` | no | Ratio between minimum and maximum memory, from just above 0 to 1. `1` by default. |

With a limit of `L` MiB, `{{ resources.memory_max_mb }}` is `L - reserve_mb`
and `{{ resources.memory_min_mb }}` is `memory_max_mb × min_ratio`, rounded
down. Pass them in `launch.arguments` with the unit and syntax the game
expects (`-Xmx{{ resources.memory_max_mb }}M` for Java).

Write `resources: none` when the game takes no memory parameter. The section
is required, so this is always a deliberate choice.

## Variables

Settings the user can change. The configuration form in the apps is
generated from this list; no interface change is needed for a new game.

```yaml
variables:
  - name: max_players
    type: number
    label: Maximum players
    default: 20
    min: 1
    max: 100
    integer: true
```

| Key | Types | Meaning |
| --- | --- | --- |
| `name` | all | Lowercase letters, digits and underscores. Unique. Becomes `{{ variables.<name> }}`. |
| `type` | all | `boolean`, `number`, `text` or `choice`. |
| `label` | all | Field label. |
| `description` | all | Optional help text. |
| `default` | all | Required, of the variable's type. For `choice`, one of the values. |
| `min`, `max` | number | Optional bounds. |
| `integer` | number | `true` when only whole numbers are accepted. |
| `max_length` | text | Optional maximum length. |
| `choices` | choice | List of `value` (text written to the configuration) and `label`. |

A key that does not belong to the type, such as `min` on a text variable, is
an error.

A variable is written somewhere in one of two ways:

- in a configuration file, with a [binding](#config-files-and-bindings);
- on the command line, by using `{{ variables.<name> }}` in
  `launch.arguments`.

## Config files and bindings

```yaml
config_files:
  - path: server.properties
    format: properties

bindings:
  - file: server.properties
    key: max-players
    variable: max_players
  - file: server.properties
    key: server-port
    value: "{{ server.port }}"
```

`config_files` lists the files the probe reads and writes, with their
format. The probe creates a missing file, changes only the keys that are
bound, and reads the file back before writing, so comments, order and a
change made by hand are kept rather than overwritten.

| Format | Files | Addressed by | Values |
| --- | --- | --- | --- |
| `properties` | Java `.properties` (Minecraft) and other `key=value` files | `key` | text |
| `ini` | INI | `key`, `section` | text |
| `json` | JSON | `path` | typed |
| `yaml` | YAML | `path` | typed |
| `toml` | TOML (BeamMP's `ServerConfig.toml`) | `key`, `section` (the table, `a.b` when nested) | typed |
| `cfx` | The `server.cfg` of FiveM and RedM | `key` | typed |
| `bohemia` | The `.cfg` files of DayZ and Arma | `key`, `section` (classes, `Missions.DayZ`) | typed |

- **cfx**: each line is a console command. `key` is the name a line sets,
  optionally with the command that sets it: `sv_maxclients`,
  `set onesync`, `sets sv_projectName`, `endpoint_add_tcp`. A line matches
  whatever command sets the name, ignoring case as the server does, and
  keeps its own command; a missing name is added at the end as `key` says.
  Text is written in double quotes and cannot hold one.
- **bohemia**: entries `name = value;` inside `class Name { ... };`. `key`
  is an entry name and `section` the classes holding it, separated by dots.
  Names ignore case. Text is quoted, booleans are written `1` and `0`.
- **toml**: a missing key is added at the end of its table, a missing table
  at the end of the file.

Each binding writes one value to one place in a declared file:

| Key | Meaning |
| --- | --- |
| `file` | A path declared in `config_files`. |
| `variable` | Write this variable, in its own type (booleans as `true`/`false`). |
| `value` | Or write this fixed text, which may hold placeholders, such as the port the server was given. |
| `as` | For a `value` in a typed format: write it as `text` (default), `number` or `boolean`. |
| `key` | Properties, INI, TOML, cfx and bohemia files: the key, written exactly as in the file. Dots are part of the key. |
| `section` | INI, TOML and bohemia files: the section, table or classes holding the key. Left out, the key is placed at the top of the file. |
| `path` | JSON and YAML files: the keys from the top of the document down to the value, for example `[server, max_players]`. A number selects an array element. |

Two bindings cannot write the same place (in cfx and bohemia files, names
that differ only by case, or by the cfx command, are the same place).

## Console

```yaml
console:
  ready: '^Server started$'
  player_join: '^(?P<player>\w+) joined$'
  player_leave: '^(?P<player>\w+) left$'
```

Regular expressions matched against each line of server output, without its
line ending. They drive what the apps show: when the server is ready, and
who is online.

| Key | Meaning |
| --- | --- |
| `ready` | The line printed when the server accepts players. |
| `player_join` | A player joined. Captures the name in a group named `player`. |
| `player_leave` | A player left. Captures the name in a group named `player`. |

The syntax is [RE2](https://github.com/google/re2/wiki/Syntax), the engine the
probe uses: no look-ahead or look-behind, no back-references. Write named
groups as `(?P<player>...)`. Use single quotes in YAML so backslashes stay as
they are.

Anchor the patterns on something players cannot type, such as the log
prefix, so a chat message like `<Steve> Alex joined the game` does not
count as a join.

Every manifest with a `console` section has sample lines in
`tests/<id>/console.yaml`, copied from real server output:

```yaml
samples:
  - line: '[08:10:15] [Server thread/INFO]: Steve joined the game'
    expect: player_join
    player: Steve
  - line: '[08:10:16] [Server thread/INFO]: <Steve> Alex joined the game'
    expect: none
```

`expect` is `ready`, `player_join`, `player_leave` or `none`; `player` is the
name the pattern must capture. The validator checks that each line matches
exactly the expected pattern, and that every pattern is matched by at least
one sample.

## Backup

```yaml
backup:
  include:
    - world/
    - server.properties
  exclude:
    - world/session.lock
```

`include` lists what is worth restoring: worlds, saves, configuration,
player lists. `exclude` leaves out paths inside them: logs, caches, lock
files. Files the install downloads again (the server itself, libraries) are
not needed. When in doubt, include it: a backup must restore a working
server.

Paths are relative to the server directory. A trailing `/` marks a
directory, `*` matches within one name and `**` any number of directories.

## Format changes

The probe, the API, the apps and the website all read this format. A change
that keeps every existing manifest valid (a new optional key, a new brick)
stays in version 1. A change that would make an existing manifest invalid or
change its meaning increases `schema_version`, and is discussed in an issue
first.
