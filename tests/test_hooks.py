"""Test git hooks management functionality."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import toml

from multi_poetry_runner.core.hooks import GitHooksManager
from multi_poetry_runner.utils.config import ConfigManager, RepositoryConfig


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        yield workspace_path


@pytest.fixture
def mock_config_manager(temp_workspace: Path) -> Mock:
    """Create a mock ConfigManager with test repositories."""
    config_manager = Mock(spec=ConfigManager)
    config_manager.workspace_root = temp_workspace

    # Create test repos directory
    repos_dir = temp_workspace / "repos"
    repos_dir.mkdir(exist_ok=True)

    # Create test repositories with git initialization
    repo_configs = []

    for repo_name in ["repo-a", "repo-b", "repo-c"]:
        repo_path = repos_dir / repo_name
        repo_path.mkdir(exist_ok=True)

        # Initialize git repository
        git_dir = repo_path / ".git"
        git_dir.mkdir(exist_ok=True)
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)

        # Create basic pyproject.toml
        pyproject_content = {
            "tool": {
                "poetry": {
                    "name": repo_name,
                    "version": "1.0.0",
                    "description": "Test repository",
                    "dependencies": {"python": "^3.11"},
                }
            }
        }

        pyproject_path = repo_path / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            toml.dump(pyproject_content, f)

        # Initialize git repo properly
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
        )

        repo_config = RepositoryConfig(
            name=repo_name,
            url=f"https://github.com/test/{repo_name}.git",
            package_name=repo_name,
            path=repo_path,
            dependencies=[],
        )
        repo_configs.append(repo_config)

    # Mock config object
    mock_config = Mock()
    mock_config.repositories = repo_configs
    mock_config.name = "test-workspace"
    config_manager.load_.return_value = mock_config

    return config_manager


@pytest.fixture
def hooks_manager(mock_config_manager: Mock) -> GitHooksManager:
    """Create GitHooksManager instance with mocked config."""

    return GitHooksManager(mock_config_manager)


class TestGitHooksManager:
    """Test suite for GitHooksManager class."""

    def test_pre_commit_hook_prevents_local_deps(
        self,
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
            subprocess.run(
                ["git", "add", "pyproject.toml"], cwd=repo_a_path, check=True
            )

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

    def test_hook_installation_idempotency(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test repeated hook installation is safe."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Create a custom pre-existing hook
        pre_commit_hook_path = repo_a_path / ".git" / "hooks" / "pre-commit"
        original_hook_content = "#!/bin/bash\necho 'Original hook'\nexit 0\n"
        pre_commit_hook_path.write_text(original_hook_content)
        pre_commit_hook_path.chmod(0o755)

        # First installation (should backup existing hook)
        hooks_manager.install_hooks()

        # Verify backup was created
        backup_path = repo_a_path / ".git" / "hooks" / "pre-commit.backup"
        assert backup_path.exists()
        assert backup_path.read_text() == original_hook_content

        # Verify new hook was installed
        assert pre_commit_hook_path.exists()
        new_content = pre_commit_hook_path.read_text()
        assert "MPR managed repositories" in new_content

        # Second installation (should not create another backup)
        hooks_manager.install_hooks()

        # Backup should still exist and not be overwritten
        assert backup_path.exists()
        assert backup_path.read_text() == original_hook_content

        # Test force installation
        hooks_manager.install_hooks(force=True)

        # Hook should still be the MPR hook
        assert pre_commit_hook_path.exists()
        mpr_content = pre_commit_hook_path.read_text()
        assert "MPR managed repositories" in mpr_content

    def test_hook_cross_platform_compatibility(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hooks work on different platforms."""
        repos_dir = temp_workspace / "repos"

        # Install hooks
        hooks_manager.install_hooks()

        # Check hook templates
        hooks_dir = temp_workspace / "hooks"
        assert hooks_dir.exists()

        pre_commit_template = hooks_dir / "pre-commit"
        assert pre_commit_template.exists()

        hook_content = pre_commit_template.read_text()

        # Check for Unix shebang
        assert hook_content.startswith("#!/bin/bash")

        # Check for cross-platform path handling
        assert "WORKSPACE_ROOT=" in hook_content
        assert "git rev-parse --show-toplevel" in hook_content

        # Check for proper error handling
        assert "set -euo pipefail" in hook_content

        # Verify executable permissions were set correctly

        for repo_name in ["repo-a", "repo-b", "repo-c"]:
            repo_path = repos_dir / repo_name
            pre_commit_hook = repo_path / ".git" / "hooks" / "pre-commit"
            assert pre_commit_hook.exists()

            # Check executable bit
            stat_info = pre_commit_hook.stat()
            assert stat_info.st_mode & 0o111  # Check any execute bit is set

    def test_hook_functionality_validation(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook functionality validation through testing."""
        # repos_dir = temp_workspace / "repos"  # Reserved for future use

        # Install hooks
        hooks_manager.install_hooks()

        # Test hooks functionality
        test_results = hooks_manager.test_hooks(verbose=True)

        # Should return boolean indicating overall success
        assert isinstance(test_results, bool)

        # Get detailed status to verify hook testing
        status = hooks_manager.get_hook_status()

        assert "repositories" in status
        assert len(status["repositories"]) == 3

        # Check that hooks are detected as installed

        for repo_status in status["repositories"]:
            if repo_status["name"] in ["repo-a", "repo-b", "repo-c"]:
                assert repo_status["hooks_installed"] is True
                assert "pre-commit" in repo_status["hooks"]

                pre_commit_info = repo_status["hooks"]["pre-commit"]
                assert pre_commit_info["exists"] is True
                assert pre_commit_info["executable"] is True
                assert pre_commit_info["is_mpr_hook"] is True

    def test_hook_uninstallation_and_restoration(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook uninstallation and backup restoration."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Create original hook
        original_hook_content = "#!/bin/bash\necho 'Original custom hook'\nexit 0\n"
        pre_commit_hook_path = repo_a_path / ".git" / "hooks" / "pre-commit"
        pre_commit_hook_path.write_text(original_hook_content)
        pre_commit_hook_path.chmod(0o755)

        # Install MPR hooks (should backup original)
        hooks_manager.install_hooks()

        # Verify MPR hook is installed
        mpr_content = pre_commit_hook_path.read_text()
        assert "MPR managed repositories" in mpr_content

        # Verify backup exists
        backup_path = repo_a_path / ".git" / "hooks" / "pre-commit.backup"
        assert backup_path.exists()
        assert backup_path.read_text() == original_hook_content

        # Uninstall hooks
        hooks_manager.uninstall_hooks()

        # Verify original hook was restored
        assert pre_commit_hook_path.exists()
        restored_content = pre_commit_hook_path.read_text()
        assert restored_content == original_hook_content

        # Verify backup was removed
        assert not backup_path.exists()

        # Verify hook is no longer MPR hook
        status = hooks_manager.get_hook_status()
        repo_a_status = next(
            repo for repo in status["repositories"] if repo["name"] == "repo-a"
        )
        assert repo_a_status["hooks"]["pre-commit"]["is_mpr_hook"] is False

    def test_dependency_mode_detection(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook detection of dependency mode markers."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Install hooks
        hooks_manager.install_hooks()

        # Create dependency mode marker file
        dependency_marker = temp_workspace / ".dependency-mode"
        dependency_marker.write_text("local\n2024-01-01T10:00:00\n")

        # Try to commit (should be blocked by dependency mode)
        pyproject_path = repo_a_path / "pyproject.toml"

        # Stage a harmless change
        with open(pyproject_path) as f:
            data: dict[str, Any] = toml.load(f)
        data["tool"]["poetry"]["description"] = "Updated description"
        with open(pyproject_path, "w") as f:
            toml.dump(data, f)

        subprocess.run(["git", "add", "pyproject.toml"], cwd=repo_a_path, check=True)

        # Run pre-commit hook
        pre_commit_hook = repo_a_path / ".git" / "hooks" / "pre-commit"
        result = subprocess.run(
            [str(pre_commit_hook)], cwd=repo_a_path, capture_output=True, text=True
        )

        # Hook should fail because of local dependency mode
        assert result.returncode != 0
        assert "local dependency mode" in result.stderr.lower()

    def test_hook_bypassing_mechanism(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook bypassing with environment variable."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Install hooks
        hooks_manager.install_hooks()

        # Add local dependency to pyproject.toml
        pyproject_path = repo_a_path / "pyproject.toml"
        with open(pyproject_path) as f:
            data: dict[str, Any] = toml.load(f)
        data["tool"]["poetry"]["dependencies"]["local-dep"] = {
            "path": "../local",
            "develop": True,
        }
        with open(pyproject_path, "w") as f:
            toml.dump(data, f)

        subprocess.run(["git", "add", "pyproject.toml"], cwd=repo_a_path, check=True)

        # Run hook with bypass environment variable
        pre_commit_hook = repo_a_path / ".git" / "hooks" / "pre-commit"

        # Test with bypass enabled
        env = os.environ.copy()
        env["SKIP_MPR_HOOKS"] = "1"

        result = subprocess.run(
            [str(pre_commit_hook)],
            cwd=repo_a_path,
            capture_output=True,
            text=True,
            env=env,
        )

        # Hook should pass because bypass is enabled
        assert result.returncode == 0
        assert "Skipping MPR hooks" in result.stderr

    def test_multiple_validation_rules(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook validation of multiple rules."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Install hooks
        hooks_manager.install_hooks()

        test_cases: list[tuple[dict[str, Any], bool, str]] = [
            # Test case: (pyproject_content, should_fail, expected_error_pattern)
            (
                {
                    "tool": {
                        "poetry": {"dependencies": {"test-pkg": {"path": "../test"}}}
                    }
                },
                True,
                "path dependencies",
            ),
            (
                {
                    "tool": {
                        "poetry": {
                            "dependencies": {
                                "test-pkg": {"path": "../test", "develop": True}
                            }
                        }
                    }
                },
                True,
                "local path dependencies",
            ),
            ({"tool": {"poetry": {"dependencies": {"test-pkg": "^1.0.0"}}}}, False, ""),
        ]

        for i, (content_update, should_fail, error_pattern) in enumerate(test_cases):
            # Reset pyproject.toml
            pyproject_path = repo_a_path / "pyproject.toml"
            base_content: dict[str, Any] = {
                "tool": {
                    "poetry": {
                        "name": "repo-a",
                        "version": "1.0.0",
                        "description": "Test repository",
                        "dependencies": {"python": "^3.11"},
                    }
                }
            }

            # Merge test content

            if content_update.get("tool", {}).get("poetry", {}).get("dependencies"):
                base_content["tool"]["poetry"]["dependencies"].update(
                    content_update["tool"]["poetry"]["dependencies"]
                )

            with open(pyproject_path, "w") as f:
                toml.dump(base_content, f)

            # Stage and test
            subprocess.run(
                ["git", "add", "pyproject.toml"], cwd=repo_a_path, check=True
            )

            pre_commit_hook = repo_a_path / ".git" / "hooks" / "pre-commit"
            result = subprocess.run(
                [str(pre_commit_hook)], cwd=repo_a_path, capture_output=True, text=True
            )

            if should_fail:
                assert result.returncode != 0, f"Test case {i} should have failed"

                if error_pattern:
                    assert (
                        error_pattern.lower() in result.stderr.lower()
                    ), f"Test case {i} should contain '{error_pattern}'"
            else:
                assert result.returncode == 0, f"Test case {i} should have passed"

            # Reset git state
            subprocess.run(
                ["git", "reset", "HEAD", "pyproject.toml"],
                cwd=repo_a_path,
                capture_output=True,
            )

    def test_hook_status_reporting(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test comprehensive hook status reporting."""
        temp_workspace / "repos"

        # Test status before installation
        status_before = hooks_manager.get_hook_status()
        assert status_before["workspace"] == "test-workspace"
        assert len(status_before["repositories"]) == 3

        # All repos should have no hooks installed initially

        for repo_status in status_before["repositories"]:
            assert repo_status["hooks_installed"] is False

        # Install hooks
        hooks_manager.install_hooks()

        # Test status after installation
        status_after = hooks_manager.get_hook_status()

        for repo_status in status_after["repositories"]:
            assert repo_status["hooks_installed"] is True

            # Check pre-commit hook details
            pre_commit = repo_status["hooks"]["pre-commit"]
            assert pre_commit["exists"] is True
            assert pre_commit["executable"] is True
            assert pre_commit["is_mpr_hook"] is True

            # Check pre-push hook (may or may not exist depending on implementation)

            if "pre-push" in repo_status["hooks"]:
                pre_push = repo_status["hooks"]["pre-push"]

                if pre_push["exists"]:
                    assert pre_push["executable"] is True

        # Test display functionality (should not raise exceptions)
        hooks_manager.display_hook_status(status_after)

    def test_hook_template_content_validation(
        self, hooks_manager: GitHooksManager, temp_workspace: Path
    ) -> None:
        """Test that hook templates contain expected content."""
        # Create hooks directory and templates
        hooks_dir = temp_workspace / "hooks"
        hooks_manager._create_hook_templates(hooks_dir)

        # Verify pre-commit hook template
        pre_commit_template = hooks_dir / "pre-commit"
        assert pre_commit_template.exists()

        content = pre_commit_template.read_text()

        # Check essential components
        assert "#!/bin/bash" in content
        assert "MPR managed repositories" in content
        assert "SKIP_MPR_HOOKS" in content
        assert "path =" in content
        assert "develop = true" in content
        assert "dependency-mode" in content
        assert "print_error" in content
        assert "pyproject.toml validation" in content

        # Check for proper error handling
        assert "set -euo pipefail" in content
        assert "exit 1" in content
        assert "exit 0" in content

        # Verify pre-push hook template
        pre_push_template = hooks_dir / "pre-push"
        assert pre_push_template.exists()

        pre_push_content = pre_push_template.read_text()
        assert "#!/bin/bash" in pre_push_content
        assert "SKIP_MPR_HOOKS" in pre_push_content
        assert "dependency-mode" in pre_push_content

    def test_hook_error_handling_edge_cases(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook behavior with edge cases and error conditions."""
        repos_dir = temp_workspace / "repos"

        # Create a repository without .git directory
        broken_repo_path = repos_dir / "broken-repo"
        broken_repo_path.mkdir(exist_ok=True)

        # Add to config
        broken_repo_config = RepositoryConfig(
            name="broken-repo",
            url="https://github.com/test/broken-repo.git",
            package_name="broken-repo",
            path=broken_repo_path,
            dependencies=[],
        )

        mock_config = mock_config_manager.load_config()
        mock_config.repositories.append(broken_repo_config)

        # Install hooks (should handle missing .git gracefully)
        hooks_manager.install_hooks()

        # Test status with broken repo
        status = hooks_manager.get_hook_status()

        broken_repo_status = next(
            repo for repo in status["repositories"] if repo["name"] == "broken-repo"
        )
        assert broken_repo_status["hooks_installed"] is False

        # Test hook testing with mixed conditions
        test_results = hooks_manager.test_hooks(verbose=True)

        # Should handle the broken repo gracefully
        assert isinstance(test_results, bool)

    def test_hook_performance_with_large_files(
        self,
        hooks_manager: GitHooksManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test hook performance with large pyproject.toml files."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Install hooks
        hooks_manager.install_hooks()

        # Create a large pyproject.toml with many dependencies
        pyproject_path = repo_a_path / "pyproject.toml"
        large_config: dict[str, Any] = {
            "tool": {
                "poetry": {
                    "name": "repo-a",
                    "version": "1.0.0",
                    "description": "Test repository with many dependencies",
                    "dependencies": {"python": "^3.11"},
                }
            }
        }

        # Add many dependencies

        for i in range(100):
            large_config["tool"]["poetry"]["dependencies"][
                f"package-{i}"
            ] = f"^{i % 10}.0.0"

        with open(pyproject_path, "w") as f:
            toml.dump(large_config, f)

        # Stage and test hook performance
        subprocess.run(["git", "add", "pyproject.toml"], cwd=repo_a_path, check=True)

        import time

        start_time = time.time()

        pre_commit_hook = repo_a_path / ".git" / "hooks" / "pre-commit"
        result = subprocess.run(
            [str(pre_commit_hook)], cwd=repo_a_path, capture_output=True, text=True
        )

        execution_time = time.time() - start_time

        # Hook should complete quickly even with large files
        assert execution_time < 5.0  # Should complete within 5 seconds
        assert result.returncode == 0  # Should pass (no local dependencies)

    def test_concurrent_hook_operations(
        self, hooks_manager: GitHooksManager, mock_config_manager: Mock
    ) -> None:
        """Test thread safety of hook operations."""
        import threading

        results = []
        errors = []

        def install_and_test() -> None:
            try:
                hooks_manager.install_hooks()
                status = hooks_manager.get_hook_status()
                results.append(status)
            except Exception as e:
                errors.append(str(e))

        # Run multiple hook operations concurrently
        threads = []

        for _i in range(3):
            thread = threading.Thread(target=install_and_test)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete

        for thread in threads:
            thread.join(timeout=5.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors during concurrent operations: {errors}"

        # Verify all operations completed
        assert len(results) == 3

        # Verify final state is consistent
        final_status = hooks_manager.get_hook_status()

        for repo_status in final_status["repositories"]:
            if repo_status["name"] in ["repo-a", "repo-b", "repo-c"]:
                assert repo_status["hooks_installed"] is True
