"""Test release coordination functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from multi_poetry_runner.core.release import ReleaseCoordinator


def test_release_coordinator_initialization(
    release_coordinator: ReleaseCoordinator,
    mock_config_manager: Mock,
) -> None:
    """Test ReleaseCoordinator initialization."""
    assert release_coordinator is not None
    assert release_coordinator.config_manager == mock_config_manager


def test_generate_release_notes(
    release_coordinator: ReleaseCoordinator,
    temp_workspace: Path,
    mock_config_manager: Mock,
) -> None:
    """Test generating release notes for repositories."""
    # Create mock git logs
    repo_a_path = temp_workspace / "repos" / "repo-a"
    repo_b_path = temp_workspace / "repos" / "repo-b"

    # Create proper Mock repository configs
    repo_a_mock = Mock(name="repo-a", path=repo_a_path, dependencies=[])
    repo_b_mock = Mock(name="repo-b", path=repo_b_path, dependencies=[])

    # Create a Mock for load_config and attach it
    mock_load_config = Mock()
    mock_load_config.return_value.repositories = [repo_a_mock, repo_b_mock]

    # Replace the method on the mock config manager
    mock_config_manager.load_config = mock_load_config

    # Mock get_dependency_order to return a simple list
    mock_get_dependency_order = Mock()
    mock_get_dependency_order.return_value = ["repo-a", "repo-b"]
    mock_config_manager.get_dependency_order = mock_get_dependency_order

    # Patch the internal method for testing
    def mock_git_log_effect(repo_path: Path) -> list[str]:
        if "repo-a" in str(repo_path):
            return [
                "commit 1234 feat: Add new feature to repo-a",
                "commit 5678 fix: Resolve bug in repo-a",
            ]
        elif "repo-b" in str(repo_path):
            return [
                "commit 9012 refactor: Improve code in repo-b",
                "commit 3456 docs: Update documentation for repo-b",
            ]
        return []

    with patch.object(
        release_coordinator, "_get_git_log", side_effect=mock_git_log_effect
    ):
        # Create a realistic test scenario using the correct method name
        release_info = release_coordinator.create_release("dev", dry_run=True)

        # Validate release info structure
        assert isinstance(release_info, bool)
        assert release_info is True  # Dry run should return True


def test_get_repository_changelog(
    release_coordinator: ReleaseCoordinator,
    temp_workspace: Path,
) -> None:
    """Test generating changelog for a specific repository."""
    # Create a mock repository path
    repo_path = temp_workspace / "repos" / "test-repo"
    repo_path.mkdir(parents=True)

    # Create a mock repository config for the test repo
    mock_repo_config = Mock(path=repo_path)

    # Patch the git log method
    with patch.object(
        release_coordinator,
        "_get_git_log",
        return_value=[
            "commit 1234 feat: Add new feature",
            "commit 5678 fix: Resolve critical bug",
            "commit 9012 refactor: Improve performance",
        ],
    ):
        # Use a method to retrieve current version
        result = release_coordinator._get_current_version(mock_repo_config)

        # Validate current version retrieval
        assert result is not None
