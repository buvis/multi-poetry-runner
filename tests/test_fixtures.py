import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import pytest

from multi_poetry_runner.core.dependencies import DependencyManager
from multi_poetry_runner.core.hooks import GitHooksManager
from multi_poetry_runner.core.release import ReleaseCoordinator
from multi_poetry_runner.core.testing import ExecutorService
from multi_poetry_runner.core.version_manager import VersionManager
from multi_poetry_runner.core.workspace import WorkspaceManager
from multi_poetry_runner.utils.config import ConfigManager


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        yield workspace_path


@pytest.fixture
def config_manager(temp_workspace: Path) -> ConfigManager:
    """Create a config manager for testing."""
    return ConfigManager(workspace_root=temp_workspace)


@pytest.fixture
def mock_config_manager(temp_workspace: Path) -> Mock:
    """Create a mock ConfigManager with test repositories."""
    mock = Mock(spec=ConfigManager)
    mock.workspace_root = temp_workspace
    return mock


@pytest.fixture
def dependency_manager(mock_config_manager: Mock) -> DependencyManager:
    """Create DependencyManager instance with mocked config."""
    return DependencyManager(mock_config_manager)


@pytest.fixture
def hooks_manager(mock_config_manager: Mock) -> GitHooksManager:
    """Create GitHooksManager instance with mocked config."""
    return GitHooksManager(mock_config_manager)


@pytest.fixture
def release_coordinator(mock_config_manager: Mock) -> ReleaseCoordinator:
    """Create ReleaseCoordinator instance with mocked config."""
    return ReleaseCoordinator(mock_config_manager)


@pytest.fixture
def test_runner(mock_config_manager: Mock) -> ExecutorService:
    """Create ExecutorService instance with mocked config."""
    return ExecutorService(mock_config_manager)


@pytest.fixture
def version_manager(mock_config_manager: Mock) -> VersionManager:
    """Create VersionManager instance with mocked config."""
    return VersionManager(mock_config_manager)


@pytest.fixture
def workspace_manager(config_manager: ConfigManager) -> WorkspaceManager:
    """Create a workspace manager for testing."""
    return WorkspaceManager(config_manager)
