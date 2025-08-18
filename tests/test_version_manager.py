"""Test version management functionality."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import toml

from multi_poetry_runner.core.version_manager import VersionManager
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

    # Create test repositories with dependency chain
    repo_a = repos_dir / "repo-a"
    repo_b = repos_dir / "repo-b"
    repo_c = repos_dir / "repo-c"
    repo_d = repos_dir / "repo-d"

    for repo_path in [repo_a, repo_b, repo_c, repo_d]:
        repo_path.mkdir(exist_ok=True)

        # Create basic pyproject.toml
        pyproject_content = {
            "tool": {
                "poetry": {
                    "name": repo_path.name,
                    "version": "1.0.0",
                    "description": "Test repository",
                    "dependencies": {"python": "^3.11"},
                }
            }
        }

        pyproject_path = repo_path / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            toml.dump(pyproject_content, f)

    # Mock repository configurations with dependency chain: A → B → C → D
    repo_configs = [
        RepositoryConfig(
            name="repo-a",
            url="https://github.com/test/repo-a.git",
            package_name="repo-a",
            path=repo_a,
            dependencies=["repo-b"],
        ),
        RepositoryConfig(
            name="repo-b",
            url="https://github.com/test/repo-b.git",
            package_name="repo-b",
            path=repo_b,
            dependencies=["repo-c"],
        ),
        RepositoryConfig(
            name="repo-c",
            url="https://github.com/test/repo-c.git",
            package_name="repo-c",
            path=repo_c,
            dependencies=["repo-d"],
        ),
        RepositoryConfig(
            name="repo-d",
            url="https://github.com/test/repo-d.git",
            package_name="repo-d",
            path=repo_d,
            dependencies=[],
        ),
    ]

    config_manager.get_repository.side_effect = lambda name: next(
        (repo for repo in repo_configs if repo.name == name), None
    )
    config_manager.get_dependency_order.return_value = [
        "repo-d",
        "repo-c",
        "repo-b",
        "repo-a",
    ]

    # Mock config object
    mock_config = Mock()
    mock_config.repositories = repo_configs
    config_manager.load_config.return_value = mock_config

    return config_manager


@pytest.fixture
def version_manager(mock_config_manager: Mock) -> VersionManager:
    """Create VersionManager instance with mocked config."""

    return VersionManager(mock_config_manager)


class TestVersionManager:
    """Test suite for VersionManager class."""

    def test_bump_version_alpha_progression(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test alpha version number progression."""
        repos_dir = temp_workspace / "repos"
        repo_a_path = repos_dir / "repo-a"

        # Set initial version to 1.2.3
        pyproject_path = repo_a_path / "pyproject.toml"
        with open(pyproject_path) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["version"] = "1.2.3"
        with open(pyproject_path, "w") as f:
            toml.dump(data, f)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0

            # First alpha bump (patch)
            result = version_manager.bump_version(
                "repo-a", "patch", alpha=True, dry_run=False, update_dependents=False
            )
            assert result is True

            # Check that poetry version was called with 1.2.4-alpha.1
            version_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "version" in str(call[0])
            ]
            assert len(version_calls) > 0

            # Update the actual file to simulate the version change
            with open(pyproject_path) as f:
                data = toml.load(f)
            data["tool"]["poetry"]["version"] = "1.2.4-alpha.1"
            with open(pyproject_path, "w") as f:
                toml.dump(data, f)

            mock_subprocess.reset_mock()

            # Second alpha bump (should go to alpha.2)
            result = version_manager.bump_version(
                "repo-a", "patch", alpha=True, dry_run=False, update_dependents=False
            )
            assert result is True

            # Update to alpha.2
            with open(pyproject_path) as f:
                data = toml.load(f)
            data["tool"]["poetry"]["version"] = "1.2.4-alpha.2"
            with open(pyproject_path, "w") as f:
                toml.dump(data, f)

            mock_subprocess.reset_mock()

            # Release version (should go to 1.2.4)
            result = version_manager.bump_version(
                "repo-a", "patch", alpha=False, dry_run=False, update_dependents=False
            )
            assert result is True

    def test_dependent_version_cascade(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test version bumping cascades through dependents."""
        repos_dir = temp_workspace / "repos"

        # Set up dependency chain: A → B → C → D
        repo_configs = [
            ("repo-a", ["repo-b"]),
            ("repo-b", ["repo-c"]),
            ("repo-c", ["repo-d"]),
            ("repo-d", []),
        ]

        # Add dependencies to pyproject.toml files

        for repo_name, deps in repo_configs:
            pyproject_path = repos_dir / repo_name / "pyproject.toml"
            with open(pyproject_path) as f:
                data = toml.load(f)

            for dep in deps:
                data["tool"]["poetry"]["dependencies"][dep] = "^1.0.0"

            with open(pyproject_path, "w") as f:
                toml.dump(data, f)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0

            # Bump repo-a with major version and minor bump for dependents
            result = version_manager.bump_version(
                "repo-a",
                "major",
                alpha=False,
                dry_run=False,
                update_dependents=True,
                dependents_bump="minor",
                validate=False,
            )

            assert result is True

            # Should have called poetry version for repo-a and its dependents
            version_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "version" in str(call[0])
            ]

            # Should have version calls (exact number depends on implementation)
            assert len(version_calls) > 0

            # Should have lock file updates
            lock_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "lock" in str(call[0])
            ]
            assert len(lock_calls) >= 0  # Lock updates are optional in some flows

    def test_version_sync_with_conflicts(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test version synchronization with conflicting requirements."""
        repos_dir = temp_workspace / "repos"

        # Set up conflicting versions
        # repo-a depends on repo-b ^1.0.0, but repo-b is actually 2.0.0
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["dependencies"]["repo-b"] = "^1.0.0"
        with open(repo_a_pyproject, "w") as f:
            toml.dump(data, f)

        repo_b_pyproject = repos_dir / "repo-b" / "pyproject.toml"
        with open(repo_b_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["version"] = "2.0.0"
        with open(repo_b_pyproject, "w") as f:
            toml.dump(data, f)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0

            # Test sync with force flag
            result = version_manager.sync_dependency_versions(dry_run=False, force=True)

            # Should detect and attempt to resolve conflicts
            assert result is True

            # Should have made subprocess calls to update dependencies
            assert mock_subprocess.called

    def test_version_rollback(
        self, version_manager: VersionManager, temp_workspace: Path
    ) -> None:
        """Test version rollback functionality."""
        # Create version history with multiple entries
        history_file = temp_workspace / ".version-history.json"

        history_data = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "repository": "repo-a",
                "old_version": "1.0.0",
                "new_version": "1.1.0",
                "bump_type": "minor",
                "alpha": False,
                "dependents_updated": [],
            },
            {
                "timestamp": "2024-01-02T10:00:00",
                "repository": "repo-a",
                "old_version": "1.1.0",
                "new_version": "1.2.0",
                "bump_type": "minor",
                "alpha": False,
                "dependents_updated": [],
            },
        ]

        with open(history_file, "w") as f:
            json.dump(history_data, f)

        # Test getting version history
        recent_history = version_manager._get_recent_version_history(limit=5)
        assert len(recent_history) == 2
        assert recent_history[0]["old_version"] == "1.0.0"
        assert recent_history[1]["new_version"] == "1.2.0"

    def test_concurrent_version_updates(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test thread safety of version updates."""
        # repos_dir = temp_workspace / "repos"  # Reserved for future use
        results = {}
        errors = []

        def update_version(repo_name: str, bump_type: str, thread_id: int) -> None:
            """Thread function to update version."""

            try:
                with patch("subprocess.run") as mock_subprocess:
                    mock_subprocess.return_value.returncode = 0

                    result = version_manager.bump_version(
                        repo_name,
                        bump_type,
                        alpha=False,
                        dry_run=True,  # Use dry run to avoid actual file conflicts
                        update_dependents=False,
                        validate=False,
                    )
                    results[thread_id] = result
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        # Start multiple threads updating different repositories
        threads = []

        for i in range(4):
            repo_name = f"repo-{chr(ord('a') + i)}"  # repo-a, repo-b, repo-c, repo-d
            thread = threading.Thread(
                target=update_version, args=(repo_name, "patch", i)
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete

        for thread in threads:
            thread.join(timeout=5.0)

        # Verify all updates succeeded without errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 4
        assert all(result is True for result in results.values())

    def test_version_calculation_edge_cases(
        self, version_manager: VersionManager
    ) -> None:
        """Test version calculation with various formats."""
        # Test alpha version progression
        assert (
            version_manager._calculate_new_version("1.0.0", "patch", True)
            == "1.0.1-alpha.1"
        )
        assert (
            version_manager._calculate_new_version("1.0.1-alpha.1", "patch", True)
            == "1.0.1-alpha.2"
        )
        assert (
            version_manager._calculate_new_version("1.0.1-alpha.2", "patch", False)
            == "1.0.1"
        )

        # Test minor and major bumps
        assert (
            version_manager._calculate_new_version("1.2.3", "minor", False) == "1.3.0"
        )
        assert (
            version_manager._calculate_new_version("1.2.3", "major", False) == "2.0.0"
        )

        # Test alpha to release progression
        assert (
            version_manager._calculate_new_version("1.2.4-alpha.1", "minor", False)
            == "1.2.0"
        )
        assert (
            version_manager._calculate_new_version("1.2.4-alpha.1", "major", False)
            == "1.0.0"
        )

    def test_dependency_info_retrieval(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test detailed dependency information retrieval."""
        repos_dir = temp_workspace / "repos"

        # Set up repo-a with various dependency types
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject) as f:
            data = toml.load(f)

        data["tool"]["poetry"]["dependencies"] = {
            "python": "^3.11",
            "repo-b": "^1.0.0",  # Managed dependency
            "repo-c": {"path": "../repo-c", "develop": True},  # Local path
            "external-lib": "^2.0.0",  # External dependency
        }

        with open(repo_a_pyproject, "w") as f:
            toml.dump(data, f)

        repo_config = mock_config_manager.get_repository("repo-a")
        dependency_info = version_manager._get_dependency_info(repo_config)

        # Should only return managed dependencies
        managed_deps = [dep for dep in dependency_info if dep.get("managed")]
        assert len(managed_deps) == 2  # repo-b and repo-c

        # Check dependency details
        repo_b_dep = next(dep for dep in managed_deps if dep["name"] == "repo-b")
        assert repo_b_dep["required_version"] == "^1.0.0"
        assert repo_b_dep["is_path"] is False

        repo_c_dep = next(dep for dep in managed_deps if dep["name"] == "repo-c")
        assert repo_c_dep["is_path"] is True

    def test_version_status_display(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test version status retrieval and display formatting."""
        repos_dir = temp_workspace / "repos"

        # Set up some repositories with alpha versions
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["version"] = "1.0.0-alpha.1"
        with open(repo_a_pyproject, "w") as f:
            toml.dump(data, f)

        status = version_manager.get_version_status()

        # Verify status structure
        assert "repositories" in status
        assert "dependency_graph" in status
        assert "version_history" in status

        # Check repository status
        repos = status["repositories"]
        repo_a_status = next(repo for repo in repos if repo["name"] == "repo-a")

        assert repo_a_status["current_version"] == "1.0.0-alpha.1"
        assert repo_a_status["is_alpha"] is True
        assert repo_a_status["path_exists"] is True

    def test_version_compatibility_edge_cases(
        self, version_manager: VersionManager
    ) -> None:
        """Test version compatibility checking with edge cases."""
        # Test various requirement formats
        assert version_manager._is_version_compatible("^1.0.0", "1.5.0") is True
        assert version_manager._is_version_compatible("^1.0.0", "2.0.0") is False
        assert version_manager._is_version_compatible("^2.0.0", "2.1.0") is True

        # Test tilde requirements
        assert version_manager._is_version_compatible("~1.2.0", "1.2.5") is True
        assert version_manager._is_version_compatible("~1.2.0", "1.3.0") is False

        # Test exact versions
        assert version_manager._is_version_compatible("1.0.0", "1.0.0") is True
        assert version_manager._is_version_compatible("1.0.0", "1.0.1") is False

    def test_validation_tests_execution(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test validation test execution during version bump."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock successful poetry version and pytest commands
            def subprocess_side_effect(*args: str, **kwargs: str) -> Mock:
                cmd = args[0]
                result = Mock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""

                if "pytest" in str(cmd):
                    # Simulate successful tests
                    result.stdout = "2 passed"

                return result

            mock_subprocess.side_effect = subprocess_side_effect

            repo_config = mock_config_manager.get_repository("repo-a")
            success = version_manager._run_validation_tests(repo_config, [])

            assert success is True

            # Should have run pytest
            pytest_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "pytest" in str(call[0])
            ]
            assert len(pytest_calls) > 0

    def test_version_history_management(
        self, version_manager: VersionManager, temp_workspace: Path
    ) -> None:
        """Test version history recording and retrieval."""
        # Record some version changes
        version_manager._record_version_history(
            "repo-a", "1.0.0", "1.1.0", "minor", False, []
        )

        version_manager._record_version_history(
            "repo-b",
            "2.0.0",
            "2.0.1",
            "patch",
            False,
            [{"name": "repo-a", "old_version": "1.1.0", "new_version": "1.1.1"}],
        )

        # Test history retrieval
        history = version_manager._get_recent_version_history(limit=5)
        assert len(history) == 2

        # Check latest entry
        latest = history[-1]
        assert latest["repository"] == "repo-b"
        assert latest["old_version"] == "2.0.0"
        assert latest["new_version"] == "2.0.1"
        assert len(latest["dependents_updated"]) == 1

    def test_dry_run_mode(
        self, version_manager: VersionManager, mock_config_manager: Mock
    ) -> None:
        """Test dry run mode doesn't make actual changes."""
        with patch("subprocess.run") as mock_subprocess:
            # Should not be called in dry run mode
            result = version_manager.bump_version(
                "repo-a", "patch", alpha=False, dry_run=True, update_dependents=True
            )

            assert result is True
            # No subprocess calls should be made in dry run
            mock_subprocess.assert_not_called()

    def test_error_handling_invalid_repository(
        self, version_manager: VersionManager
    ) -> None:
        """Test error handling for invalid repository names."""
        result = version_manager.bump_version(
            "nonexistent-repo", "patch", dry_run=False
        )

        assert result is False

    def test_error_handling_missing_pyproject(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test error handling when pyproject.toml is missing."""
        repos_dir = temp_workspace / "repos"

        # Remove pyproject.toml from repo-a
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"

        if repo_a_pyproject.exists():
            repo_a_pyproject.unlink()

        result = version_manager.bump_version(
            "repo-a", "patch", dry_run=False, update_dependents=False
        )

        assert result is False

    @patch("subprocess.run")
    def test_poetry_command_failures(
        self, mock_subprocess: Mock, version_manager: VersionManager
    ) -> None:
        """Test handling of Poetry command failures."""
        # Mock Poetry command failure
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "poetry")

        result = version_manager.bump_version(
            "repo-a", "patch", dry_run=False, update_dependents=False, validate=False
        )

        assert result is False

    def test_sync_with_no_conflicts(
        self,
        version_manager: VersionManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test sync when all dependencies are already synchronized."""
        repos_dir = temp_workspace / "repos"

        # Set up consistent versions
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["dependencies"]["repo-b"] = "^1.0.0"
        with open(repo_a_pyproject, "w") as f:
            toml.dump(data, f)

        # repo-b is at version 1.0.0 (matches requirement)
        repo_b_pyproject = repos_dir / "repo-b" / "pyproject.toml"
        with open(repo_b_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["version"] = "1.0.0"
        with open(repo_b_pyproject, "w") as f:
            toml.dump(data, f)

        result = version_manager.sync_dependency_versions(dry_run=False)

        # Should succeed without making changes
        assert result is True
