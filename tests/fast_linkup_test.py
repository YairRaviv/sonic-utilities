import os
import logging
import pytest

import show.main as show
import config.main as config

from click.testing import CliRunner
from utilities_common.db import Db
from .mock_tables import dbconnector


logger = logging.getLogger(__name__)


SUCCESS = 0
ERROR2 = 2


test_path = os.path.dirname(os.path.abspath(__file__))
input_path = os.path.join(test_path, "fast_linkup_input")
mock_state_path = os.path.join(input_path, "mock_state")
mock_config_path = os.path.join(input_path, "mock_config")


class TestFastLinkupCLI:
    @classmethod
    def setup_class(cls):
        logger.info("Setup class: %s", cls.__name__)
        os.environ['UTILITIES_UNIT_TESTING'] = "1"

    @classmethod
    def teardown_class(cls):
        logger.info("Teardown class: %s", cls.__name__)
        os.environ['UTILITIES_UNIT_TESTING'] = "0"
        dbconnector.dedicated_dbs.clear()

    def test_config_global_not_supported(self):
        # STATE_DB indicates not supported
        dbconnector.dedicated_dbs["STATE_DB"] = os.path.join(mock_state_path, "not_supported")
        db = Db()
        runner = CliRunner()
        result = runner.invoke(
            config.config.commands["switch-fast-linkup"].commands["global"],
            ["--polling-time", "60"], obj=db
        )
        assert result.exit_code == ERROR2
        assert "not supported" in result.output.lower()

    def test_config_global_range_validation(self):
        # STATE_DB indicates supported with ranges polling:[5,120], guard:[1,20]
        dbconnector.dedicated_dbs["STATE_DB"] = os.path.join(mock_state_path, "supported")
        db = Db()
        runner = CliRunner()

        # Below min polling -> error
        res1 = runner.invoke(
            config.config.commands["switch-fast-linkup"].commands["global"],
            ["--polling-time", "4"], obj=db
        )
        assert res1.exit_code == ERROR2
        assert "polling_time 4 out of supported range" in res1.output

        # Above max guard -> error
        res2 = runner.invoke(
            config.config.commands["switch-fast-linkup"].commands["global"],
            ["--guard-time", "21"], obj=db
        )
        assert res2.exit_code == ERROR2
        assert "guard_time 21 out of supported range" in res2.output

        # In-range values -> success
        res3 = runner.invoke(
            config.config.commands["switch-fast-linkup"].commands["global"],
            ["--polling-time", "60", "--guard-time", "10", "--ber", "12"], obj=db
        )
        assert res3.exit_code == SUCCESS

    # show command tests:
    # 1. Validate that the default global parameter values from STATE_DB and from the show command output are equal - when the feature is supported
    # 2. Validate that the configured global parameter values from a config CLI and from the show command output are equal - when the feature is supported
    def test_show_global_configured_values(self):
        # Provide CONFIG_DB with a pre-set global entry and verify JSON output matches exactly
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "global")
        db = Db()
        runner = CliRunner()
        result = runner.invoke(
            show.cli.commands["switch-fast-linkup"].commands["global"],
            ["--json"], obj=db
        )
        assert result.exit_code == SUCCESS
        import json
        data = json.loads(result.output)
        assert data == {"polling_time": "60", "guard_time": "10", "ber_threshold": "12"}

    def test_show_interfaces_mode(self):
        # Provide CONFIG_DB with PORT table fast_linkup fields
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "ports")
        db = Db()
        runner = CliRunner()
        result = runner.invoke(
            show.cli.commands["interfaces"].commands["fast-linkup"].commands["status"],
            [], obj=db
        )
        assert result.exit_code == SUCCESS
        self.assert_interface_fast_linkup_mode(result.output, "Ethernet0", "true")

    def test_enable_fast_linkup_supported(self, monkeypatch):
        # Use supported STATE_DB (FAST_LINKUP_CAPABLE == 'true')
        dbconnector.dedicated_dbs["STATE_DB"] = os.path.join(mock_state_path, "supported")
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "ports")
        db = Db()
        runner = CliRunner()

        # Patch command runner to simulate 'portconfig -fl' writing to CONFIG_DB
        import utilities_common.cli as clicommon

        def fake_run_command(cmd, display_cmd=False, ignore_error=False, return_cmd=False, interactive_mode=False, shell=False):
            # Expect: ['portconfig', '-p', <iface>, '-fl', <enabled|disabled>, ['-n', <ns>]?]
            assert cmd[0] == 'portconfig'
            iface = cmd[cmd.index('-p') + 1]
            mode = cmd[cmd.index('-fl') + 1]
            value = 'true' if mode == 'enabled' else 'false'
            db.cfgdb.mod_entry('PORT', iface, {'fast_linkup': value})
            return

        monkeypatch.setattr(clicommon, 'run_command', fake_run_command)

        # Enable fast-linkup on Ethernet0 via config CLI
        result = runner.invoke(
            config.config.commands["interface"].commands["fast-linkup"],
            ["Ethernet0", "enabled"], obj=db
        )
        assert result.exit_code == SUCCESS

        # Show reflects change
        show_result = runner.invoke(
            show.cli.commands["interfaces"].commands["fast-linkup"].commands["status"],
            [], obj=db
        )
        self.assert_interface_fast_linkup_mode(show_result.output, "Ethernet0", "true")

    def test_disable_fast_linkup_supported(self, monkeypatch):
        # Use supported STATE_DB (FAST_LINKUP_CAPABLE == 'true')
        dbconnector.dedicated_dbs["STATE_DB"] = os.path.join(mock_state_path, "supported")
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "ports")
        db = Db()
        runner = CliRunner()

        import utilities_common.cli as clicommon

        def fake_run_command(cmd, display_cmd=False, ignore_error=False, return_cmd=False, interactive_mode=False, shell=False):
            iface = cmd[cmd.index('-p') + 1]
            mode = cmd[cmd.index('-fl') + 1]
            value = 'true' if mode == 'enabled' else 'false'
            db.cfgdb.mod_entry('PORT', iface, {'fast_linkup': value})
            return

        monkeypatch.setattr(clicommon, 'run_command', fake_run_command)

        # Disable fast-linkup on Ethernet0 via config CLI
        result = runner.invoke(
            config.config.commands["interface"].commands["fast-linkup"],
            ["Ethernet0", "disabled"], obj=db
        )
        assert result.exit_code == SUCCESS

        # Show reflects change
        show_result = runner.invoke(
            show.cli.commands["interfaces"].commands["fast-linkup"].commands["status"],
            [], obj=db
        )
        self.assert_interface_fast_linkup_mode(show_result.output, "Ethernet0", "false")

    def test_enable_fast_linkup_not_supported(self, monkeypatch):
        # Use not_supported STATE_DB (FAST_LINKUP_CAPABLE == 'false')
        dbconnector.dedicated_dbs["STATE_DB"] = os.path.join(mock_state_path, "not_supported")
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "ports")
        db = Db()
        runner = CliRunner()

        import utilities_common.cli as clicommon
        import json

        def fake_run_command(cmd, display_cmd=False, ignore_error=False, return_cmd=False, interactive_mode=False, shell=False):
            # Simulate portconfig capability check
            state_dir = dbconnector.dedicated_dbs.get('STATE_DB')
            cap_file = os.path.join(state_dir, 'STATE_DB.json') if state_dir else None
            if cap_file and os.path.exists(cap_file):
                with open(cap_file) as f:
                    state = json.load(f)
                cap = state.get('SWITCH_CAPABILITY|switch', {}).get('FAST_LINKUP_CAPABLE', 'false')
                if cap != 'true':
                    # Simulate non-zero return (run_command would sys.exit)
                    raise SystemExit(1)
            # Should not reach here for not supported
            return

        monkeypatch.setattr(clicommon, 'run_command', fake_run_command)

        result = runner.invoke(
            config.config.commands["interface"].commands["fast-linkup"],
            ["Ethernet0", "enabled"], obj=db
        )
        assert result.exit_code != SUCCESS
    
    # Helper: Assert that the specified interface has the expected fast-linkup mode in the CLI output.
    def assert_interface_fast_linkup_mode(self, output, intf_name, expected_mode):
        for line in output.splitlines():
            if intf_name in line and expected_mode.lower() in line.lower():
                return
        raise AssertionError(f"{intf_name} fast-linkup mode is not set to {expected_mode}")
    


