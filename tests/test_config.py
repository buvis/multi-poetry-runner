"""Test configuration manager."""

import tempfile
from pathlib import Path

import pytest
import yaml
from multi_poetry_runner.utils.config import (
    ConfigManager,
    RepositoryConfig,
    WorkspaceConfig,
)


@pytest.fixture
def temp_workspace() -> Path:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        yield workspace_path


@pytest.fixture
def sample_config(temp_workspace) -> Path:
    """Create a sample configuration file."""
    config_data = {
        "version": "1.0",
        "workspace": {"name": "test-workspace", "python_version": "3.11"},
        "repositories": [
            {
                "name": "repo1",
                "url": "https://github.com/test/repo1.git",
                "package_name": "repo1",
                "branch": "main",
                "dependencies": [],
                "source": "pypi",
            },
            {
                "name": "repo2",
                "url": "https://github.com/test/repo2.git",
                "package_name": "repo2",
                "branch": "main",
                "dependencies": ["repo1"],
                "source": "pypi",
            },
        ],
    }

    config_file = temp_workspace / "mpr-config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    return config_file


def test_config_manager_init(temp_workspace) -> None:
    """Test ConfigManager initialization."""
    config_manager = ConfigManager(workspace_root=temp_workspace)
    assert config_manager.workspace_root.resolve() == temp_workspace.resolve()
    assert (
        config_manager.config_file.resolve()
        == (temp_workspace / "mpr-config.yaml").resolve()
    )


def test_load_config(temp_workspace, sample_config) -> None:
    """Test loading configuration from file."""
    config_manager = ConfigManager(
        config_file=sample_config, workspace_root=temp_workspace
    )
    config = config_manager.load_config()

    assert isinstance(config, WorkspaceConfig)
    assert config.name == "test-workspace"
    assert config.python_version == "3.11"
    assert len(config.repositories) == 2

    repo1 = config.repositories[0]
    assert repo1.name == "repo1"
    assert repo1.dependencies == []

    repo2 = config.repositories[1]
    assert repo2.name == "repo2"
    assert repo2.dependencies == ["repo1"]


def test_save_config(temp_workspace) -> None:
    """Test saving configuration to file."""
    config_manager = ConfigManager(workspace_root=temp_workspace)

    repo = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test_repo",
        path=temp_workspace / "repos" / "test-repo",
    )

    workspace_config = WorkspaceConfig(name="test-workspace", repositories=[repo])

    config_manager.save_config(workspace_config)

    # Verify file was created and contains correct data
    config_file = temp_workspace / "mpr-config.yaml"
    assert config_file.exists()

    with open(config_file) as f:
        data = yaml.safe_load(f)

    assert data["workspace"]["name"] == "test-workspace"
    assert len(data["repositories"]) == 1
    assert data["repositories"][0]["name"] == "test-repo"


def test_get_dependency_order(temp_workspace, sample_config) -> None:
    """Test dependency order calculation."""
    config_manager = ConfigManager(
        config_file=sample_config, workspace_root=temp_workspace
    )

    order = config_manager.get_dependency_order()

    # repo1 should come before repo2 since repo2 depends on repo1
    assert order.index("repo1") < order.index("repo2")


def test_get_dependency_order_circular(temp_workspace) -> None:
    """Test circular dependency detection."""
    config_data = {
        "version": "1.0",
        "workspace": {"name": "test-workspace", "python_version": "3.11"},
        "repositories": [
            {
                "name": "repo1",
                "url": "https://github.com/test/repo1.git",
                "package_name": "repo1",
                "dependencies": ["repo2"],
            },
            {
                "name": "repo2",
                "url": "https://github.com/test/repo2.git",
                "package_name": "repo2",
                "dependencies": ["repo1"],
            },
        ],
    }

    config_file = temp_workspace / "mpr-config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    config_manager = ConfigManager(
        config_file=config_file, workspace_root=temp_workspace
    )

    with pytest.raises(ValueError, match="Circular dependency"):
        config_manager.get_dependency_order()


def test_add_repository(temp_workspace, sample_config) -> None:
    """Test adding a repository to configuration."""
    config_manager = ConfigManager(
        config_file=sample_config, workspace_root=temp_workspace
    )

    new_repo = RepositoryConfig(
        name="repo3",
        url="https://github.com/test/repo3.git",
        package_name="repo3",
        path=temp_workspace / "repos" / "repo3",
        dependencies=["repo2"],
    )

    config_manager.add_repository(new_repo)

    # Verify repository was added
    config = config_manager.load_config()
    assert len(config.repositories) == 3

    repo3 = next(r for r in config.repositories if r.name == "repo3")
    assert repo3.dependencies == ["repo2"]


def test_add_duplicate_repository(temp_workspace, sample_config) -> None:
    """Test adding a duplicate repository raises error."""
    config_manager = ConfigManager(
        config_file=sample_config, workspace_root=temp_workspace
    )

    duplicate_repo = RepositoryConfig(
        name="repo1",  # This already exists
        url="https://github.com/test/duplicate.git",
        package_name="duplicate",
        path=temp_workspace / "repos" / "duplicate",
    )

    with pytest.raises(ValueError, match="Repository repo1 already exists"):
        config_manager.add_repository(duplicate_repo)


def test_get_repository(temp_workspace, sample_config) -> None:
    """Test getting a specific repository."""
    config_manager = ConfigManager(
        config_file=sample_config, workspace_root=temp_workspace
    )

    repo = config_manager.get_repository("repo1")
    assert repo is not None
    assert repo.name == "repo1"

    non_existent = config_manager.get_repository("non-existent")
    assert non_existent is None
