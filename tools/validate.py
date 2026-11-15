#!/usr/bin/env python3
"""Validate game manifests.

Usage:
    python3 tools/validate.py [FILE ...]

Without arguments, every manifest in games/ and templates/ is checked.
Each file is validated against schema/manifest.schema.json, then against
the rules a JSON Schema cannot express (references between sections,
placeholder names, portable paths, regular expressions), and its console
patterns are tested against the sample lines in tests/<id>/console.yaml.

Exit status: 0 when every file passes, 1 otherwise.
"""

import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "manifest.schema.json"

# Placeholder names whose set is fixed. They mirror the names the probe
# fills in; see docs/manifest-format.md.
STATIC_NAMES = {
    "platform",
    "probe.kind",
    "server.id",
    "server.name",
    "server.version",
    "server.ip",
    "resources.memory_bytes",
    "resources.memory_mb",
    "resources.cpu_millis",
    "resources.storage_bytes",
}
# Only available when the manifest declares resources.memory.
MEMORY_NAMES = {"resources.memory_max_mb", "resources.memory_min_mb"}

PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}")
NAME = re.compile(r"^[a-z_]+(\.[A-Za-z0-9_-]+)*$")
WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)
# Constructs RE2 (the engine used by the probe) does not support.
NOT_RE2 = [
    (re.compile(r"\(\?[=!]"), "look-ahead"),
    (re.compile(r"\(\?<[=!]"), "look-behind"),
    (re.compile(r"\(\?>"), "atomic group"),
    (re.compile(r"\\[1-9]"), "back-reference"),
    (re.compile(r"[*+?}]\+"), "possessive quantifier"),
]
CONSOLE_KEYS = ("ready", "player_join", "player_leave")
# Config file formats addressed by key, those with sections, and those
# that hold text only. The others (JSON, YAML) are addressed by path.
KEY_FORMATS = ("properties", "ini", "toml", "cfx", "bohemia")
SECTION_FORMATS = ("ini", "toml", "bohemia")
TEXT_FORMATS = ("properties", "ini")
CFX_COMMANDS = ("set", "sets", "setr", "seta")
BOHEMIA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Step parameters holding one path, or a list of paths, inside the server
# directory.
STEP_PATHS = ("dest", "archive", "subfolder", "executable", "working_dir", "unless_exists")
STEP_PATH_LISTS = ("keep", "paths")
# Parameters of the steamcmd brick, as the probe checks them. A branch
# password is passed to SteamCMD as one argument, so it has no spaces and
# does not start with "+" or "-", which SteamCMD would read as a command.
STEAM_APP_ID = re.compile(r"^[0-9]{1,10}$")
STEAM_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
STEAM_BRANCH_PASSWORD = re.compile(r"^[A-Za-z0-9_.!@#$%^&*=~][!-~]{0,127}$")


class UniqueKeyLoader(yaml.SafeLoader):
    """A YAML loader that rejects a key written twice in one mapping, as
    the probe does."""


def _mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node, deep)


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping
)


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        docs = list(yaml.load_all(f, Loader=UniqueKeyLoader))
    if len(docs) != 1:
        raise ValueError("a manifest file holds exactly one YAML document")
    return docs[0]


def walk_strings(value, where):
    """Yield (location, string) for every string inside value."""
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk_strings(item, f"{where}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f"{where}.{key}")


def check_path(where, path, errors):
    static = PLACEHOLDER.sub("x", path)
    for elem in static.rstrip("/").split("/"):
        if elem in ("", ".."):
            errors.append(f"{where}: {path!r} is not a clean relative path")
            return
        if elem.strip("*") and WINDOWS_RESERVED.match(elem):
            errors.append(f"{where}: {path!r} uses the Windows reserved name {elem!r}")


def check_manifest(path, manifest, errors):
    in_games = path.parent.resolve() == (ROOT / "games").resolve()
    if in_games and manifest["id"] != path.stem:
        errors.append(f"id {manifest['id']!r} does not match the file name {path.name!r}")
    if in_games and path.suffix != ".yaml":
        errors.append("manifests in games/ use the .yaml extension")

    variables = {}
    for i, var in enumerate(manifest.get("variables", [])):
        where = f"variables[{i}]"
        if var["name"] in variables:
            errors.append(f"{where}: variable {var['name']!r} is declared twice")
        variables[var["name"]] = var
        if var["type"] == "number":
            lo, hi, default = var.get("min"), var.get("max"), var["default"]
            if lo is not None and hi is not None and lo > hi:
                errors.append(f"{where}: min is greater than max")
            if (lo is not None and default < lo) or (hi is not None and default > hi):
                errors.append(f"{where}: default {default} is outside min/max")
            if var.get("integer") and default != int(default):
                errors.append(f"{where}: default must be a whole number")
        if var["type"] == "choice":
            values = [c["value"] for c in var["choices"]]
            if len(set(values)) != len(values):
                errors.append(f"{where}: two choices have the same value")
            if var["default"] not in values:
                errors.append(f"{where}: default {var['default']!r} is not one of the choices")
        if var["type"] == "text" and "max_length" in var and len(var["default"]) > var["max_length"]:
            errors.append(f"{where}: default is longer than max_length")

    ports = []
    declared = {p["name"]: p for p in manifest.get("network", {}).get("ports", [])}
    for i, port in enumerate(manifest.get("network", {}).get("ports", [])):
        if port["name"] in ports:
            errors.append(f"network.ports[{i}]: port {port['name']!r} is declared twice")
        ports.append(port["name"])
        base = port.get("from")
        if base is None:
            continue
        if base == port["name"]:
            errors.append(f"network.ports[{i}].from: a port cannot be derived from itself")
        elif base not in declared:
            errors.append(f"network.ports[{i}].from: port {base!r} is not declared")
        elif "from" in declared[base]:
            errors.append(f"network.ports[{i}].from: port {base!r} is itself derived; derive from the port it comes from")

    resources = manifest["resources"]
    memory = resources.get("memory") if isinstance(resources, dict) else None
    if memory and memory["default_mb"] < memory["minimum_mb"]:
        errors.append("resources.memory: default_mb is below minimum_mb")
    if memory and memory.get("reserve_mb", 0) >= memory["minimum_mb"]:
        errors.append("resources.memory: reserve_mb leaves nothing of minimum_mb for the game")

    files = {}
    for i, cf in enumerate(manifest.get("config_files", [])):
        if cf["path"] in files:
            errors.append(f"config_files[{i}]: {cf['path']!r} is declared twice")
        files[cf["path"]] = cf["format"]
        check_path(f"config_files[{i}].path", cf["path"], errors)

    targets = set()
    for i, b in enumerate(manifest.get("bindings", [])):
        where = f"bindings[{i}]"
        fmt = files.get(b["file"])
        if fmt is None:
            errors.append(f"{where}: file {b['file']!r} is not declared in config_files")
            continue
        if "variable" in b and b["variable"] not in variables:
            errors.append(f"{where}: variable {b['variable']!r} is not declared")
        if fmt in KEY_FORMATS:
            if "key" not in b or "path" in b:
                errors.append(f"{where}: a {fmt} file takes 'key', not 'path'")
                continue
            if "section" in b and fmt not in SECTION_FORMATS:
                errors.append(f"{where}: 'section' is only for INI, TOML and bohemia files")
            key, section = b["key"], b.get("section")
            if fmt == "cfx":
                # "set onesync" and "onesync" set the same name; Cfx ignores case.
                fields = key.split()
                if not 1 <= len(fields) <= 2 or (len(fields) == 2 and fields[0].lower() not in CFX_COMMANDS):
                    errors.append(f"{where}.key: {key!r} is a name, or set, sets, setr or seta and a name")
                key = fields[-1].lower() if fields else key
                if '"' in b.get("value", ""):
                    errors.append(f"{where}.value: a cfx file cannot hold a double quote")
            if fmt == "bohemia":
                if not BOHEMIA_NAME.match(key):
                    errors.append(f"{where}.key: {key!r} is not an entry name (letters, digits and _)")
                if section is not None and not all(BOHEMIA_NAME.match(c) for c in section.split(".")):
                    errors.append(f"{where}.section: {section!r} is not a list of class names separated by dots")
                key, section = key.lower(), section.lower() if section else section
            target = (b["file"], section, key)
        else:
            if "path" not in b or "key" in b or "section" in b:
                errors.append(f"{where}: a {fmt} file takes 'path', not 'key' or 'section'")
            target = (b["file"], tuple(b.get("path", [])))
        if "as" in b and fmt in TEXT_FORMATS:
            errors.append(f"{where}: 'as' does not apply to {fmt} files, which hold text only")
        if target in targets:
            errors.append(f"{where}: another binding already writes this key")
        targets.add(target)

    # Placeholders: allowed where the probe renders them, and only with
    # names it knows. Everywhere else "{{" is a mistake.
    rendered = ["install", "runtime", "launch", "stop"]
    rendered_parts = [(s, manifest.get(s)) for s in rendered]
    for name, section in manifest["platforms"].items():
        rendered_parts.append((f"platforms.{name}", section))
    rendered_parts += [
        (f"bindings[{i}].value", b.get("value"))
        for i, b in enumerate(manifest.get("bindings", []))
    ]
    names = set(STATIC_NAMES)
    names |= {f"server.port.{p}" for p in ports}
    if ports:
        names.add("server.port")
    names |= {f"variables.{v}" for v in variables}
    if memory:
        names |= MEMORY_NAMES
    for part, value in rendered_parts:
        for where, text in walk_strings(value, part):
            for raw in PLACEHOLDER.findall(text):
                name = raw.strip()
                if not NAME.match(name):
                    errors.append(f"{where}: {{{{ {name} }}}} is not a name; placeholders hold names only")
                elif name not in names and not name.startswith("versions.selected."):
                    errors.append(f"{where}: unknown placeholder {{{{ {name} }}}}")
            if "{{" in PLACEHOLDER.sub("", text):
                errors.append(f"{where}: unclosed placeholder")
    others = {k: v for k, v in manifest.items() if k not in rendered + ["platforms", "bindings", "console"]}
    others["bindings"] = [{k: v for k, v in b.items() if k != "value"} for b in manifest.get("bindings", [])]
    for where, text in walk_strings(others, "manifest"):
        if "{{" in text:
            errors.append(f"{where}: placeholders are not rendered here")

    step_lists = [("install", manifest.get("install"))]
    step_lists += [(f"platforms.{n}.install", p.get("install")) for n, p in manifest["platforms"].items()]
    for where, steps in step_lists:
        for i, step in enumerate(steps or []):
            at = f"{where}[{i}]"
            for key in STEP_PATHS:
                if key in step:
                    check_path(f"{at}.{key}", step[key], errors)
            for key in STEP_PATH_LISTS:
                for j, item in enumerate(step.get(key, [])):
                    check_path(f"{at}.{key}[{j}]", item, errors)
            # A pattern holding a placeholder is checked by the probe once rendered.
            if "id_pattern" in step and "{{" not in step["id_pattern"]:
                check_regex(f"{at}.id_pattern", step["id_pattern"], "id", errors)
    check_steam(manifest, step_lists, errors)
    for i, item in enumerate(manifest.get("backup", {}).get("include", [])):
        check_path(f"backup.include[{i}]", item, errors)
    for i, item in enumerate(manifest.get("backup", {}).get("exclude", [])):
        check_path(f"backup.exclude[{i}]", item, errors)

    launches = [("launch", manifest.get("launch"))]
    launches += [(f"platforms.{n}.launch", p.get("launch")) for n, p in manifest["platforms"].items()]
    for where, launch in launches:
        if not launch:
            continue
        if "executable" in launch:
            check_path(f"{where}.executable", launch["executable"], errors)
        if "working_dir" in launch:
            check_path(f"{where}.working_dir", launch["working_dir"], errors)
        for i, arg in enumerate(launch.get("arguments", [])):
            if isinstance(arg, str):
                continue
            name = arg.get("when", arg.get("unless"))
            var = variables.get(name)
            if var is None:
                errors.append(f"{where}.arguments[{i}]: variable {name!r} is not declared")
            elif var["type"] != "boolean":
                errors.append(f"{where}.arguments[{i}]: variable {name!r} is a {var['type']} variable; when and unless take a boolean one")
        if launch.get("runtime") and launch["runtime"] not in manifest.get("runtime", {}):
            errors.append(f"{where}: runtime {launch['runtime']!r} is not declared in 'runtime'")

    check_console(path, manifest, errors)


def check_steam(manifest, step_lists, errors):
    """SteamCMD is used by 'steamcmd' manifests only, and each platform of
    such a manifest installs through a steamcmd step. The parameter rules
    are the probe's: each placeholder stands for a plain value, so it is
    replaced by one before the check."""
    is_steam = manifest["category"] == "steamcmd"
    shared = manifest.get("install")
    for name, section in manifest["platforms"].items():
        steps = section.get("install", shared) or []
        uses = any(step["type"] == "steamcmd" for step in steps)
        if uses and not is_steam:
            errors.append(f"platforms.{name}: uses a steamcmd step, so category must be steamcmd")
        if steps and is_steam and not uses:
            errors.append(f"platforms.{name}: a steamcmd manifest installs through a steamcmd step")
    for where, steps in step_lists:
        for i, step in enumerate(steps or []):
            if step["type"] != "steamcmd":
                continue
            at = f"{where}[{i}]"
            if not STEAM_APP_ID.fullmatch(PLACEHOLDER.sub("1", step["app_id"])):
                errors.append(f"{at}.app_id: {step['app_id']!r} is not a Steam app id (1 to 10 digits)")
            if "branch" in step and not STEAM_BRANCH.fullmatch(PLACEHOLDER.sub("x", step["branch"])):
                errors.append(f"{at}.branch: {step['branch']!r} is not a branch name (letters, digits, _ . -; at most 64)")
            if "branch_password" in step and not STEAM_BRANCH_PASSWORD.fullmatch(
                PLACEHOLDER.sub("x", step["branch_password"])
            ):
                errors.append(f"{at}.branch_password: printable text without spaces, not starting with + or -")


def check_console(path, manifest, errors):
    console = manifest.get("console")
    if not console:
        return
    patterns = {}
    for key in CONSOLE_KEYS:
        if key not in console:
            continue
        pattern = check_regex(f"console.{key}", console[key], None if key == "ready" else "player", errors)
        if pattern is not None:
            patterns[key] = pattern

    if path.parent.resolve() != (ROOT / "games").resolve():
        return
    samples_path = ROOT / "tests" / manifest["id"] / "console.yaml"
    if not samples_path.exists():
        errors.append(f"console: sample lines are missing; add tests/{manifest['id']}/console.yaml")
        return
    samples = load_yaml(samples_path).get("samples") or []
    tested = set()
    for i, sample in enumerate(samples):
        line, expect = sample["line"], sample["expect"]
        matched = [k for k, p in patterns.items() if p.search(line)]
        want = [] if expect == "none" else [expect]
        if matched != want:
            errors.append(
                f"{samples_path.relative_to(ROOT)} sample {i + 1}: expected {expect}, "
                f"matched {', '.join(matched) or 'nothing'}: {line!r}"
            )
            continue
        tested.add(expect)
        if expect in ("player_join", "player_leave"):
            got = patterns[expect].search(line).group("player")
            if got != sample.get("player"):
                errors.append(
                    f"{samples_path.relative_to(ROOT)} sample {i + 1}: captured player "
                    f"{got!r}, expected {sample.get('player')!r}"
                )
    for key in patterns:
        if key not in tested:
            errors.append(f"console.{key}: no sample line in {samples_path.relative_to(ROOT)} matches it")


def check_regex(where, source, group, errors):
    """Compile an RE2 expression, which must have the named group when
    group is set. Returns the pattern, or None after reporting a problem."""
    bad = False
    for construct, label in NOT_RE2:
        if construct.search(source):
            errors.append(f"{where}: {label} is not supported (RE2 syntax)")
            bad = True
    try:
        pattern = re.compile(source)
    except re.error as e:
        errors.append(f"{where}: invalid regular expression: {e}")
        return None
    if group and group not in pattern.groupindex:
        errors.append(f"{where}: needs a group named {group!r}, like (?P<{group}>...)")
        return None
    return None if bad else pattern


def load_validator():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(validator, path, manifest):
    """Return the list of problems found in one decoded manifest."""
    errors = []
    schema_errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path))
    for e in schema_errors:
        where = ".".join(str(p) for p in e.absolute_path) or "manifest"
        errors.append(f"{where}: {e.message}")
    if not schema_errors:
        check_manifest(path, manifest, errors)
    return errors


def main(argv):
    validator = load_validator()

    if argv:
        paths = [Path(a) for a in argv]
    else:
        paths = sorted(
            p for d in ("games", "templates") for p in (ROOT / d).glob("*") if p.suffix in (".yaml", ".yml")
        )
    if not paths:
        print("no manifest found")
        return 1

    failed = 0
    for path in paths:
        try:
            shown = path.resolve().relative_to(ROOT)
        except ValueError:
            shown = path
        errors = []
        try:
            manifest = load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as e:
            errors.append(str(e))
            manifest = None
        if manifest is not None:
            errors += validate(validator, path, manifest)
        if errors:
            failed += 1
            print(f"FAIL {shown}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"ok   {shown}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
