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

    @patch(
        "multi_poetry_runner.core.version_manager.VersionManager._record_version_history"
    )
    @patch("builtins.open", new_callable=MagicMock)
    def test_bump_version(self, mock_open: MagicMock) -> None:
        mock_config_manager = MagicMock(spec=ConfigManager)
        mock_repo = MagicMock()
        mock_repo.name = "repo-a"
        mock_repo.path = Path(".")
        mock_config_manager.load_config.return_value.repositories = [mock_repo]
        mock_config_manager.get_repository.return_value = mock_repo
        mock_config_manager.workspace_root = Path(".")

        mock_file = mock_open.return_value.__enter__.return_value
        mock_file.read.return_value = (
            '[tool.poetry]\nname = "repo-a"\nversion = "1.2.3"\n'
        )

        version_manager = VersionManager(config_manager=mock_config_manager)
        version_manager.bump_version("repo-a", "major")

        # Assert that the file was written to with the new version
        mock_open.assert_called_with(Path("./pyproject.toml"), "w")
        mock_file.write.assert_called_with('name = "repo-a"\nversion = "2.0.0"\n')
