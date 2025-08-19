"""Test workspace manager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from multi_poetry_runner.core.workspace import WorkspaceManager


def test_workspace_manager_initialization(
    workspace_manager: WorkspaceManager,
    config_manager: Mock,
) -> None:
    """Test WorkspaceManager initialization."""
    assert workspace_manager is not None
    assert workspace_manager.config_manager == config_manager


def test_workspace_initialization(
    workspace_manager: WorkspaceManager,
    temp_workspace: Path,
) -> None:
    """Test workspace initialization."""
    # Initialize workspace
    workspace_manager.initialize_workspace("test-workspace")

    # Verify workspace structure
    assert (temp_workspace / ".dependency-mode").exists()
    assert (temp_workspace / "repos").exists()
    assert (temp_workspace / "logs").exists()
    assert (temp_workspace / "backups").exists()
    assert (temp_workspace / "scripts").exists()
    assert (temp_workspace / "tests").exists()


def test_workspace_status(
    workspace_manager: WorkspaceManager,
    temp_workspace: Path,
) -> None:
    """Test workspace status retrieval."""
    # Initialize workspace
    workspace_manager.initialize_workspace("test-workspace")

    # Get workspace status
    status = workspace_manager.get_status()

    # Verify status details
    assert isinstance(status, dict)
    assert "workspace" in status
    assert "repositories" in status
    assert "dependency_mode" in status["workspace"]
    assert status["workspace"]["dependency_mode"] in ["remote", "local"]


def test_add_repository(
    workspace_manager: WorkspaceManager,
    temp_workspace: Path,
) -> None:
    """Test adding a repository to the workspace."""
    # Initialize workspace
    workspace_manager.initialize_workspace("test-workspace")

    # Add repository
    workspace_manager.add_repository(
        repo_url="https://github.com/test/new-test-repo.git", name="new-test-repo"
    )

    # Verify repository added
    status = workspace_manager.get_status()
    added_repo = next(
        (
            repo
            for repo in status.get("repositories", [])
            if repo["name"] == "new-test-repo"
        ),
        None,
    )
    assert added_repo is not None
    assert "path" in added_repo
    assert added_repo["path"].endswith("/repos/new-test-repo")


def test_workspace_clean(
    workspace_manager: WorkspaceManager,
    temp_workspace: Path,
) -> None:
    """Test workspace clean operation."""
    # Initialize workspace
    workspace_manager.initialize_workspace("test-workspace")

    # Add some repositories and artifacts
    workspace_manager.add_repository(
        repo_url="https://github.com/test/test-repo.git", name="test-repo"
    )

    # Create some mock artifacts
    logs_dir = temp_workspace / "logs"
    backups_dir = temp_workspace / "backups"
    (logs_dir / "test.log").write_text("Test log")
    (backups_dir / "backup.zip").write_text("Test backup")

    # Clean workspace
    workspace_manager.clean_workspace(force=True)

    # Verify cleanup
    assert logs_dir.exists()
    assert backups_dir.exists()
    assert not any(logs_dir.iterdir())
    assert not any(backups_dir.iterdir())
