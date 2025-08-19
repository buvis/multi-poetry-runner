from pathlib import Path
from unittest.mock import MagicMock

from multi_poetry_runner.core import hooks
from multi_poetry_runner.utils.config import ConfigManager


class TestHooks:
    def test_hooks_with_repository(self) -> None:
        mock_config_manager = MagicMock(spec=ConfigManager)
        mock_repo = MagicMock()
        mock_repo.name = "repo-a"
        mock_repo.path = Path(".")
        mock_config_manager.load_config.return_value.repositories = [mock_repo]
        hooks_manager = hooks.GitHooksManager(config_manager=mock_config_manager)
        hooks_manager.test_hooks()
