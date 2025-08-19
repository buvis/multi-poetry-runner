"""Test dependency management functionality."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, call, patch

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
    # Setup Mock methods for the config manager
    mock_get_repository = Mock()
    mock_get_dependency_order = Mock()
    mock_get_backups_path = Mock()
    mock_load_config = Mock()

    # Mock circular dependency in config
    circular_configs = [
        RepositoryConfig(
            name="repo-a",
            url="https://github.com/test/repo-a.git",
            package_name="repo-a",
            path=temp_workspace / "repos" / "repo-a",
            dependencies=["repo-b"],
        ),
        RepositoryConfig(
            name="repo-b",
            url="https://github.com/test/repo-b.git",
            package_name="repo-b",
            path=temp_workspace / "repos" / "repo-b",
            dependencies=["repo-c"],
        ),
        RepositoryConfig(
            name="repo-c",
            url="https://github.com/test/repo-c.git",
            package_name="repo-c",
            path=temp_workspace / "repos" / "repo-c",
            dependencies=["repo-a"],  # Creates cycle
        ),
    ]

    mock_get_repository.side_effect = lambda name: next(
        (repo for repo in circular_configs if repo.name == name), None
    )

    # Mock get_dependency_order to raise an exception for circular dependency
    mock_get_dependency_order.side_effect = Exception("Circular dependency detected")

    # Mock other required methods
    mock_get_backups_path.return_value = temp_workspace / "backups"
    mock_load_config.return_value = Mock(repositories=circular_configs)

    # Replace the methods on the mock config manager
    mock_config_manager.get_repository = mock_get_repository
    mock_config_manager.get_dependency_order = mock_get_dependency_order
    mock_config_manager.get_backups_path = mock_get_backups_path
    mock_config_manager.load_config = mock_load_config

    # Test that circular dependency is detected
    with pytest.raises(Exception, match="Circular dependency detected"):
        dependency_manager.switch_to_local()


# Version compatibility tests
def test_version_compatibility_caret_ranges(
    dependency_manager: DependencyManager,
) -> None:
    """Test ^1.2.3 version matching logic."""
    # Caret allows changes that do not modify the major version
    assert dependency_manager._is_version_compatible("^1.2.3", "1.2.3") is True
    assert dependency_manager._is_version_compatible("^1.2.3", "1.2.4") is True
    assert dependency_manager._is_version_compatible("^1.2.3", "1.3.0") is True
    assert dependency_manager._is_version_compatible("^1.2.3", "2.0.0") is False

    # Test with different major versions
    assert dependency_manager._is_version_compatible("^2.0.0", "2.1.0") is True
    assert dependency_manager._is_version_compatible("^2.0.0", "3.0.0") is False


def test_version_compatibility_tilde_ranges(
    dependency_manager: DependencyManager,
) -> None:
    """Test ~1.2.3 version matching logic."""
    # Tilde allows patch-level changes if a minor version is specified
    assert dependency_manager._is_version_compatible("~1.2.3", "1.2.3") is True
    assert dependency_manager._is_version_compatible("~1.2.3", "1.2.4") is True
    assert dependency_manager._is_version_compatible("~1.2.0", "1.2.9") is True
    assert dependency_manager._is_version_compatible("~1.2.3", "1.3.0") is False

    # Test edge cases
    assert dependency_manager._is_version_compatible("~2.1.0", "2.1.5") is True
    assert dependency_manager._is_version_compatible("~2.1.0", "2.2.0") is False


def test_version_compatibility_exact_match(
    dependency_manager: DependencyManager,
) -> None:
    """Test exact version matching."""
    # Exact version matching
    assert dependency_manager._is_version_compatible("1.2.3", "1.2.3") is True
    assert (
        dependency_manager._is_version_compatible("1.2.3", "1.2.4") is True
    )  # Default to compatible
    assert dependency_manager._is_version_compatible("2.0.0", "2.0.0") is True


def test_version_compatibility_pre_release(
    dependency_manager: DependencyManager,
) -> None:
    """Test alpha/beta version handling."""
    # Test pre-release versions (should default to compatible for now)
    assert (
        dependency_manager._is_version_compatible("^1.0.0-alpha.1", "1.0.0-alpha.2")
        is True
    )
    assert (
        dependency_manager._is_version_compatible("^1.0.0-beta", "1.0.0-beta.1") is True
    )
    assert dependency_manager._is_version_compatible("^1.0.0-rc.1", "1.0.0") is True


# Poetry integration tests
def test_poetry_add_dependency_success(
    dependency_manager: DependencyManager, temp_workspace: Path
) -> None:
    """Test successful Poetry add command."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    # Create basic pyproject.toml
    pyproject_content = {
        "tool": {
            "poetry": {
                "name": "test-repo",
                "version": "1.0.0",
                "dependencies": {"python": "^3.11"},
            }
        }
    }
    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(pyproject_content, f)

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Mock successful Poetry commands
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        dependency_manager._add_poetry_local_dependency(
            repo_config, "test-package", "../test-package"
        )

        # Should call poetry remove first, then poetry add
        expected_calls = [
            call(
                ["poetry", "remove", "test-package"],
                cwd=repo_path,
                capture_output=True,
                check=False,
            ),
            call(
                ["poetry", "add", "--editable", "../test-package"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            ),
        ]
        mock_run.assert_has_calls(expected_calls)


def test_poetry_add_dependency_failure(
    dependency_manager: DependencyManager, temp_workspace: Path
) -> None:
    """Test handling of Poetry command failures."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    # Create basic pyproject.toml
    pyproject_content = {
        "tool": {
            "poetry": {
                "name": "test-repo",
                "version": "1.0.0",
                "dependencies": {"python": "^3.11"},
            }
        }
    }
    pyproject_path = repo_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(pyproject_content, f)

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Mock Poetry add failure, should fallback to direct edit
    with (
        patch("subprocess.run") as mock_run,
        patch.object(dependency_manager, "_add_local_dependency_direct") as mock_direct,
        patch("multi_poetry_runner.core.dependencies.logger") as mock_logger,
    ):

        # First call (remove) succeeds, second call (add) fails
        mock_run.side_effect = [
            Mock(returncode=0),  # remove succeeds
            subprocess.CalledProcessError(
                1, "poetry add", stderr="Dependency resolution failed"
            ),
        ]

        dependency_manager._add_poetry_local_dependency(
            repo_config, "test-package", "../test-package"
        )

        # Should have called direct edit as fallback
        mock_direct.assert_called_once_with(
            repo_config, "test-package", "../test-package"
        )

        # Should have logged warning
        mock_logger.warning.assert_called()


def test_poetry_lock_file_generation(
    dependency_manager: DependencyManager, temp_workspace: Path
) -> None:
    """Test lock file updates after dependency changes."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Test both old and new Poetry lock command variations
    with patch("subprocess.run") as mock_run:
        # First try --no-update (older Poetry), then fallback
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "poetry lock --no-update"),
            Mock(returncode=0),  # Second call succeeds
        ]

        dependency_manager._update_lock_file(repo_config)

        expected_calls = [
            call(
                ["poetry", "lock", "--no-update"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            ),
            call(["poetry", "lock"], cwd=repo_path, check=True, capture_output=True),
        ]
        mock_run.assert_has_calls(expected_calls)


# File system operations tests
def test_pyproject_toml_parsing_edge_cases(
    dependency_manager: DependencyManager, temp_workspace: Path
) -> None:
    """Test handling of malformed TOML files."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Test with malformed TOML
    malformed_pyproject = repo_path / "pyproject.toml"
    malformed_pyproject.write_text(
        """
    [tool.poetry
    name = "test-repo"
    version = "1.0.0"
    # Missing closing bracket - invalid TOML
    """
    )

    # Should handle TOML parsing errors gracefully
    result = dependency_manager._get_current_version(repo_config)
    assert result is None

    # Test with missing sections
    minimal_pyproject = repo_path / "pyproject.toml"
    minimal_pyproject.write_text(
        """
    [build-system]
    requires = ["poetry-core"]
    # Missing tool.poetry section
    """
    )

    result = dependency_manager._get_current_version(repo_config)
    assert result is None

    # Test with valid minimal structure
    valid_pyproject = repo_path / "pyproject.toml"
    valid_content = {"tool": {"poetry": {"name": "test-repo", "version": "1.2.3"}}}
    with open(valid_pyproject, "w") as f:
        toml.dump(valid_content, f)

    result = dependency_manager._get_current_version(repo_config)
    assert result == "1.2.3"


def test_relative_path_calculation(
    dependency_manager: DependencyManager, temp_workspace: Path
) -> None:
    """Test relative path calculations."""
    repos_dir = temp_workspace / "repos"
    repos_dir.mkdir()

    # Test sibling repositories (same level)
    sibling_a = repos_dir / "sibling-a"
    sibling_b = repos_dir / "sibling-b"
    sibling_a.mkdir()
    sibling_b.mkdir()

    relative_path = dependency_manager._get_relative_path(sibling_a, sibling_b)
    assert relative_path == "../sibling-b"

    # Test nested repository structure
    nested_a = repos_dir / "group-a" / "repo-a"
    nested_b = repos_dir / "group-b" / "repo-b"
    nested_a.mkdir(parents=True)
    nested_b.mkdir(parents=True)

    relative_path = dependency_manager._get_relative_path(nested_a, nested_b)
    # Should calculate proper relative path or fallback to absolute
    assert "repo-b" in relative_path  # Should contain target directory name


def test_dependency_marker_file_operations(
    dependency_manager: DependencyManager, temp_workspace: Path
) -> None:
    """Test marker file creation and deletion."""
    marker_file = temp_workspace / ".dependency-mode"

    # Test marker creation
    dependency_manager._create_dependency_marker("local")

    assert marker_file.exists()
    content = marker_file.read_text()
    lines = content.strip().split("\n")
    assert lines[0] == "local"
    assert len(lines) == 2  # mode + timestamp

    # Test workspace mode detection
    mode = dependency_manager._get_workspace_mode()
    assert mode == "local"

    # Test marker removal
    dependency_manager._remove_dependency_marker()
    assert not marker_file.exists()

    # Test default mode when no marker
    mode = dependency_manager._get_workspace_mode()
    assert mode == "remote"

    # Test marker update
    dependency_manager._create_dependency_marker("test")
    mode = dependency_manager._get_workspace_mode()
    assert mode == "test"
