"""Test testing module functionality."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

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

    # Mock repositories in config manager
    config_mock = Mock()
    config_mock.repositories = [
        Mock(name=repo_name, path=repos_dir / repo_name) for repo_name in mock_repos
    ]
    mock_config_manager.load_config.return_value = config_mock

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
) -> None:
    """Test running integration tests across repositories."""
    # Run integration tests
    results = test_runner.run_integration_tests()

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
    mock_repo_config: RepositoryConfig = Mock(
        name="repo-a", package_name="repo-a", path=repo_path
    )

    # Mock config manager to return the repository config
    mock_config_manager.get_repository.return_value = mock_repo_config

    # Patch subprocess to simulate successful tests
    with patch("subprocess.run", side_effect=mock_run_method):
        # Create a temporary capture of print output
        with patch("builtins.print"):
            # Prepare a function to run tests for a specific repository
            def run_tests(repo_name: str) -> dict[str, Any]:
                # Capture the current get_repository method
                original_get_repository = test_runner.config_manager.get_repository

                try:
                    # Override the method temporarily
                    test_runner.config_manager.get_repository = (
                        lambda name: mock_repo_config
                    )

                    repo = test_runner.config_manager.get_repository(repo_name)
                    success_unit = test_runner._run_repository_tests(repo, "unit")
                    success_integration = test_runner._run_repository_tests(
                        repo, "integration"
                    )

                    return {
                        "repository": repo_name,
                        "unit_tests": {
                            "status": "success" if success_unit else "failure"
                        },
                        "integration_tests": {
                            "status": "success" if success_integration else "failure"
                        },
                    }
                finally:
                    # Restore the original method
                    test_runner.config_manager.get_repository = original_get_repository

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
    mock_repo_configs: list[Mock] = []
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

        # Create mock repository config
        mock_repo_config = Mock(name=repo_name, package_name=repo_name, path=repo_path)
        mock_repo_configs.append(mock_repo_config)

    # Prepare configuration mock
    config_mock = Mock()
    config_mock.repositories = mock_repo_configs
    config_mock.name = "test-workspace"
    mock_config_manager.load_config.return_value = config_mock

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
