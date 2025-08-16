"""Test CLI interface."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from multi_poetry_runner.cli import main


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        yield workspace_path


@pytest.fixture
def runner():
    """Create a Click test runner."""

    return CliRunner()


def test_main_help(runner):
    """Test main help command."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Multi-Poetry Runner" in result.output


def test_workspace_init(runner, temp_workspace):
    """Test workspace initialization command."""
    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        assert result.exit_code == 0
        assert "initialized successfully" in result.output


def test_workspace_init_with_python_version(runner, temp_workspace):
    """Test workspace initialization with custom Python version."""
    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            [
                "--workspace",
                str(temp_workspace),
                "workspace",
                "init",
                "test-workspace",
                "--python-version",
                "3.12",
            ],
        )

        assert result.exit_code == 0


@patch("multi_poetry_runner.core.workspace.WorkspaceManager.setup_workspace")
def test_workspace_setup(mock_setup, runner, temp_workspace):
    """Test workspace setup command."""
    # First initialize workspace
    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        # Then test setup
        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "workspace", "setup"]
        )

        mock_setup.assert_called_once()


@patch("multi_poetry_runner.core.workspace.WorkspaceManager.get_status")
def test_workspace_status(mock_status, runner, temp_workspace):
    """Test workspace status command."""
    mock_status.return_value = {
        "workspace": {
            "name": "test-workspace",
            "root": str(temp_workspace),
            "python_version": "3.11",
            "dependency_mode": "remote",
        },
        "repositories": [],
    }

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "workspace", "status"]
        )

        mock_status.assert_called_once()


@patch("multi_poetry_runner.core.dependencies.DependencyManager.switch_to_local")
def test_deps_switch_local(mock_switch, runner, temp_workspace):
    """Test dependency switch to local command."""
    mock_switch.return_value = True

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "deps", "switch", "local"]
        )

        assert result.exit_code == 0
        mock_switch.assert_called_once_with(dry_run=False)


@patch("multi_poetry_runner.core.dependencies.DependencyManager.switch_to_remote")
def test_deps_switch_remote(mock_switch, runner, temp_workspace):
    """Test dependency switch to remote command."""
    mock_switch.return_value = True

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "deps", "switch", "remote"]
        )

        assert result.exit_code == 0
        mock_switch.assert_called_once_with(dry_run=False)


@patch("multi_poetry_runner.core.dependencies.DependencyManager.switch_to_test")
def test_deps_switch_test(mock_switch, runner, temp_workspace):
    """Test dependency switch to test command."""
    mock_switch.return_value = True

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "deps", "switch", "test"]
        )

        assert result.exit_code == 0
        mock_switch.assert_called_once_with(dry_run=False)


def test_deps_switch_dry_run(runner, temp_workspace):
    """Test dependency switch with dry run."""
    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main,
            [
                "--workspace",
                str(temp_workspace),
                "deps",
                "switch",
                "local",
                "--dry-run",
            ],
        )

        # Should not fail even without actual repositories
        assert result.exit_code == 0


@patch("multi_poetry_runner.core.release.ReleaseCoordinator.create_release")
def test_release_create(mock_release, runner, temp_workspace):
    """Test release creation command."""
    mock_release.return_value = True

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "release", "create", "--stage", "dev"],
        )

        assert result.exit_code == 0
        mock_release.assert_called_once()


@patch("multi_poetry_runner.core.testing.TestRunner.run_unit_tests")
def test_test_unit(mock_test, runner, temp_workspace):
    """Test unit test command."""
    mock_test.return_value = True

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "test", "unit"]
        )

        assert result.exit_code == 0
        mock_test.assert_called_once_with(parallel=False, coverage=False)


@patch("multi_poetry_runner.core.testing.TestRunner.run_integration_tests")
def test_test_integration(mock_test, runner, temp_workspace):
    """Test integration test command."""
    mock_test.return_value = True

    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "test", "integration"]
        )

        assert result.exit_code == 0
        mock_test.assert_called_once()


@patch("multi_poetry_runner.core.hooks.GitHooksManager.install_hooks")
def test_hooks_install(mock_install, runner, temp_workspace):
    """Test hooks installation command."""
    with runner.isolated_filesystem():
        runner.invoke(
            main,
            ["--workspace", str(temp_workspace), "workspace", "init", "test-workspace"],
        )

        result = runner.invoke(
            main, ["--workspace", str(temp_workspace), "hooks", "install"]
        )

        assert result.exit_code == 0
        mock_install.assert_called_once_with(force=False)


def test_verbose_flag(runner, temp_workspace):
    """Test verbose flag."""
    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            [
                "--verbose",
                "--workspace",
                str(temp_workspace),
                "workspace",
                "init",
                "test-workspace",
            ],
        )

        assert result.exit_code == 0


def test_config_file_option(runner, temp_workspace):
    """Test custom config file option."""
    config_file = temp_workspace / "custom-config.yaml"
    config_file.write_text(
        """
version: "1.0"
workspace:
  name: "custom-workspace"
  python_version: "3.11"
repositories: []
"""
    )

    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            [
                "--config",
                str(config_file),
                "--workspace",
                str(temp_workspace),
                "workspace",
                "status",
            ],
        )

        # Should work with custom config
        assert result.exit_code == 0
