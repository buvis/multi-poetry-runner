"""Test dependency management functionality."""

import shutil
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import toml

from multi_poetry_runner.core.dependencies import DependencyManager
from multi_poetry_runner.utils.config import (
    ConfigManager,
    RepositoryConfig,
)


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

    # Create test repositories with circular dependency structure
    repo_a = repos_dir / "repo-a"
    repo_b = repos_dir / "repo-b"
    repo_c = repos_dir / "repo-c"

    for repo_path in [repo_a, repo_b, repo_c]:
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

    # Mock repository configurations
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
            dependencies=[],
        ),
    ]

    config_manager.get_repository.side_effect = lambda name: next(
        (repo for repo in repo_configs if repo.name == name), None
    )
    config_manager.get_dependency_order.return_value = ["repo-c", "repo-b", "repo-a"]
    config_manager.get_backups_path.return_value = temp_workspace / "backups"

    # Mock config object
    mock_config = Mock()
    mock_config.repositories = repo_configs
    config_manager.load_config.return_value = mock_config

    return config_manager


@pytest.fixture
def dependency_manager(mock_config_manager: Mock) -> DependencyManager:
    """Create DependencyManager instance with mocked config."""

    return DependencyManager(mock_config_manager)


class TestDependencyManager:
    """Test suite for DependencyManager class."""

    def test_dependency_cycle_detection(
        self,
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

        mock_config_manager.get_repository.side_effect = lambda name: next(
            (repo for repo in circular_configs if repo.name == name), None
        )

        # Mock get_dependency_order to raise an exception for circular dependency
        mock_config_manager.get_dependency_order.side_effect = Exception(
            "Circular dependency detected"
        )

        # Test that circular dependency is detected
        with pytest.raises(Exception, match="Circular dependency detected"):
            dependency_manager.switch_to_local()

    def test_switch_to_local_with_missing_repos(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test handling of missing repositories when switching to local dependencies."""
        repos_dir = temp_workspace / "repos"

        # Remove one repository directory
        missing_repo = repos_dir / "repo-b"

        if missing_repo.exists():
            shutil.rmtree(missing_repo)

        with patch("multi_poetry_runner.core.dependencies.logger") as mock_logger:
            result = dependency_manager.switch_to_local(dry_run=False)

            # Should still succeed partially
            assert result is True

            # Should log warning about missing repo
            mock_logger.warning.assert_called()
            warning_calls = [
                call.args[0] for call in mock_logger.warning.call_args_list
            ]
            assert any("does not exist" in call for call in warning_calls)

    def test_switch_to_remote_version_resolution(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test correct version resolution when switching to remote dependencies."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock successful poetry operations
            mock_subprocess.return_value.returncode = 0

            result = dependency_manager.switch_to_remote(dry_run=False)

            assert result is True

            # Verify poetry commands were called
            assert mock_subprocess.called

            # Check that lock files were updated
            lock_calls = [
                call for call in mock_subprocess.call_args_list if "lock" in str(call)
            ]
            assert len(lock_calls) > 0

    def test_switch_to_test_pypi_fallback(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test fallback to PyPI when test-PyPI package not available."""
        with patch("subprocess.run") as mock_subprocess:

            def subprocess_side_effect(*args: object, **kwargs: object) -> Mock:
                cmd = args[0]

                if "test-pypi" in str(cmd):
                    # Simulate test-pypi failure
                    result = Mock()
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = "Package not found on test-pypi"

                    return result
                else:
                    # Simulate regular pypi success
                    result = Mock()
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""

                    return result

            mock_subprocess.side_effect = subprocess_side_effect

            with patch("multi_poetry_runner.core.dependencies.logger") as mock_logger:
                result = dependency_manager.switch_to_test(dry_run=False)

                assert result is True

                # Should log warnings about test-pypi failures
                mock_logger.warning.assert_called()

    def test_backup_and_restore(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test backup creation and restoration on failure."""
        repos_dir = temp_workspace / "repos"

        # Modify pyproject.toml files to have some content to backup

        for repo_name in ["repo-a", "repo-b", "repo-c"]:
            pyproject_path = repos_dir / repo_name / "pyproject.toml"
            with open(pyproject_path) as f:
                data = toml.load(f)

            # Add some dependencies
            data["tool"]["poetry"]["dependencies"]["test-dep"] = "^1.0.0"

            with open(pyproject_path, "w") as f:
                toml.dump(data, f)

        # Test backup creation
        dependency_manager._create_backup()

        # Verify backup directory exists and contains files
        backups_dir = temp_workspace / "backups"
        assert backups_dir.exists()

        backup_entries = list(backups_dir.iterdir())
        assert len(backup_entries) > 0

        # Latest backup should contain pyproject.toml files
        latest_backup = max(backup_entries, key=lambda p: p.stat().st_mtime)
        backup_files = list(latest_backup.iterdir())

        # Should have backed up all repository pyproject.toml files
        expected_backups = [
            "repo-a_pyproject.toml",
            "repo-b_pyproject.toml",
            "repo-c_pyproject.toml",
        ]
        backup_names = [f.name for f in backup_files]

        for expected in expected_backups:
            assert expected in backup_names

    def test_analyze_transitive_dependencies(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test transitive dependency analysis."""
        repos_dir = temp_workspace / "repos"

        # Set up a more complex dependency chain
        # repo-a depends on repo-b (version ^1.0.0)
        # repo-b depends on repo-c (version ^1.0.0)
        # but repo-c is actually version 2.0.0 (incompatible)

        # Update repo-a to depend on repo-b
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["dependencies"]["repo-b"] = "^1.0.0"
        with open(repo_a_pyproject, "w") as f:
            toml.dump(data, f)

        # Update repo-b to depend on repo-c
        repo_b_pyproject = repos_dir / "repo-b" / "pyproject.toml"
        with open(repo_b_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["dependencies"]["repo-c"] = "^1.0.0"
        with open(repo_b_pyproject, "w") as f:
            toml.dump(data, f)

        # Update repo-c to version 2.0.0 (incompatible)
        repo_c_pyproject = repos_dir / "repo-c" / "pyproject.toml"
        with open(repo_c_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["version"] = "2.0.0"
        with open(repo_c_pyproject, "w") as f:
            toml.dump(data, f)

        # Run transitive dependency analysis
        analysis = dependency_manager.analyze_transitive_dependencies()

        # Verify analysis structure
        assert "dependency_graph" in analysis
        assert "dependency_chains" in analysis
        assert "transitive_issues" in analysis

        # Should detect the incompatibility
        transitive_issues = analysis["transitive_issues"]
        assert len(transitive_issues) > 0

        # Should find the chain repo-a -> repo-b -> repo-c
        dependency_chains = analysis["dependency_chains"]
        assert "repo-a" in dependency_chains

        # Verify the dependency chain structure
        repo_a_chains = dependency_chains["repo-a"]
        assert len(repo_a_chains) > 0

        # Should contain a chain that goes through all three repos
        long_chains = [chain for chain in repo_a_chains if len(chain) >= 3]
        assert len(long_chains) > 0

    def test_get_status_detailed(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test detailed status retrieval including compatibility issues."""
        repos_dir = temp_workspace / "repos"

        # Set up repos with various dependency types
        # repo-a: local path dependency on repo-b
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["dependencies"]["repo-b"] = {
            "path": "../repo-b",
            "develop": True,
        }
        with open(repo_a_pyproject, "w") as f:
            toml.dump(data, f)

        # repo-b: version dependency on repo-c with mismatch
        repo_b_pyproject = repos_dir / "repo-b" / "pyproject.toml"
        with open(repo_b_pyproject) as f:
            data = toml.load(f)
        data["tool"]["poetry"]["dependencies"][
            "repo-c"
        ] = "^2.0.0"  # Incompatible with repo-c version 1.0.0
        with open(repo_b_pyproject, "w") as f:
            toml.dump(data, f)

        status = dependency_manager.get_status()

        # Verify status structure
        assert "workspace_mode" in status
        assert "repositories" in status

        # Check repository statuses
        repos = status["repositories"]
        assert len(repos) == 3

        # Find repo-a status
        repo_a_status = next(repo for repo in repos if repo["name"] == "repo-a")
        assert repo_a_status["mode"] == "local"  # Has path dependency
        assert len(repo_a_status["path_dependencies"]) > 0

        # Find repo-b status
        repo_b_status = next(repo for repo in repos if repo["name"] == "repo-b")
        assert repo_b_status["mode"] == "remote"  # Has version dependency
        assert len(repo_b_status["version_dependencies"]) > 0

        # Should detect compatibility issues
        assert len(repo_b_status["compatibility_issues"]) > 0

    def test_dependency_manager_edge_cases(
        self,
        dependency_manager: DependencyManager,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test edge cases and error handling."""
        repos_dir = temp_workspace / "repos"

        # Test with corrupted pyproject.toml
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"
        with open(repo_a_pyproject, "w") as f:
            f.write("invalid toml content [[[[")

        # Should handle corrupted files gracefully
        with patch("multi_poetry_runner.core.dependencies.logger") as mock_logger:
            dependency_manager.switch_to_local(dry_run=True)
            # Should not crash, may log warnings

        # Test with missing pyproject.toml - remove repo-a which has dependencies
        repo_a_pyproject = repos_dir / "repo-a" / "pyproject.toml"

        if repo_a_pyproject.exists():
            repo_a_pyproject.unlink()

        # Mock subprocess to avoid actual poetry calls
        with (
            patch("subprocess.run") as mock_subprocess,
            patch("multi_poetry_runner.core.dependencies.logger") as mock_logger,
        ):
            mock_subprocess.return_value.returncode = 0

            dependency_manager.switch_to_remote(dry_run=False)
            # Should log warning about missing pyproject.toml
            mock_logger.warning.assert_called()

    def test_version_compatibility_checks(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test version compatibility checking logic."""
        # Test caret requirements
        assert dependency_manager._is_version_compatible("^1.0.0", "1.5.0") is True
        assert dependency_manager._is_version_compatible("^1.0.0", "2.0.0") is False

        # Test tilde requirements
        assert dependency_manager._is_version_compatible("~1.2.0", "1.2.5") is True
        assert dependency_manager._is_version_compatible("~1.2.0", "1.3.0") is False

        # Test exact requirements
        assert dependency_manager._is_version_compatible("1.0.0", "1.0.0") is True
        assert (
            dependency_manager._is_version_compatible("1.0.0", "1.0.1") is True
        )  # Default to compatible

    @patch("subprocess.run")
    def test_switch_local_poetry_failures(
        self, mock_subprocess: Mock, dependency_manager: DependencyManager
    ) -> None:
        """Test handling of Poetry command failures during local switch."""
        # Mock Poetry command failure
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "poetry")

        with patch("multi_poetry_runner.core.dependencies.logger") as mock_logger:
            result = dependency_manager.switch_to_local(dry_run=False)

            # Should still return True (best effort)
            assert result is True

            # Should attempt direct pyproject.toml editing as fallback
            mock_logger.warning.assert_called()

    def test_workspace_dependency_modes(
        self, dependency_manager: DependencyManager, temp_workspace: Path
    ) -> None:
        """Test workspace dependency mode tracking."""
        # Test setting local mode
        dependency_manager._create_dependency_marker("local")
        assert dependency_manager._get_workspace_mode() == "local"

        # Test setting test mode
        dependency_manager._create_dependency_marker("test")
        assert dependency_manager._get_workspace_mode() == "test"

        # Test removing marker (defaults to remote)
        dependency_manager._remove_dependency_marker()
        assert dependency_manager._get_workspace_mode() == "remote"

    def test_relative_path_calculation(
        self, dependency_manager: DependencyManager, temp_workspace: Path
    ) -> None:
        """Test relative path calculation between repositories."""
        repos_dir = temp_workspace / "repos"
        repo_a = repos_dir / "repo-a"
        repo_b = repos_dir / "repo-b"

        # Test sibling repositories
        relative_path = dependency_manager._get_relative_path(repo_a, repo_b)
        assert relative_path == "../repo-b"

        # Test with different directory structure
        nested_repo = repos_dir / "nested" / "repo-nested"
        nested_repo.mkdir(parents=True)

        relative_path = dependency_manager._get_relative_path(repo_a, nested_repo)
        assert "nested/repo-nested" in relative_path
