# Contributing

Thank you for helping add games. This guide covers adding a game, fixing one,
and what reviewers check.

Everything in this repository is written in English: file content, comments,
commit messages and pull requests.

## Add a game

1. Pick an `id`: lowercase letters, digits and hyphens, for example
   `my-game`. It is permanent once published, so choose the common name of
   the game.
2. Copy `templates/example.yaml` to `games/<id>.yaml`. The file name must
   match the `id`.
3. Fill in every section. Remove what the game does not use, and keep a short
   comment on any value that is not obvious.
4. Validate it locally (see "Validate locally" in [README.md](README.md)).
5. Open a pull request. Describe how you tested the manifest: on which
   operating systems you ran the server and which version.

### Things to get right

- **Platforms.** Only declare a platform you have actually run the server on.
  A missing platform is fine: the game is shown as unavailable there. Most
  SteamCMD servers do not run on macOS.
- **Ports.** Declare every port the game uses, not only the main one.
- **Resources.** Say which launch argument receives the memory limit and in
  what unit, so the limit the game knows matches the limit the system
  enforces. Use `none` if the game takes no such argument.
- **Versions.** Set `notify_updates: true` when a new server version should be
  offered as an update. Set it to `false` only when choosing a version is a
  deliberate choice for players.
- **SteamCMD games.** Use a single `steamcmd` install step with the app id.
  If the server can only be downloaded by an account that owns the game, set
  `install.requires_owned_game: true`.
- **Console regexes.** Test them against real server output for the ready
  line, a player joining and a player leaving. Include a few sample lines in
  the pull request description.
- **Backup.** Include everything needed to restore the server (configuration,
  saves, worlds). Exclude logs and caches.
- **Sources.** Download only from official, publicly documented sources for
  the game.

### What does not belong in a manifest

- Scripts, shell commands or any code. If no existing brick fits, open an
  issue describing the operation the game needs; it is added to the probe
  first.
- Mods, add-ons and Workshop content. These are handled outside manifests.
- Credentials, private URLs, or anything that is not public.

## Fix a game

Edit the file in `games/` and explain in the pull request what was wrong and
how you checked the fix. Never change an existing `id`.

## Change the format

The schema and the format are read by the probe, the apps and the website.
Open an issue to discuss a format change before sending a pull request. A
change that would make existing manifests invalid increases `format_version`.

## Review

Every pull request needs CI to pass and at least one maintainer approval.
Reviewers check that:

- the file validates and its name matches the `id`;
- the manifest contains data only, no code;
- declared platforms, ports and regexes were tested, as described in the
  pull request;
- download sources are official;
- comments are short, plain and in English.

Small, focused pull requests (one game per pull request) are reviewed fastest.
