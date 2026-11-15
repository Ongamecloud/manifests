"""Tests for tools/validate.py: each case breaks a valid manifest in one
way and checks that the validator reports it.

Run with: python3 -m unittest discover -s tools
"""

import copy
import unittest
from pathlib import Path

import validate

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "games" / "minecraft-java.yaml"
TEMPLATE = ROOT / "templates" / "example.yaml"


class ValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = validate.load_validator()
        cls.game = validate.load_yaml(GAME)
        cls.template = validate.load_yaml(TEMPLATE)

    def errors(self, mutate, base="game", path=GAME):
        manifest = copy.deepcopy(getattr(self, base))
        mutate(manifest)
        return validate.validate(self.validator, path, manifest)

    def assertRejected(self, mutate, needle, **kw):
        errors = self.errors(mutate, **kw)
        self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")

    def test_valid_files(self):
        self.assertEqual(self.errors(lambda m: None), [])
        self.assertEqual(self.errors(lambda m: None, base="template", path=TEMPLATE), [])

    def test_unknown_top_level_key(self):
        self.assertRejected(lambda m: m.update(script="rm -rf /"), "Additional properties")

    def test_unknown_brick(self):
        self.assertRejected(lambda m: m["install"].append({"type": "shell", "command": "x"}), "is not one of")

    def test_unknown_brick_parameter(self):
        self.assertRejected(lambda m: m["install"][2].update(mode="0755"), "Additional properties")

    def test_select_needs_list(self):
        self.assertRejected(lambda m: m["install"][1].update(select="latest"), "'list' is a dependency")

    def test_wrong_schema_version(self):
        self.assertRejected(lambda m: m.update(schema_version=2), "schema_version")

    def test_id_must_match_file_name(self):
        self.assertRejected(lambda m: m.update(id="minecraft"), "does not match the file name")

    def test_platform_without_install(self):
        def mutate(m):
            del m["install"]
            m["platforms"]["linux"] = {"install": [{"type": "write_file", "dest": "a"}]}
        errors = self.errors(mutate)
        self.assertTrue(any("platforms.windows" in e and "'install'" in e for e in errors), errors)

    def test_unknown_platform(self):
        self.assertRejected(lambda m: m["platforms"].update(freebsd={}), "Additional properties")

    def test_unknown_placeholder(self):
        self.assertRejected(lambda m: m["launch"]["arguments"].append("{{ server.dir }}"), "unknown placeholder")

    def test_placeholder_expression(self):
        self.assertRejected(lambda m: m["launch"]["arguments"].append("{{ variables.motd | upper }}"), "names only")

    def test_placeholder_for_undeclared_port(self):
        self.assertRejected(lambda m: m["launch"]["arguments"].append("{{ server.port.query }}"), "unknown placeholder")

    def test_port_placeholder_needs_a_port(self):
        self.assertRejected(lambda m: m.pop("network"), "server.port")

    def test_memory_placeholder_needs_memory_section(self):
        self.assertRejected(lambda m: m.update(resources="none"), "resources.memory_max_mb")

    def test_placeholder_where_not_rendered(self):
        self.assertRejected(lambda m: m.update(name="{{ server.name }}"), "not rendered here")

    def test_path_leaving_server_directory(self):
        self.assertRejected(lambda m: m["install"][3].update(dest="../eula.txt"), "clean relative path")

    def test_absolute_path(self):
        self.assertRejected(lambda m: m["install"][3].update(dest="/etc/passwd"), "does not match")

    def test_windows_reserved_name(self):
        self.assertRejected(lambda m: m["backup"]["include"].append("nul.txt"), "reserved name")

    def test_binding_to_undeclared_variable(self):
        self.assertRejected(
            lambda m: m["bindings"].append({"file": "server.properties", "key": "pvp", "variable": "pvp"}),
            "is not declared",
        )

    def test_binding_to_undeclared_file(self):
        self.assertRejected(
            lambda m: m["bindings"].append({"file": "ops.json", "path": ["a"], "variable": "motd"}),
            "not declared in config_files",
        )

    def test_binding_with_path_on_properties(self):
        self.assertRejected(
            lambda m: m["bindings"].append({"file": "server.properties", "path": ["a"], "variable": "motd"}),
            "takes 'key'",
        )

    def test_binding_written_twice(self):
        self.assertRejected(
            lambda m: m["bindings"].append({"file": "server.properties", "key": "motd", "value": "x"}),
            "already writes",
        )

    def test_choice_default_not_in_choices(self):
        self.assertRejected(lambda m: m["variables"][2].update(default="hardcore"), "not one of the choices")

    def test_number_default_out_of_bounds(self):
        self.assertRejected(lambda m: m["variables"][1].update(default=0), "outside min/max")

    def test_variable_key_of_other_type(self):
        self.assertRejected(lambda m: m["variables"][0].update(min=1), "Unevaluated properties")

    def test_launch_runtime_not_declared(self):
        self.assertRejected(lambda m: m.pop("runtime"), "not declared in 'runtime'")

    def test_launch_needs_runtime_or_executable(self):
        self.assertRejected(lambda m: m["launch"].update(executable="server.jar"), "launch")

    def test_regex_not_re2(self):
        self.assertRejected(lambda m: m["console"].update(ready="(?<=Done) "), "look-behind")

    def test_join_regex_without_player_group(self):
        self.assertRejected(lambda m: m["console"].update(player_join="joined the game$"), "group named 'player'")

    def test_console_samples_must_pass(self):
        self.assertRejected(lambda m: m["console"].update(player_leave=r"(?P<player>\S+) left the game$"), "expected none")


if __name__ == "__main__":
    unittest.main()
