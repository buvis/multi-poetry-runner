import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

from multi_poetry_runner.core.version_manager import VersionManager
from multi_poetry_runner.utils.config import ConfigManager


class TestVersionManager:
    @patch("builtins.open", new_callable=MagicMock)
    def test_get_version_status(self, mock_open: MagicMock) -> None:
        mock_config_manager = MagicMock(spec=ConfigManager)
        mock_repo = MagicMock()
        mock_repo.name = "repo-a"
        mock_repo.path = Path(".")
        mock_config_manager.load_config.return_value.repositories = [mock_repo]

        mock_file = mock_open.return_value.__enter__.return_value
        mock_file.read.return_value = (
            '[tool.poetry]\nname = "repo-a"\nversion = "1.2.3"\n'
        )

        version_manager = VersionManager(config_manager=mock_config_manager)
        status = version_manager.get_version_status()

        assert isinstance(status, dict)
        assert status["repositories"][0]["current_version"] == "1.2.3"

    @patch("subprocess.run")
    @patch(
        "multi_poetry_runner.core.version_manager.VersionManager._record_version_history"
    )
    @patch(
        "multi_poetry_runner.core.version_manager.VersionManager._get_current_version"
    )
    def test_bump_version(
        self,
        mock_get_current_version: MagicMock,
        mock_record_version_history: MagicMock,
        mock_subprocess: MagicMock,
    ) -> None:
        mock_config_manager = MagicMock(spec=ConfigManager)
        mock_repo = MagicMock()
        mock_repo.name = "repo-a"
        mock_repo.path = Path(".")
        mock_config_manager.load_config.return_value.repositories = [mock_repo]
        mock_config_manager.get_repository.return_value = mock_repo
        mock_config_manager.workspace_root = Path(".")

        # Mock _get_current_version to return a specific version
        mock_get_current_version.return_value = "1.2.3"

        # Configure subprocess mock to handle both calls
        mock_subprocess.side_effect = [
            MagicMock(),  # First call: poetry version
            MagicMock(),  # Second call: poetry lock --no-update
        ]

        version_manager = VersionManager(config_manager=mock_config_manager)
        # Call with validate=False to skip validation tests
        result = version_manager.bump_version("repo-a", "major", validate=False)

        # Assert that subprocess.run was called with the correct arguments
        expected_calls = [
            unittest.mock.call(
                ["poetry", "version", "2.0.0"],
                cwd=mock_repo.path,
                check=True,
                capture_output=True,
                text=True,
            ),
            unittest.mock.call(
                ["poetry", "lock", "--no-update"],
                cwd=mock_repo.path,
                capture_output=True,
                check=False,
            ),
        ]
        mock_subprocess.assert_has_calls(expected_calls)

        # Assert that _get_current_version was called
        mock_get_current_version.assert_called_once_with(mock_repo)

        # Assert that _record_version_history was called
        mock_record_version_history.assert_called_once()

        # Assert that the method returned True (success)
        assert result is True
