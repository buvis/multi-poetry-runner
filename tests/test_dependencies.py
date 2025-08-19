"""Test dependency management functionality."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import toml

from multi_poetry_runner.core.dependencies import DependencyManager
from multi_poetry_runner.utils.config import (
    RepositoryConfig,
)


def test_dependency_cycle_detection(
    dependency_manager: DependencyManager,
    mock_config_manager: Mock,
    temp_workspace: Path,
) -> None:
    """Test that circular dependencies are detected and prevented."""
    # Setup circular dependency: A -> B -> C -> A
    repos_dir = temp_workspace / "repos"

    # Update repo-c to depend on repo-a, creating a cycle
    repo_c_pyproject = repos_dir / "repo-c" / "pyproject.toml"
    with open(repo_c_pyproject) as f:
        pyproject_data = toml.load(f)

    pyproject_data["tool"]["poetry"]["dependencies"]["repo-a"] = "^1.0.0"

    with open(repo_c_pyproject, "w") as f:
        toml.dump(pyproject_data, f)

    # Create a Mock for config manager methods and attach them
    mock_get_repository = Mock()
    mock_get_dependency_order = Mock()

    # Mock circular dependency in config
    circular_configs = [
        RepositoryConfig(
            name="repo-a",
            url="https://github.com/test/repo-a.git",
            package_name="repo-a",
            path=repos_dir / "repo-a",
            dependencies=["repo-b"],
        ),
        RepositoryConfig(
            name="repo-b",
            url="https://github.com/test/repo-b.git",
            package_name="repo-b",
            path=repos_dir / "repo-b",
            dependencies=["repo-c"],
        ),
        RepositoryConfig(
            name="repo-c",
            url="https://github.com/test/repo-c.git",
            package_name="repo-c",
            path=repos_dir / "repo-c",
            dependencies=["repo-a"],  # Creates cycle
        ),
    ]

    mock_get_repository.side_effect = lambda name: next(
        (repo for repo in circular_configs if repo.name == name), None
    )

    # Mock get_dependency_order to raise an exception for circular dependency
    mock_get_dependency_order.side_effect = Exception("Circular dependency detected")

    # Replace the methods on the mock config manager
    mock_config_manager.get_repository = mock_get_repository
    mock_config_manager.get_dependency_order = mock_get_dependency_order

    # Test that circular dependency is detected
    with pytest.raises(Exception, match="Circular dependency detected"):
        dependency_manager.switch_to_local()
