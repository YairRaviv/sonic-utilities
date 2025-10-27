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

    def test_show_global(self):
        # Provide CONFIG_DB with a pre-set global entry
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "global")
        db = Db()
        runner = CliRunner()
        result = runner.invoke(
            show.cli.commands["switch-fast-linkup"].commands["global"],
            [], obj=db
        )
        assert result.exit_code == SUCCESS
        assert "polling_time" in result.output
        assert "guard_time" in result.output
        assert "ber_threshold" in result.output

    def test_show_interfaces_mode(self):
        # Provide CONFIG_DB with PORT table fast_linkup fields
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "ports")
        db = Db()
        runner = CliRunner()
        result = runner.invoke(
            show.cli.commands["interfaces"].commands["fast-linkup-mode"],
            [], obj=db
        )
        assert result.exit_code == SUCCESS
        assert "Ethernet0" in result.output
        assert "true" in result.output or "false" in result.output

    def test_config_interface_fast_linkup_mode(self):
        # Start with a base CONFIG_DB and toggle via CLI
        dbconnector.dedicated_dbs["CONFIG_DB"] = os.path.join(mock_config_path, "ports")
        db = Db()
        runner = CliRunner()

        # Enable -> writes on
        res1 = runner.invoke(
            config.config.commands["interface"].commands["fast-linkup-mode"],
            ["Ethernet0", "enabled"], obj=db
        )
        assert res1.exit_code == SUCCESS
        table = db.cfgdb.get_entry("PORT", "Ethernet0")
        assert table.get("fast_linkup") == "true"
        # Show reflects on
        show1 = runner.invoke(
            show.cli.commands["interfaces"].commands["fast-linkup-mode"],
            [], obj=db
        )
        assert show1.exit_code == SUCCESS
        assert "Ethernet0" in show1.output and "true" in show1.output

        # Disable -> writes off
        res2 = runner.invoke(
            config.config.commands["interface"].commands["fast-linkup-mode"],
            ["Ethernet0", "disabled"], obj=db
        )
        assert res2.exit_code == SUCCESS
        table = db.cfgdb.get_entry("PORT", "Ethernet0")
        assert table.get("fast_linkup") == "false"
        # Show reflects off
        show2 = runner.invoke(
            show.cli.commands["interfaces"].commands["fast-linkup-mode"],
            [], obj=db
        )
        assert show2.exit_code == SUCCESS
        assert "Ethernet0" in show2.output and "false" in show2.output


