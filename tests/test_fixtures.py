import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import pytest
import toml

from multi_poetry_runner.core.dependencies import DependencyManager
from multi_poetry_runner.core.hooks import GitHooksManager
from multi_poetry_runner.core.release import ReleaseCoordinator
from multi_poetry_runner.core.testing import ExecutorService
from multi_poetry_runner.core.version_manager import VersionManager
from multi_poetry_runner.core.workspace import WorkspaceManager
from multi_poetry_runner.utils.config import ConfigManager, RepositoryConfig


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
    """Create a mock ConfigManager with test repositories.

    This fixture creates a comprehensive setup with multiple test repositories
    that can be used across all test files.
    """
    config_manager = Mock(spec=ConfigManager)
    config_manager.workspace_root = temp_workspace

    # Create test repos directory
    repos_dir = temp_workspace / "repos"
    repos_dir.mkdir(exist_ok=True)

    # Create test repositories with comprehensive setup
    repo_names = ["repo-a", "repo-b", "repo-c", "repo-d", "repo-e"]
    repo_configs = []

    for i, repo_name in enumerate(repo_names):
        repo_path = repos_dir / repo_name
        repo_path.mkdir(exist_ok=True)

        # Create basic pyproject.toml
        pyproject_content = {
            "tool": {
                "poetry": {
                    "name": repo_name,
                    "version": "1.0.0",
                    "description": "Test repository",
                    "dependencies": {"python": "^3.11"},
                    "dev-dependencies": {"pytest": "^7.0.0", "pytest-cov": "^4.0.0"},
                }
            }
        }

        pyproject_path = repo_path / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            toml.dump(pyproject_content, f)

        # Create tests directory structure for testing module tests
        tests_dir = repo_path / "tests"
        tests_dir.mkdir(exist_ok=True)

        # Create unit tests directory
        unit_tests_dir = tests_dir / "unit"
        unit_tests_dir.mkdir(exist_ok=True)

        # Create a sample unit test
        unit_test_file = unit_tests_dir / "test_sample.py"
        unit_test_content = f'''
"""Sample unit tests for {repo_name}."""

def test_basic_functionality():
    """Test basic functionality."""
    assert True

def test_calculation():
    """Test some calculation."""
    result = 2 + 2
    assert result == 4

def test_string_operations():
    """Test string operations."""
    text = "hello"
    assert text.upper() == "HELLO"
'''
        unit_test_file.write_text(unit_test_content)

        # Create integration tests directory for some repos
        if i < 3:  # Only first three repos have integration tests
            integration_tests_dir = tests_dir / "integration"
            integration_tests_dir.mkdir(exist_ok=True)

            integration_test_file = integration_tests_dir / "test_integration.py"
            integration_test_content = f'''
"""Integration tests for {repo_name}."""

import pytest
from click.testing import CliRunner
def test_integration_workflow():
    """Test integration workflow."""
    # Simulate some integration test
    assert True

@pytest.mark.asyncio
async def test_async_integration():
    """Test async integration."""
    await asyncio.sleep(0.1)
    assert True
'''
            integration_test_file.write_text(integration_test_content)

        # Set up dependencies based on common patterns
        dependencies = []
        if repo_name == "repo-a":
            dependencies = ["repo-b"]
        elif repo_name == "repo-b":
            dependencies = ["repo-c"]
        elif repo_name == "repo-c":
            dependencies = ["repo-d"]
        # repo-d and repo-e are independent

        repo_config = RepositoryConfig(
            name=repo_name,
            url=f"https://github.com/test/{repo_name}.git",
            package_name=repo_name,
            path=repo_path,
            dependencies=dependencies,
        )
        repo_configs.append(repo_config)

    # Set up mock methods
    config_manager.get_repository.side_effect = lambda name: next(
        (repo for repo in repo_configs if repo.name == name), None
    )
    config_manager.get_dependency_order.return_value = [
        "repo-d",
        "repo-c",
        "repo-b",
        "repo-a",
        "repo-e",
    ]
    config_manager.get_backups_path.return_value = temp_workspace / "backups"

    # Mock config object
    mock_config = Mock()
    mock_config.repositories = repo_configs
    mock_config.name = "test-workspace"
    mock_config.python_version = "3.11"
    config_manager.load_config.return_value = mock_config

    return config_manager


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
