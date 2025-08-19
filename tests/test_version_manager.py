"""Test version management functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import toml

from multi_poetry_runner.core.version_manager import VersionManager


def test_version_manager_initialization(
    version_manager: VersionManager,
    mock_config_manager: Mock,
) -> None:
    """Test VersionManager initialization."""
    assert version_manager is not None
    assert version_manager.config_manager == mock_config_manager


def test_bump_version_patch(
    version_manager: VersionManager,
    temp_workspace: Path,
) -> None:
    """Test bumping version with patch level."""
    # Prepare a repository with an existing pyproject.toml
    repo_path = temp_workspace / "repos" / "repo-a"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Create initial pyproject.toml
    initial_pyproject = {
        "tool": {"poetry": {"name": "test-project", "version": "1.2.3"}}
    }

    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(initial_pyproject, f)

    # Bump version
    version_manager.bump_version(
        repository="repo-a", bump_type="patch", update_dependents=False, validate=False
    )

    # Read updated pyproject.toml
    with open(pyproject_path) as f:
        updated_pyproject = toml.load(f)

    # Check version updated in file
    assert updated_pyproject["tool"]["poetry"]["version"] == "1.2.4"


def test_bump_version_minor(
    version_manager: VersionManager,
    temp_workspace: Path,
) -> None:
    """Test bumping version with minor level."""
    # Prepare a repository with an existing pyproject.toml
    repo_path = temp_workspace / "repos" / "repo-b"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Create initial pyproject.toml
    initial_pyproject = {
        "tool": {"poetry": {"name": "test-project", "version": "1.2.3"}}
    }

    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(initial_pyproject, f)

    # Bump version
    version_manager.bump_version(
        repository="repo-b", bump_type="minor", update_dependents=False, validate=False
    )

    # Read updated pyproject.toml
    with open(pyproject_path) as f:
        updated_pyproject = toml.load(f)

    # Check version updated in file
    assert updated_pyproject["tool"]["poetry"]["version"] == "1.3.0"


def test_bump_version_major(
    version_manager: VersionManager,
    temp_workspace: Path,
) -> None:
    """Test bumping version with major level."""
    # Prepare a repository with an existing pyproject.toml
    repo_path = temp_workspace / "repos" / "repo-c"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Create initial pyproject.toml
    initial_pyproject = {
        "tool": {"poetry": {"name": "test-project", "version": "1.2.3"}}
    }

    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(initial_pyproject, f)

    # Bump version
    version_manager.bump_version(
        repository="repo-c", bump_type="major", update_dependents=False, validate=False
    )

    # Read updated pyproject.toml
    with open(pyproject_path) as f:
        updated_pyproject = toml.load(f)

    # Check version updated in file
    assert updated_pyproject["tool"]["poetry"]["version"] == "2.0.0"


def test_bump_version_invalid_type(
    version_manager: VersionManager,
    temp_workspace: Path,
) -> None:
    """Test bumping version with invalid version type."""
    # Prepare a repository with an existing pyproject.toml
    repo_path = temp_workspace / "repos" / "repo-d"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Create initial pyproject.toml
    initial_pyproject = {
        "tool": {"poetry": {"name": "test-project", "version": "1.2.3"}}
    }

    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(initial_pyproject, f)

    # Attempt to bump version with invalid type
    with pytest.raises(ValueError, match="Invalid version type"):
        version_manager.bump_version(
            repository="repo-d",
            bump_type="invalid_type",
            update_dependents=False,
            validate=False,
        )


def test_get_project_version(
    version_manager: VersionManager,
    temp_workspace: Path,
) -> None:
    """Test retrieving project version."""
    # Prepare a repository with an existing pyproject.toml
    repo_path = temp_workspace / "repos" / "repo-e"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Create initial pyproject.toml
    initial_pyproject = {
        "tool": {"poetry": {"name": "test-project", "version": "1.2.3"}}
    }

    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(initial_pyproject, f)

    # Get version using the method
    version_status = version_manager.get_version_status("repo-e")

    # Verify version
    repo_info = next(
        (repo for repo in version_status["repositories"] if repo["name"] == "repo-e"),
        None,
    )
    assert repo_info is not None
    assert repo_info["current_version"] == "1.2.3"
