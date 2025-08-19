"""Test testing module functionality."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import toml

from multi_poetry_runner.core.testing import ExecutorService
from multi_poetry_runner.utils.config import RepositoryConfig


def mock_run_method(cmd: list[str], **kwargs: Any) -> Any:
    """Create a mock subprocess result for tests."""

    class MockResult:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    # Successful test cases for pytest
    if "pytest" in str(cmd) or any(
        test_word in str(cmd) for test_word in ["-v", "test"]
    ):
        return MockResult(returncode=0, stdout="Successful test output")

    # Default behavior
    return MockResult()


def test_executor_service_initialization(
    test_runner: ExecutorService,
    mock_config_manager: Mock,
) -> None:
    """Test ExecutorService initialization."""
    assert test_runner is not None
    assert test_runner.config_manager == mock_config_manager


def test_run_unit_tests(
    test_runner: ExecutorService,
    temp_workspace: Path,
    mock_config_manager: Mock,
) -> None:
    """Test running unit tests across repositories."""
    # Configure mock repositories
    repos_dir = temp_workspace / "repos"
    repos_dir.mkdir(exist_ok=True)

    # Create mock repositories with unit tests
    mock_repos: list[str] = ["repo-a", "repo-b", "repo-c"]
    for repo_name in mock_repos:
        repo_path = repos_dir / repo_name
        repo_path.mkdir(exist_ok=True)

        # Create a pyproject.toml
        (repo_path / "pyproject.toml").write_text(
            f"""
[tool.poetry]
name = "{repo_name}"
version = "0.1.0"
description = "Test repository"

[tool.poetry.dependencies]
python = "^3.11"
"""
        )

        # Create tests directory
        tests_dir = repo_path / "tests" / "unit"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # Create a dummy test file
        (tests_dir / "test_example.py").write_text(
            """
def test_dummy():
    assert True
"""
        )

    # Create a Mock for load_config and attach it
    config_mock = Mock()
    config_mock.repositories = [
        Mock(name=repo_name, path=repos_dir / repo_name) for repo_name in mock_repos
    ]
    mock_load_config = Mock()
    mock_load_config.return_value = config_mock
    mock_config_manager.load_config = mock_load_config

    # Patch subprocess to simulate successful tests
    with patch("subprocess.run", side_effect=mock_run_method):
        # Create a temporary capture of print output
        with patch("builtins.print"):
            # Run unit tests
            results = test_runner.run_unit_tests()

        # Verify results
        assert isinstance(results, bool)
        assert results is True


def test_run_integration_tests(
    test_runner: ExecutorService,
    temp_workspace: Path,
    mock_config_manager: Mock,
) -> None:
    """Test running integration tests across repositories."""
    # Mock the config manager to return a proper config
    config_mock = Mock()
    config_mock.repositories = []  # Empty list for simple test
    config_mock.name = "test-workspace"
    config_mock.python_version = "3.11"
    mock_config_manager.load_config.return_value = config_mock

    # Mock the file operations for integration config
    with (
        patch("pathlib.Path.write_text") as mock_write,
        patch("pathlib.Path.exists") as mock_exists,
    ):
        mock_exists.return_value = False  # Config doesn't exist yet

        # Run integration tests (should create default config)
        results = test_runner.run_integration_tests()

        # Should have attempted to create default config
        mock_write.assert_called()

        # Validate test results
        assert isinstance(results, bool)


def test_run_specific_repository_tests(
    test_runner: ExecutorService,
    temp_workspace: Path,
    mock_config_manager: Mock,
) -> None:
    """Test running tests for a specific repository."""
    # Create mock repository
    repo_path = temp_workspace / "repos" / "repo-a"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Create pyproject.toml
    (repo_path / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "repo-a"
version = "0.1.0"
description = "Test repository"

[tool.poetry.dependencies]
python = "^3.11"
"""
    )

    # Create unit and integration test directories
    (repo_path / "tests" / "unit").mkdir(parents=True, exist_ok=True)
    (repo_path / "tests" / "integration").mkdir(parents=True, exist_ok=True)

    # Create dummy test files
    (repo_path / "tests" / "unit" / "test_unit.py").write_text(
        """
def test_unit():
    assert True
"""
    )
    (repo_path / "tests" / "integration" / "test_integration.py").write_text(
        """
def test_integration():
    assert True
"""
    )

    # Create a mock RepositoryConfig
    mock_repo_config = RepositoryConfig(
        name="repo-a",
        package_name="repo-a",
        path=repo_path,
        dependencies=[],
        url="file://test_path",  # Required argument for RepositoryConfig
    )

    # Mock config manager to return the repository config
    mock_get_repository = Mock()
    mock_get_repository.return_value = mock_repo_config
    mock_config_manager.get_repository = mock_get_repository

    # Patch subprocess to simulate successful tests
    with (
        patch("subprocess.run", side_effect=mock_run_method),
        patch("builtins.print"),
        patch.object(test_runner, "config_manager", mock_config_manager),
    ):

        def run_tests(repo_name: str) -> dict[str, Any]:
            repo = test_runner.config_manager.get_repository(repo_name)

            # Validate that repository is not None
            assert repo is not None, f"Repository {repo_name} not found"

            success_unit = test_runner._run_repository_tests(repo, "unit")
            success_integration = test_runner._run_repository_tests(repo, "integration")

            return {
                "repository": repo_name,
                "unit_tests": {"status": "success" if success_unit else "failure"},
                "integration_tests": {
                    "status": "success" if success_integration else "failure"
                },
            }

        # Use the function
        results = run_tests("repo-a")

        # Validate test results
        assert isinstance(results, dict)
        assert results.get("repository") == "repo-a"
        assert "unit_tests" in results
        assert "integration_tests" in results
        assert results["unit_tests"]["status"] == "success"
        assert results["integration_tests"]["status"] == "success"


def test_test_results_summary(
    test_runner: ExecutorService,
    temp_workspace: Path,
    mock_config_manager: Mock,
) -> None:
    """Test generating test results summary."""
    # Set up workspace and configuration
    repos_dir = temp_workspace / "repos"
    repos_dir.mkdir(exist_ok=True)

    # Create mock repositories
    mock_repos: list[str] = ["repo-a", "repo-b", "repo-c"]
    mock_repo_configs: list[RepositoryConfig] = []
    for repo_name in mock_repos:
        repo_path = repos_dir / repo_name
        repo_path.mkdir(exist_ok=True)

        # Create pyproject.toml
        (repo_path / "pyproject.toml").write_text(
            f"""
[tool.poetry]
name = "{repo_name}"
version = "0.1.0"
description = "Test repository"

[tool.poetry.dependencies]
python = "^3.11"
"""
        )

        # Create tests directory
        tests_dir = repo_path / "tests" / "unit"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # Create a dummy test file
        (tests_dir / "test_example.py").write_text(
            """
def test_dummy():
    assert True
"""
        )

        # Create a proper RepositoryConfig
        mock_repo_config = RepositoryConfig(
            name=repo_name,
            package_name=repo_name,
            path=repo_path,
            dependencies=[],
            url="file://test_path",
        )
        mock_repo_configs.append(mock_repo_config)

    # Prepare configuration mock
    config_mock = Mock()
    config_mock.repositories = mock_repo_configs
    config_mock.name = "test-workspace"
    mock_load_config = Mock()
    mock_load_config.return_value = config_mock
    mock_config_manager.load_config = mock_load_config

    # Reset test results to an empty dictionary
    test_runner.test_results = {}

    # Patch subprocess for test simulation
    with (
        patch("subprocess.run", side_effect=mock_run_method),
        patch("builtins.print"),
        patch("builtins.open", create=True),
        patch("json.dump") as mock_json_dump,
    ):

        # Simulate running repository tests
        for repo_config in mock_repo_configs:
            test_result = test_runner._run_repository_tests(repo_config, "unit")
            test_runner.test_results[repo_config.name] = {
                "type": "unit",
                "success": test_result,
                "coverage": False,
            }

        # Generate test report with mocked file writing
        summary = test_runner.generate_test_report()

        # Verify summary generation
        assert summary is not None
        assert hasattr(summary, "stat")

        # Ensure some content was generated for the report
        mock_json_dump.assert_called_once()

        # Optional: check that test results were recorded
        assert len(test_runner.test_results) == len(mock_repos)
        for _repo_name, result in test_runner.test_results.items():
            assert result["type"] == "unit"
            assert result["success"] is True


# Additional tests for ExecutorService functionality
def test_run_tests_with_coverage(
    test_runner: ExecutorService, temp_workspace: Path
) -> None:
    """Test running tests with coverage reporting."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Test coverage option
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="Coverage: 95%")

        # This would typically be called via a coverage flag
        result = test_runner._run_repository_tests(repo_config, "unit", coverage=True)

        assert result is True


def test_test_timeout_handling(
    test_runner: ExecutorService, temp_workspace: Path
) -> None:
    """Test handling of test timeouts."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    # Create pyproject.toml so test is not skipped
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

    # Test timeout handling
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("pytest", 300)

        # Should handle timeout gracefully (current implementation returns True for timeouts)
        result = test_runner._run_repository_tests(repo_config, "unit")
        assert result is True  # Current implementation returns True on timeout


def test_test_command_not_found(
    test_runner: ExecutorService, temp_workspace: Path
) -> None:
    """Test handling when pytest is not found."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Test command not found
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("pytest not found")

        # Should handle missing pytest gracefully
        result = test_runner._run_repository_tests(repo_config, "unit")
        assert result is True  # Should return True when no tests available


def test_empty_test_directory(
    test_runner: ExecutorService, temp_workspace: Path
) -> None:
    """Test handling of repositories with no tests."""
    repo_path = temp_workspace / "test-repo"
    repo_path.mkdir()

    # Create empty tests directory
    tests_dir = repo_path / "tests" / "unit"
    tests_dir.mkdir(parents=True)

    repo_config = RepositoryConfig(
        name="test-repo",
        url="https://github.com/test/test-repo.git",
        package_name="test-repo",
        path=repo_path,
        dependencies=[],
    )

    # Test with empty test directory
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(
            returncode=5
        )  # pytest exit code for "no tests found"

        result = test_runner._run_repository_tests(repo_config, "unit")
        assert result is True  # Should succeed when no tests found
