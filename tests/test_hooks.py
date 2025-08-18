"""Test git hooks management functionality."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import toml

from multi_poetry_runner.core.hooks import GitHooksManager


def test_pre_commit_hook_prevents_local_deps(
    hooks_manager: GitHooksManager,
    mock_config_manager: Mock,
    temp_workspace: Path,
) -> None:
    """Test pre-commit hook blocks local dependencies."""
    repos_dir = temp_workspace / "repos"
    repo_a_path = repos_dir / "repo-a"

    # Install hooks first
    hooks_manager.install_hooks()

    # Verify hooks were installed
    pre_commit_hook = repo_a_path / ".git" / "hooks" / "pre-commit"
    assert pre_commit_hook.exists()
    assert pre_commit_hook.stat().st_mode & 0o111  # Check executable

    # Modify pyproject.toml to include local dependency
    pyproject_path = repo_a_path / "pyproject.toml"
    with open(pyproject_path) as f:
        data: dict[str, Any] = toml.load(f)

    # Add local path dependency
    data["tool"]["poetry"]["dependencies"]["local-dep"] = {
        "path": "../some-local-path",
        "develop": True,
    }

    with open(pyproject_path, "w") as f:
        toml.dump(data, f)

    # Try to commit (should be blocked by hook)

    try:
        subprocess.run(["git", "add", "pyproject.toml"], cwd=repo_a_path, check=True)

        # Run pre-commit hook directly
        result = subprocess.run(
            [str(pre_commit_hook)], cwd=repo_a_path, capture_output=True, text=True
        )

        # Hook should fail (non-zero exit code) because of local dependency
        assert result.returncode != 0
        assert (
            "Local path dependencies detected" in result.stderr
            or "path =" in result.stderr
        )

    finally:
        # Clean up - restore original pyproject.toml
        original_data: dict[str, Any] = {
            "tool": {
                "poetry": {
                    "name": "repo-a",
                    "version": "1.0.0",
                    "description": "Test repository",
                    "dependencies": {"python": "^3.11"},
                }
            }
        }
        with open(pyproject_path, "w") as f:
            toml.dump(original_data, f)


# Rest of the test cases follow the same pattern
