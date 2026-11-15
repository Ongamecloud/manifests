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
STEAM_GAME = ROOT / "games" / "valheim.yaml"
STEAM_ACCOUNT_GAME = ROOT / "games" / "dayz.yaml"
STEAM_TEMPLATE = ROOT / "templates" / "example-steamcmd.yaml"


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


class SteamTest(unittest.TestCase):
    """The steam section and the steamcmd step."""

    @classmethod
    def setUpClass(cls):
        cls.validator = validate.load_validator()
        cls.game = validate.load_yaml(STEAM_GAME)
        cls.custom = validate.load_yaml(GAME)

    def errors(self, mutate, base="game", path=STEAM_GAME):
        manifest = copy.deepcopy(getattr(self, base))
        mutate(manifest)
        return validate.validate(self.validator, path, manifest)

    def assertRejected(self, mutate, needle, **kw):
        errors = self.errors(mutate, **kw)
        self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")

    def test_valid_files(self):
        self.assertEqual(self.errors(lambda m: None), [])
        account = validate.load_yaml(STEAM_ACCOUNT_GAME)
        self.assertEqual(account["steam"]["login"], "account")
        self.assertEqual(validate.validate(self.validator, STEAM_ACCOUNT_GAME, account), [])
        template = validate.load_yaml(STEAM_TEMPLATE)
        self.assertEqual(validate.validate(self.validator, STEAM_TEMPLATE, template), [])

    def test_steam_section_is_optional(self):
        self.assertEqual(self.errors(lambda m: m.pop("steam")), [])

    def test_unknown_login_mode(self):
        self.assertRejected(lambda m: m["steam"].update(login="guest"), "is not one of")

    def test_login_is_required_in_steam_section(self):
        self.assertRejected(lambda m: m["steam"].pop("login"), "'login' is a required property")

    def test_steam_section_needs_steamcmd_category(self):
        self.assertRejected(lambda m: m.update(steam={"login": "anonymous"}), "'steamcmd' was expected",
                            base="custom", path=GAME)

    def test_steamcmd_step_needs_steamcmd_category(self):
        self.assertRejected(lambda m: m["install"].append({"type": "steamcmd", "app_id": "4020"}),
                            "category must be steamcmd", base="custom", path=GAME)

    def test_steamcmd_manifest_installs_through_steamcmd(self):
        def mutate(m):
            m["platforms"]["linux"]["install"] = [{"type": "write_file", "dest": "a.txt"}]
        self.assertRejected(mutate, "installs through a steamcmd step")

    def test_app_id_is_required(self):
        self.assertRejected(lambda m: m["install"][0].pop("app_id"), "'app_id' is a required property")

    def test_app_id_is_text(self):
        self.assertRejected(lambda m: m["install"][0].update(app_id=896660), "is not of type 'string'")

    def test_app_id_is_numeric(self):
        self.assertRejected(lambda m: m["install"][0].update(app_id="valheim"), "does not match")

    def test_app_id_length(self):
        self.assertRejected(lambda m: m["install"][0].update(app_id="12345678901"), "1 to 10 digits")

    def test_app_id_placeholder(self):
        def mutate(m):
            m["variables"].append({"name": "app", "type": "text", "label": "App", "default": "1"})
            m["install"][0]["app_id"] = "{{ variables.app }}"
        self.assertEqual(self.errors(mutate), [])

    def test_branch_name(self):
        self.assertEqual(self.errors(lambda m: m["install"][0].update(branch="public-test_1.2")), [])
        self.assertRejected(lambda m: m["install"][0].update(branch="-beta"), "not a branch name")
        self.assertRejected(lambda m: m["install"][0].update(branch="my beta"), "does not match")

    def test_branch_password_needs_branch(self):
        self.assertRejected(lambda m: m["install"][0].update(branch_password="letmein"),
                            "'branch' is a dependency")

    def test_branch_password_text(self):
        self.assertRejected(lambda m: m["install"][0].update(branch="beta", branch_password="+quit"),
                            "without spaces")
        self.assertRejected(lambda m: m["install"][0].update(branch="beta", branch_password="a b"),
                            "without spaces")

    def test_unknown_steamcmd_parameter(self):
        self.assertRejected(lambda m: m["install"][0].update(username="me"), "Additional properties")

    def test_dest_stays_inside(self):
        self.assertRejected(lambda m: m["install"][0].update(dest="../other"), "clean relative path")


if __name__ == "__main__":
    unittest.main()
