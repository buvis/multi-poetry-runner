"""Test workspace manager."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
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
def workspace_manager(config_manager: ConfigManager) -> WorkspaceManager:
    """Create a workspace manager for testing."""

    return WorkspaceManager(config_manager)


def test_initialize_workspace(
    workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test workspace initialization."""
    workspace_manager.initialize_workspace("test-workspace", "3.11")

    # Check that directories were created
    assert (temp_workspace / "repos").exists()
    assert (temp_workspace / "logs").exists()
    assert (temp_workspace / "backups").exists()
    assert (temp_workspace / "scripts").exists()
    assert (temp_workspace / "tests").exists()

    # Check that configuration was created
    config_file = temp_workspace / "mpr-config.yaml"
    assert config_file.exists()

    # Check that Makefile was created
    makefile = temp_workspace / "Makefile"
    assert makefile.exists()

    # Check that .gitignore was created
    gitignore = temp_workspace / ".gitignore"
    assert gitignore.exists()


def test_add_repository(workspace_manager: WorkspaceManager) -> None:
    """Test adding a repository."""
    workspace_manager.initialize_workspace("test-workspace")

    workspace_manager.add_repository(
        "https://github.com/test/test-repo.git", name="test-repo", dependencies=[]
    )

    # Verify repository was added to configuration
    config = workspace_manager.config_manager.load_config()
    assert len(config.repositories) == 1
    assert config.repositories[0].name == "test-repo"


def test_add_repository_auto_name(workspace_manager: WorkspaceManager) -> None:
    """Test adding a repository with auto-detected name."""
    workspace_manager.initialize_workspace("test-workspace")

    workspace_manager.add_repository("https://github.com/test/auto-name-repo.git")

    # Verify repository was added with auto-detected name
    config = workspace_manager.config_manager.load_config()
    assert len(config.repositories) == 1
    assert config.repositories[0].name == "auto-name-repo"


@patch("subprocess.run")
def test_clone_repository(
    mock_subprocess: Any, workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test repository cloning."""
    from multi_poetry_runner.utils.config import RepositoryConfig

    # Mock successful git clone
    mock_subprocess.return_value = MagicMock(returncode=0)

    repo = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test_repo",
        path=temp_workspace / "repos" / "test-repo",
        branch="main",
    )

    workspace_manager._clone_repository(repo)

    # Verify git clone was called
    mock_subprocess.assert_called_once()
    call_args = mock_subprocess.call_args[0][0]
    assert "git" in call_args
    assert "clone" in call_args
    assert repo.url in call_args


@patch("subprocess.run")
def test_setup_poetry_environment(
    mock_subprocess: Any, workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test Poetry environment setup."""
    from multi_poetry_runner.utils.config import RepositoryConfig

    # Create a mock pyproject.toml
    repo_path = temp_workspace / "repos" / "test-repo"
    repo_path.mkdir(parents=True)
    (repo_path / "pyproject.toml").write_text("[tool.poetry]\\nname = 'test'")

    repo = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test_repo",
        path=repo_path,
    )

    # Mock successful poetry install
    mock_subprocess.return_value = MagicMock(returncode=0)

    workspace_manager._setup_poetry_environment(repo, ci_mode=False)

    # Verify poetry install was called
    mock_subprocess.assert_called_once()
    call_args = mock_subprocess.call_args[0][0]
    assert "poetry" in call_args
    assert "install" in call_args


@patch("subprocess.run")
def test_get_status_with_git_info(
    mock_subprocess: Any, workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test getting workspace status with Git branch information."""
    from multi_poetry_runner.utils.config import RepositoryConfig

    workspace_manager.initialize_workspace("test-workspace")

    # Create a mock repository directory with git
    repo_path = temp_workspace / "repos" / "test-repo"
    repo_path.mkdir(parents=True)
    (repo_path / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "test-repo"
version = "1.2.3"

[tool.poetry.dependencies]
python = "^3.11"
"""
    )

    # Add repository to configuration
    repo = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test_repo",
        path=repo_path,
        branch="main",
    )
    workspace_manager.config_manager.add_repository(repo)

    # Mock git commands
    def mock_git_command(*args: Any, **kwargs: Any) -> Any:
        cmd = args[0]

        if "status" in cmd and "--porcelain" in cmd:
            # Mock clean git status
            result = MagicMock()
            result.stdout = ""
            result.returncode = 0

            return result
        elif "rev-parse" in cmd and "--abbrev-ref" in cmd:
            # Mock current branch
            result = MagicMock()
            result.stdout = "feature/test-branch\n"
            result.returncode = 0

            return result

        return MagicMock(returncode=0)

    mock_subprocess.side_effect = mock_git_command

    status = workspace_manager.get_status()

    # Check workspace information includes MPR version
    assert "mpr_version" in status["workspace"]
    assert status["workspace"]["mpr_version"] == "0.1.0"

    # Check repository information includes branch and version
    assert len(status["repositories"]) == 1
    repo_status = status["repositories"][0]
    assert repo_status["name"] == "test-repo"
    assert repo_status["git_branch"] == "feature/test-branch"
    assert repo_status["git_status"] == "clean"
    assert repo_status["package_version"] == "1.2.3"


@patch("subprocess.run")
def test_get_package_version_formats(
    mock_subprocess: Any, workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test getting package version from different pyproject.toml formats."""
    from multi_poetry_runner.utils.config import RepositoryConfig

    workspace_manager.initialize_workspace("test-workspace")

    # Test Poetry format
    repo_path_poetry = temp_workspace / "repos" / "poetry-repo"
    repo_path_poetry.mkdir(parents=True)
    (repo_path_poetry / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "poetry-repo"
version = "2.1.0"
"""
    )

    repo_poetry = RepositoryConfig(
        name="poetry-repo",
        url="https://github.com/test/poetry-repo.git",
        package_name="poetry_repo",
        path=repo_path_poetry,
        branch="main",
    )

    # Test PEP 621 format
    repo_path_pep621 = temp_workspace / "repos" / "pep621-repo"
    repo_path_pep621.mkdir(parents=True)
    (repo_path_pep621 / "pyproject.toml").write_text(
        """
[project]
name = "pep621-repo"
version = "3.0.0"
"""
    )

    repo_pep621 = RepositoryConfig(
        name="pep621-repo",
        url="https://github.com/test/pep621-repo.git",
        package_name="pep621_repo",
        path=repo_path_pep621,
        branch="main",
    )

    # Test dynamic version
    repo_path_dynamic = temp_workspace / "repos" / "dynamic-repo"
    repo_path_dynamic.mkdir(parents=True)
    (repo_path_dynamic / "pyproject.toml").write_text(
        """
[project]
name = "dynamic-repo"
dynamic = ["version"]
"""
    )

    repo_dynamic = RepositoryConfig(
        name="dynamic-repo",
        url="https://github.com/test/dynamic-repo.git",
        package_name="dynamic_repo",
        path=repo_path_dynamic,
        branch="main",
    )

    # Test versions
    assert workspace_manager._get_package_version(repo_poetry) == "2.1.0"
    assert workspace_manager._get_package_version(repo_pep621) == "3.0.0"
    assert workspace_manager._get_package_version(repo_dynamic) == "dynamic"


def test_get_status(workspace_manager: WorkspaceManager, temp_workspace: Path) -> None:
    """Test getting workspace status."""
    workspace_manager.initialize_workspace("test-workspace")

    status = workspace_manager.get_status()

    assert status["workspace"]["name"] == "test-workspace"
    assert Path(status["workspace"]["root"]).resolve() == temp_workspace.resolve()
    assert "repositories" in status


def test_check_dependency_mode(
    workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test dependency mode checking."""
    from multi_poetry_runner.utils.config import RepositoryConfig

    # Create a repository with local dependencies
    repo_path = temp_workspace / "repos" / "test-repo"
    repo_path.mkdir(parents=True)

    pyproject_content = """
[tool.poetry]
name = "test"

[tool.poetry.dependencies]
python = "^3.11"

[tool.poetry.dependencies.other-package]
path = "../other-package"
"""
    (repo_path / "pyproject.toml").write_text(pyproject_content)

    repo = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test_repo",
        path=repo_path,
    )

    mode = workspace_manager._check_dependency_mode(repo)
    assert mode == "local"


def test_check_dependency_modes_all_types(
    workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test dependency mode checking for all types: local, remote, test, mixed."""
    from multi_poetry_runner.utils.config import RepositoryConfig

    # Test local dependencies
    repo_path_local = temp_workspace / "repos" / "local-repo"
    repo_path_local.mkdir(parents=True)
    (repo_path_local / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "local-repo"
[tool.poetry.dependencies]
python = "^3.11"
local-package = {path = "../local-package", develop = true}
"""
    )

    repo_local = RepositoryConfig(
        name="local-repo",
        url="https://github.com/test/local-repo.git",
        package_name="local_repo",
        path=repo_path_local,
    )
    assert workspace_manager._check_dependency_mode(repo_local) == "local"

    # Test remote dependencies
    repo_path_remote = temp_workspace / "repos" / "remote-repo"
    repo_path_remote.mkdir(parents=True)
    (repo_path_remote / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "remote-repo"
[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.28.0"
httpx = {version = "^0.24.0"}
"""
    )

    repo_remote = RepositoryConfig(
        name="remote-repo",
        url="https://github.com/test/remote-repo.git",
        package_name="remote_repo",
        path=repo_path_remote,
    )
    assert workspace_manager._check_dependency_mode(repo_remote) == "remote"

    # Test test-pypi dependencies
    repo_path_test = temp_workspace / "repos" / "test-repo"
    repo_path_test.mkdir(parents=True)
    (repo_path_test / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "test-repo"
[tool.poetry.dependencies]
python = "^3.11"
test-package = {version = "^1.0.0", source = "test-pypi"}

[[tool.poetry.source]]
name = "test-pypi"
url = "https://test.pypi.org/simple/"
priority = "explicit"
"""
    )

    repo_test = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test_repo",
        path=repo_path_test,
    )
    assert workspace_manager._check_dependency_mode(repo_test) == "test"

    # Test mixed dependencies
    repo_path_mixed = temp_workspace / "repos" / "mixed-repo"
    repo_path_mixed.mkdir(parents=True)
    (repo_path_mixed / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "mixed-repo"
[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.28.0"
local-package = {path = "../local-package", develop = true}
"""
    )

    repo_mixed = RepositoryConfig(
        name="mixed-repo",
        url="https://github.com/test/mixed-repo.git",
        package_name="mixed_repo",
        path=repo_path_mixed,
    )
    assert workspace_manager._check_dependency_mode(repo_mixed) == "mixed"

    # Test no dependencies (other than python)
    repo_path_none = temp_workspace / "repos" / "none-repo"
    repo_path_none.mkdir(parents=True)
    (repo_path_none / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "none-repo"
[tool.poetry.dependencies]
python = "^3.11"
"""
    )

    repo_none = RepositoryConfig(
        name="none-repo",
        url="https://github.com/test/none-repo.git",
        package_name="none_repo",
        path=repo_path_none,
    )
    assert workspace_manager._check_dependency_mode(repo_none) == "none"


def test_clean_workspace(
    workspace_manager: WorkspaceManager, temp_workspace: Path
) -> None:
    """Test workspace cleanup."""
    workspace_manager.initialize_workspace("test-workspace")

    # Create some test files
    (temp_workspace / "logs" / "test.log").write_text("test log")
    (temp_workspace / "backups" / "test.backup").write_text("test backup")

    workspace_manager.clean_workspace(force=True)

    # Verify directories are empty
    assert not list((temp_workspace / "logs").iterdir())
    assert not list((temp_workspace / "backups").iterdir())
