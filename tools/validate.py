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
    for i, port in enumerate(manifest.get("network", {}).get("ports", [])):
        if port["name"] in ports:
            errors.append(f"network.ports[{i}]: port {port['name']!r} is declared twice")
        ports.append(port["name"])

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
        if fmt in ("properties", "ini"):
            if "key" not in b or "path" in b:
                errors.append(f"{where}: a {fmt} file takes 'key', not 'path'")
            if "section" in b and fmt != "ini":
                errors.append(f"{where}: 'section' is only for INI files")
            target = (b["file"], b.get("section"), b.get("key"))
        else:
            if "path" not in b or "key" in b or "section" in b:
                errors.append(f"{where}: a {fmt} file takes 'path', not 'key' or 'section'")
            target = (b["file"], tuple(b.get("path", [])))
        if "as" in b and fmt in ("properties", "ini"):
            errors.append(f"{where}: 'as' only applies to JSON and YAML files")
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
            for key in ("dest", "archive"):
                if key in step:
                    check_path(f"{where}[{i}].{key}", step[key], errors)
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
        if launch.get("runtime") and launch["runtime"] not in manifest.get("runtime", {}):
            errors.append(f"{where}: runtime {launch['runtime']!r} is not declared in 'runtime'")

    check_console(path, manifest, errors)


def check_console(path, manifest, errors):
    console = manifest.get("console")
    if not console:
        return
    patterns = {}
    for key in CONSOLE_KEYS:
        if key not in console:
            continue
        source = console[key]
        for construct, label in NOT_RE2:
            if construct.search(source):
                errors.append(f"console.{key}: {label} is not supported (RE2 syntax)")
        try:
            pattern = re.compile(source)
        except re.error as e:
            errors.append(f"console.{key}: invalid regular expression: {e}")
            continue
        if key != "ready" and "player" not in pattern.groupindex:
            errors.append(f"console.{key}: needs a group named 'player', like (?P<player>...)")
            continue
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
