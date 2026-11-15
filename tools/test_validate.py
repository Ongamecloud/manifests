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
TERRARIA = ROOT / "games" / "terraria.yaml"
FACTORIO = ROOT / "games" / "factorio.yaml"
BEAMNG = ROOT / "games" / "beamng-drive.yaml"
DAYZ = ROOT / "games" / "dayz.yaml"
ARMA = ROOT / "games" / "arma-3.yaml"
BEDROCK = ROOT / "games" / "minecraft-bedrock.yaml"
FIVEM = ROOT / "games" / "fivem.yaml"
REDM = ROOT / "games" / "redm.yaml"


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


class CustomCoreTest(unittest.TestCase):
    """The bricks, launch and network keys and config formats added for the
    custom cores."""

    @classmethod
    def setUpClass(cls):
        cls.validator = validate.load_validator()
        cls.files = {p: validate.load_yaml(p) for p in (TERRARIA, FACTORIO, BEAMNG, DAYZ, ARMA, BEDROCK, FIVEM, REDM, STEAM_GAME, TEMPLATE)}

    def errors(self, path, mutate):
        manifest = copy.deepcopy(self.files[path])
        mutate(manifest)
        return validate.validate(self.validator, path, manifest)

    def assertRejected(self, path, mutate, needle):
        errors = self.errors(path, mutate)
        self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")

    def test_valid_files(self):
        for path in self.files:
            self.assertEqual(self.errors(path, lambda m: None), [], path.name)

    # resolve_version

    def test_root_array_list(self):
        rv = lambda m: m["platforms"]["linux"]["install"][0]
        self.assertEqual(rv(self.files[TERRARIA])["list"], ".")
        self.assertRejected(TERRARIA, lambda m: rv(m).update(list=".."), "list")

    def test_id_pattern_needs_id_group(self):
        rv = lambda m: m["platforms"]["linux"]["install"][0]
        self.assertRejected(TERRARIA, lambda m: rv(m).update(id_pattern="^terraria-(?P<v>[0-9]+)"), "group named 'id'")
        self.assertRejected(TERRARIA, lambda m: rv(m).update(id_pattern="(?<=x)(?P<id>1)"), "look-behind")
        self.assertRejected(TERRARIA, lambda m: rv(m).update(id_pattern="(?P<id>[0-9]+"), "invalid regular expression")

    def test_id_pattern_needs_list(self):
        self.assertRejected(FACTORIO, lambda m: m["install"][0].update(id_pattern="(?P<id>.+)"), "'list' is a dependency")

    def test_elements(self):
        rv = lambda m: m["platforms"]["linux"]["install"][0]
        self.assertRejected(BEAMNG, lambda m: rv(m)["elements"]["asset"].pop("where"), "'where' is a required property")
        self.assertRejected(BEAMNG, lambda m: rv(m)["elements"].update({"bad name": {"list": "a", "where": {"b": "c"}}}), "does not match")

    # extract, set_executable, write_file, run_program

    def test_extract_keep_or_keep_existing(self):
        ex = lambda m: m["platforms"]["windows"]["install"][2]
        self.assertRejected(TERRARIA, lambda m: ex(m).update(keep_existing=True), "should not be valid")
        self.assertEqual(self.errors(TERRARIA, lambda m: ex(m).update(keep_existing=False)), [])

    def test_extract_skip_outside_links(self):
        ex = lambda m: m["platforms"]["linux"]["install"][2]
        self.assertRejected(FIVEM, lambda m: ex(m).update(skip_outside_links="yes"), "is not of type 'boolean'")
        self.assertRejected(FIVEM, lambda m: ex(m).update(skip_outside_link=True), "Additional properties")
        self.assertEqual(self.errors(FIVEM, lambda m: ex(m).update(skip_outside_links=False)), [])
        self.assertEqual(self.errors(TERRARIA, lambda m: m["platforms"]["windows"]["install"][2].update(skip_outside_links=True)), [])

    def test_cfx_linux_extract_skips_outside_links(self):
        # The Linux FXServer archive holds absolute links the server never
        # uses; without the option the probe refuses the whole archive.
        for path in (FIVEM, REDM):
            ex = self.files[path]["platforms"]["linux"]["install"][2]
            self.assertEqual(ex["type"], "extract", path.name)
            self.assertIs(ex.get("skip_outside_links"), True, path.name)

    def test_extract_paths_stay_inside(self):
        ex = lambda m: m["platforms"]["windows"]["install"][2]
        self.assertRejected(TERRARIA, lambda m: ex(m).update(keep=["../serverconfig.txt"]), "clean relative path")
        self.assertRejected(TERRARIA, lambda m: ex(m).update(subfolder="Linux/../.."), "clean relative path")

    def test_set_executable(self):
        se = lambda m: m["platforms"]["linux"]["install"][3]
        self.assertRejected(TERRARIA, lambda m: se(m).update(paths=[]), "should be non-empty")
        self.assertRejected(TERRARIA, lambda m: se(m).update(paths=["nul"]), "reserved name")
        self.assertRejected(TERRARIA, lambda m: se(m).update(mode="0755"), "Additional properties")

    def test_write_file_if_missing_is_boolean(self):
        self.assertRejected(FACTORIO, lambda m: m["install"][3].update(if_missing="yes"), "is not of type 'boolean'")

    def test_run_program(self):
        rp = lambda m: m["install"][4]
        self.assertEqual(rp(self.files[FACTORIO])["type"], "run_program")
        self.assertRejected(FACTORIO, lambda m: rp(m).update(command="sh -c 'x'"), "Additional properties")
        self.assertRejected(FACTORIO, lambda m: rp(m).update(executable="/bin/sh"), "does not match")
        self.assertRejected(FACTORIO, lambda m: rp(m).update(unless_exists="../world.zip"), "clean relative path")
        self.assertRejected(FACTORIO, lambda m: rp(m).update(timeout_seconds=0), "less than the minimum")
        self.assertRejected(FACTORIO, lambda m: rp(m)["arguments"].append("{{ server.dir }}"), "unknown placeholder")

    # launch

    def test_argument_group(self):
        args = lambda m: m["platforms"]["linux"]["launch"]["arguments"]
        group = lambda m: next(a for a in args(m) if isinstance(a, dict))
        self.assertRejected(STEAM_GAME, lambda m: group(m).update(when="pvp"), "is not declared")
        self.assertRejected(STEAM_GAME, lambda m: group(m).update(when="world"), "a text variable")
        self.assertRejected(STEAM_GAME, lambda m: group(m).update(unless="crossplay"), "is valid under each of")
        self.assertRejected(STEAM_GAME, lambda m: group(m).update(arguments=[]), "should be non-empty")
        self.assertRejected(STEAM_GAME, lambda m: group(m)["arguments"].append("{{ server.nope }}"), "unknown placeholder")

    def test_working_dir(self):
        self.assertEqual(self.errors(TEMPLATE, lambda m: m["launch"].update(working_dir="bin")), [])
        self.assertRejected(TEMPLATE, lambda m: m["launch"].update(working_dir="../bin"), "clean relative path")

    # network

    def test_derived_port(self):
        ports = lambda m: m["network"]["ports"]
        self.assertRejected(ARMA, lambda m: ports(m)[1].update(default=2303), "should not be valid")
        self.assertRejected(ARMA, lambda m: ports(m)[1].pop("offset"), "'offset' is a required property")
        self.assertRejected(ARMA, lambda m: ports(m)[1].update(offset=0), "should not be valid")
        self.assertRejected(ARMA, lambda m: ports(m)[1].update(offset=1001), "greater than the maximum")
        self.assertRejected(ARMA, lambda m: ports(m)[0].update(offset=1), "should not be valid")
        self.assertRejected(ARMA, lambda m: ports(m)[1].update({"from": "rcon"}), "is not declared")
        self.assertRejected(ARMA, lambda m: ports(m)[2].update({"from": "query"}), "itself derived")
        self.assertRejected(ARMA, lambda m: ports(m)[1].update({"from": "query"}), "derived from itself")

    # config formats

    def test_cfx_keys(self):
        def with_cfx(m, *bindings):
            m["config_files"].append({"path": "server.cfg", "format": "cfx"})
            m["bindings"] += [dict(file="server.cfg", **b) for b in bindings]
        self.assertEqual(self.errors(DAYZ, lambda m: with_cfx(m, {"key": "set sv_maxclients", "value": "8", "as": "number"})), [])
        self.assertRejected(DAYZ, lambda m: with_cfx(m, {"key": "ensure chat", "value": "x"}), "is a name, or set")
        self.assertRejected(DAYZ, lambda m: with_cfx(m, {"key": "a b c", "value": "x"}), "is a name, or set")
        self.assertRejected(DAYZ, lambda m: with_cfx(m, {"key": "sv_hostname", "section": "x", "value": "x"}), "'section' is only")
        self.assertRejected(DAYZ, lambda m: with_cfx(m, {"key": "sv_hostname", "value": 'a"b'}), "double quote")
        self.assertRejected(DAYZ, lambda m: with_cfx(m, {"key": "sv_maxclients", "value": "1"}, {"key": "SET SV_MAXCLIENTS", "value": "2"}), "already writes")

    def test_bohemia_keys(self):
        b = lambda m: m["bindings"]
        self.assertRejected(DAYZ, lambda m: b(m).append({"file": "serverDZ.cfg", "key": "HOSTNAME", "value": "x"}), "already writes")
        self.assertRejected(DAYZ, lambda m: b(m).append({"file": "serverDZ.cfg", "key": "motd[]", "value": "x"}), "not an entry name")
        self.assertRejected(DAYZ, lambda m: b(m).append({"file": "serverDZ.cfg", "section": "Missions..DayZ", "key": "x", "value": "x"}), "class names")
        self.assertRejected(DAYZ, lambda m: b(m).append({"file": "serverDZ.cfg", "path": ["x"], "value": "x"}), "takes 'key'")

    def test_toml_keys(self):
        b = lambda m: m["bindings"]
        self.assertRejected(BEAMNG, lambda m: b(m).append({"file": "ServerConfig.toml", "path": ["General", "Debug"], "value": "x"}), "takes 'key'")
        self.assertRejected(BEAMNG, lambda m: b(m).append({"file": "ServerConfig.toml", "section": "General", "key": "Name", "value": "x"}), "already writes")
        self.assertEqual(self.errors(BEAMNG, lambda m: b(m).append({"file": "ServerConfig.toml", "section": "Misc", "key": "Name", "value": "x"})), [])

    def test_as_on_text_formats(self):
        self.assertRejected(TERRARIA, lambda m: m["bindings"][0].update({"as": "text"}), "hold text only")

    def test_unknown_format(self):
        self.assertRejected(DAYZ, lambda m: m["config_files"][0].update(format="xml"), "is not one of")


if __name__ == "__main__":
    unittest.main()
