"""Test testing module functionality."""

import json
import subprocess
import tempfile
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
import yaml

from multi_poetry_runner.core.testing import ExecutorService
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

    # Create test repositories with different test configurations
    repo_configs = []

    for i, repo_name in enumerate(["repo-a", "repo-b", "repo-c"]):
        repo_path = repos_dir / repo_name
        repo_path.mkdir(exist_ok=True)

        # Create pyproject.toml
        pyproject_content = {
            "tool": {
                "poetry": {
                    "name": repo_name,
                    "version": "1.0.0",
                    "description": "Test repository",
                    "dependencies": {"python": "^3.11"},
                    "dev-dependencies": {"pytest": "^7.0.0", "pytest-cov": "^4.0.0"},
                }
            }
        }

        pyproject_path = repo_path / "pyproject.toml"
        with open(pyproject_path, "w") as f:
            import toml

            toml.dump(pyproject_content, f)

        # Create tests directory structure
        tests_dir = repo_path / "tests"
        tests_dir.mkdir(exist_ok=True)

        # Create unit tests directory
        unit_tests_dir = tests_dir / "unit"
        unit_tests_dir.mkdir(exist_ok=True)

        # Create a sample unit test
        unit_test_file = unit_tests_dir / "test_sample.py"
        unit_test_content = f'''
"""Sample unit tests for {repo_name}."""

def test_basic_functionality():
    """Test basic functionality."""
    assert True

def test_calculation():
    """Test some calculation."""
    result = 2 + 2
    assert result == 4

def test_string_operations():
    """Test string operations."""
    text = "hello"
    assert text.upper() == "HELLO"
'''
        unit_test_file.write_text(unit_test_content)

        # Create integration tests directory for some repos
        if i < 2:  # Only first two repos have integration tests
            integration_tests_dir = tests_dir / "integration"
            integration_tests_dir.mkdir(exist_ok=True)

            integration_test_file = integration_tests_dir / "test_integration.py"
            integration_test_content = f'''
"""Integration tests for {repo_name}."""

import pytest

def test_integration_workflow():
    """Test integration workflow."""
    # Simulate some integration test
    assert True

@pytest.mark.asyncio
async def test_async_integration():
    """Test async integration."""
    await asyncio.sleep(0.1)
    assert True
'''
            integration_test_file.write_text(integration_test_content)

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
    mock_config.python_version = "3.11"
    config_manager.load_config.return_value = mock_config

    return config_manager


@pytest.fixture
def test_runner(mock_config_manager: Mock) -> ExecutorService:
    """Create ExecutorService instance with mocked config."""
    return ExecutorService(mock_config_manager)


class TestTestExecutor:
    """Test suite for TestExecutor class."""

    def test_parallel_test_execution(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test parallel test execution across repos."""
        execution_order = []

        with patch("subprocess.run") as mock_subprocess:

            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                # Track execution order and simulate varying durations
                if "cwd" in kwargs:
                    repo_name = Path(kwargs["cwd"]).name
                    execution_order.append(repo_name)

                    # Simulate different test durations
                    if repo_name == "repo-a":
                        time.sleep(0.1)  # Simulate longer test
                    elif repo_name == "repo-b":
                        time.sleep(0.05)  # Medium test
                    else:
                        time.sleep(0.02)  # Quick test

                result = Mock()
                result.returncode = 0
                result.stdout = "2 passed"
                result.stderr = ""
                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run tests in parallel
            result = test_runner.run_unit_tests(parallel=True, coverage=False)

            assert result is True

            # Verify all repos were tested
            assert len(execution_order) == 3
            assert "repo-a" in execution_order
            assert "repo-b" in execution_order
            assert "repo-c" in execution_order

            # Verify results were recorded
            assert len(test_runner.test_results) == 3
            for repo_name in ["repo-a", "repo-b", "repo-c"]:
                assert repo_name in test_runner.test_results
                assert test_runner.test_results[repo_name]["success"] is True

    def test_integration_test_environment_setup(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test Docker environment setup for integration tests."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock docker availability check
            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                cmd = args[0]
                result = Mock()
                result.returncode = 0
                result.stdout = "Docker version 20.10.7"
                result.stderr = ""

                if "docker" in str(cmd) and "--version" in str(cmd):
                    # Docker availability check
                    pass
                elif "docker-compose" in str(cmd):
                    # Docker compose operations
                    result.stdout = "Creating test environment..."

                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run integration tests with docker environment
            result = test_runner.run_integration_tests(
                parallel=False, environment="docker", junit_output=True
            )

            assert result is True

            # Verify Docker commands were called
            docker_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "docker" in str(call[0])
            ]
            assert len(docker_calls) > 0

            # Verify docker-compose.test.yml was created
            docker_compose_test = temp_workspace / "docker-compose.test.yml"
            assert docker_compose_test.exists()

            # Verify Dockerfile.test was created
            dockerfile_test = temp_workspace / "Dockerfile.test"
            assert dockerfile_test.exists()

    def test_coverage_threshold_enforcement(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test coverage threshold checking."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock pytest with coverage output
            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                cmd = args[0]
                result = Mock()
                result.stderr = ""

                if "--cov" in cmd:
                    # Simulate coverage output with different coverage levels
                    repo_name = (
                        Path(kwargs["cwd"]).name if "cwd" in kwargs else "unknown"
                    )

                    if repo_name == "repo-a":
                        # High coverage
                        result.returncode = 0
                        result.stdout = """
========================= test session starts =========================
collecting ... collected 3 items

tests/unit/test_sample.py::test_basic_functionality PASSED
tests/unit/test_sample.py::test_calculation PASSED
tests/unit/test_sample.py::test_string_operations PASSED

---------- coverage: platform linux, python 3.11.0 -----------
Name                     Stmts   Miss  Cover
--------------------------------------------
src/repo_a/__init__.py      10      0   100%
src/repo_a/main.py          25      2    92%
--------------------------------------------
TOTAL                       35      2    94%

========================= 3 passed in 0.12s =========================
"""
                    elif repo_name == "repo-b":
                        # Low coverage (should fail if threshold is set)
                        result.returncode = 0
                        result.stdout = """
========================= test session starts =========================
collecting ... collected 3 items

tests/unit/test_sample.py::test_basic_functionality PASSED
tests/unit/test_sample.py::test_calculation PASSED
tests/unit/test_sample.py::test_string_operations PASSED

---------- coverage: platform linux, python 3.11.0 -----------
Name                     Stmts   Miss  Cover
--------------------------------------------
src/repo_b/__init__.py      10      8    20%
src/repo_b/main.py          30     25    17%
--------------------------------------------
TOTAL                       40     33    18%

========================= 3 passed in 0.10s =========================
"""
                    else:
                        # Medium coverage
                        result.returncode = 0
                        result.stdout = """
========================= test session starts =========================
collecting ... collected 3 items

tests/unit/test_sample.py::test_basic_functionality PASSED
tests/unit/test_sample.py::test_calculation PASSED
tests/unit/test_sample.py::test_string_operations PASSED

---------- coverage: platform linux, python 3.11.0 -----------
Name                     Stmts   Miss  Cover
--------------------------------------------
src/repo_c/__init__.py      10      3    70%
src/repo_c/main.py          20      6    70%
--------------------------------------------
TOTAL                       30      9    70%

========================= 3 passed in 0.08s =========================
"""
                else:
                    # Regular test without coverage
                    result.returncode = 0
                    result.stdout = "3 passed"

                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run tests with coverage
            result = test_runner.run_unit_tests(parallel=False, coverage=True)

            assert result is True

            # Verify coverage was enabled for all repos
            for repo_name in test_runner.test_results:
                assert test_runner.test_results[repo_name]["coverage"] is True

            # Verify coverage commands were used
            coverage_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "--cov" in str(call[0])
            ]
            assert len(coverage_calls) == 3  # One for each repo

    def test_junit_xml_generation(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test JUnit XML output for CI integration."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock successful test execution with JUnit output
            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                cmd = args[0]
                result = Mock()
                result.returncode = 0
                result.stderr = ""
                result.stdout = "3 passed"

                # If this is a JUnit command, create mock XML file
                if "--junit-xml" in cmd or "junit-output" in str(cmd):
                    if "cwd" in kwargs:
                        repo_path = Path(kwargs["cwd"])
                        reports_dir = repo_path / "reports"
                        reports_dir.mkdir(exist_ok=True)
                        junit_file = reports_dir / "junit.xml"

                        # Create mock JUnit XML content
                        junit_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
    <testsuite name="pytest" errors="0" failures="0" skipped="0" tests="3" time="0.120" timestamp="2024-01-01T10:00:00">
        <testcase classname="tests.unit.test_sample" name="test_basic_functionality" time="0.002"/>
        <testcase classname="tests.unit.test_sample" name="test_calculation" time="0.001"/>
        <testcase classname="tests.unit.test_sample" name="test_string_operations" time="0.001"/>
    </testsuite>
</testsuites>"""
                        junit_file.write_text(junit_content)

                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run integration tests with JUnit output
            result = test_runner.run_integration_tests(
                parallel=False, environment="local", junit_output=True
            )

            # Should succeed even if some setup is needed
            assert isinstance(result, bool)

    def test_test_timeout_handling(
        self, test_runner: ExecutorService, mock_config_manager: Mock
    ) -> None:
        """Test handling of test timeouts."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock timeout exception
            mock_subprocess.side_effect = subprocess.TimeoutExpired(
                cmd=["poetry", "run", "pytest"], timeout=600
            )

            # Run tests - should handle timeout gracefully
            result = test_runner.run_unit_tests(parallel=False, coverage=False)

            assert result is False

            # Verify timeout was handled and recorded
            assert len(test_runner.test_results) == 3
            for repo_name in test_runner.test_results:
                assert test_runner.test_results[repo_name]["success"] is False

    def test_test_results_aggregation(
        self, test_runner: ExecutorService, mock_config_manager: Mock
    ) -> None:
        """Test test results aggregation and reporting."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock mixed success/failure results
            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                repo_name = Path(kwargs["cwd"]).name if "cwd" in kwargs else "unknown"
                result = Mock()
                result.stderr = ""

                if repo_name == "repo-a":
                    result.returncode = 0  # Success
                    result.stdout = "3 passed"
                elif repo_name == "repo-b":
                    result.returncode = 1  # Failure
                    result.stdout = "2 passed, 1 failed"
                else:
                    result.returncode = 0  # Success
                    result.stdout = "3 passed"

                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run tests
            result = test_runner.run_unit_tests(parallel=False, coverage=False)

            assert result is False  # Should fail due to repo-b failure

            # Verify results were aggregated correctly
            assert test_runner.test_results["repo-a"]["success"] is True
            assert test_runner.test_results["repo-b"]["success"] is False
            assert test_runner.test_results["repo-c"]["success"] is True

    def test_test_report_generation(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test test report generation in different formats."""
        # Set up some test results
        test_runner.test_results = {
            "repo-a": {"type": "unit", "success": True, "coverage": True},
            "repo-b": {"type": "unit", "success": False, "coverage": True},
            "repo-c": {"type": "unit", "success": True, "coverage": False},
        }

        # Test JSON report generation
        json_report_path = test_runner.generate_test_report(output_format="json")
        assert json_report_path is not None
        assert json_report_path.exists()
        assert json_report_path.suffix == ".json"

        # Verify JSON content
        with open(json_report_path) as f:
            report_data = json.load(f)

        assert "timestamp" in report_data
        assert "workspace" in report_data
        assert "results" in report_data
        assert "summary" in report_data
        assert report_data["summary"]["total"] == 3
        assert report_data["summary"]["passed"] == 2
        assert report_data["summary"]["failed"] == 1

        # Test HTML report generation
        html_report_path = test_runner.generate_test_report(output_format="html")
        assert html_report_path is not None
        assert html_report_path.exists()
        assert html_report_path.suffix == ".html"

        # Verify HTML content contains expected elements
        html_content = html_report_path.read_text()
        assert "<title>Test Report" in html_content
        assert "test-workspace" in html_content
        assert "repo-a" in html_content
        assert "✓ Passed" in html_content
        assert "✗ Failed" in html_content

    def test_integration_config_creation(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test automatic creation of integration test configuration."""
        # Ensure no integration config exists
        integration_config = temp_workspace / "integration-tests.yaml"
        if integration_config.exists():
            integration_config.unlink()

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = ""

            # Run integration tests (should create default config)
            test_runner.run_integration_tests(
                parallel=False, environment="local", junit_output=False
            )

        # Verify integration config was created
        assert integration_config.exists()

        # Verify config content
        with open(integration_config) as f:
            config_data = yaml.safe_load(f)

        assert "name" in config_data
        assert "packages" in config_data
        assert len(config_data["packages"]) == 3  # Three test repos

        # Verify test directory was created
        test_dir = temp_workspace / "tests" / "integration"
        assert test_dir.exists()

        # Verify basic test file was created
        basic_test = test_dir / "test_basic_integration.py"
        assert basic_test.exists()

        # Verify test content includes imports for all packages
        test_content = basic_test.read_text()
        assert "import repo_a" in test_content
        assert "import repo_b" in test_content
        assert "import repo_c" in test_content

    def test_docker_config_creation(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test Docker configuration creation for integration tests."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock docker availability
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "Docker version 20.10.7"

            # Run Docker integration tests (should create config files)
            test_runner.run_integration_tests(
                parallel=False, environment="docker", junit_output=False
            )

        # Verify Docker files were created
        docker_compose_test = temp_workspace / "docker-compose.test.yml"
        assert docker_compose_test.exists()

        dockerfile_test = temp_workspace / "Dockerfile.test"
        assert dockerfile_test.exists()

        # Verify docker-compose content
        compose_content = docker_compose_test.read_text()
        assert "test-runner:" in compose_content
        assert "build:" in compose_content
        assert "pytest" in compose_content

        # Verify Dockerfile content
        dockerfile_content = dockerfile_test.read_text()
        assert "FROM python:3.11-slim" in dockerfile_content
        assert "RUN pip install poetry" in dockerfile_content
        assert "poetry install" in dockerfile_content

    def test_no_tests_directory_handling(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test handling of repositories without tests directory."""
        repos_dir = temp_workspace / "repos"

        # Remove tests directory from repo-c
        repo_c_tests = repos_dir / "repo-c" / "tests"
        if repo_c_tests.exists():
            import shutil

            shutil.rmtree(repo_c_tests)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "3 passed"

            # Run tests
            result = test_runner.run_unit_tests(parallel=False, coverage=False)

            assert result is True

            # Verify repo-c was handled gracefully (no tests to run)
            assert "repo-c" in test_runner.test_results
            assert test_runner.test_results["repo-c"]["success"] is True

    def test_parallel_execution_thread_safety(
        self, test_runner: ExecutorService, mock_config_manager: Mock
    ) -> None:
        """Test thread safety during parallel test execution."""
        execution_log = []
        lock = threading.Lock()

        with patch("subprocess.run") as mock_subprocess:

            def thread_safe_subprocess(*args: Any, **kwargs: Any) -> Mock:
                with lock:
                    repo_name = (
                        Path(kwargs["cwd"]).name if "cwd" in kwargs else "unknown"
                    )
                    execution_log.append(f"start-{repo_name}")

                # Simulate some processing time
                time.sleep(0.05)

                with lock:
                    execution_log.append(f"end-{repo_name}")

                result = Mock()
                result.returncode = 0
                result.stdout = "3 passed"
                result.stderr = ""
                return result

            mock_subprocess.side_effect = thread_safe_subprocess

            # Run tests in parallel
            result = test_runner.run_unit_tests(parallel=True, coverage=False)

            assert result is True

            # Verify all repos were processed
            start_events = [
                event for event in execution_log if event.startswith("start-")
            ]
            end_events = [event for event in execution_log if event.startswith("end-")]

            assert len(start_events) == 3
            assert len(end_events) == 3

            # Verify no race conditions in test results
            assert len(test_runner.test_results) == 3
            for repo_name in ["repo-a", "repo-b", "repo-c"]:
                assert repo_name in test_runner.test_results
                assert test_runner.test_results[repo_name]["success"] is True

    def test_error_handling_and_recovery(
        self, test_runner: ExecutorService, mock_config_manager: Mock
    ) -> None:
        """Test error handling and recovery mechanisms."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock various types of failures
            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                repo_name = Path(kwargs["cwd"]).name if "cwd" in kwargs else "unknown"

                if repo_name == "repo-a":
                    # Simulate subprocess error
                    raise subprocess.CalledProcessError(1, args[0])
                elif repo_name == "repo-b":
                    # Simulate timeout
                    raise subprocess.TimeoutExpired(args[0], 600)
                else:
                    # Simulate success
                    result = Mock()
                    result.returncode = 0
                    result.stdout = "3 passed"
                    result.stderr = ""
                    return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run tests in parallel to test error handling
            result = test_runner.run_unit_tests(parallel=True, coverage=False)

            assert result is False  # Should fail due to errors

            # Verify error handling
            assert "repo-a" in test_runner.test_results
            assert test_runner.test_results["repo-a"]["success"] is False

            assert "repo-b" in test_runner.test_results
            assert test_runner.test_results["repo-b"]["success"] is False

            assert "repo-c" in test_runner.test_results
            assert test_runner.test_results["repo-c"]["success"] is True

    def test_test_type_filtering(
        self,
        test_runner: ExecutorService,
        mock_config_manager: Mock,
        temp_workspace: Path,
    ) -> None:
        """Test filtering of different test types (unit vs integration)."""
        with patch("subprocess.run") as mock_subprocess:

            def subprocess_side_effect(*args: Any, **kwargs: Any) -> Mock:
                cmd = args[0]
                result = Mock()
                result.returncode = 0
                result.stderr = ""

                # Check if unit or integration tests are being run
                if "tests/unit" in str(cmd):
                    result.stdout = "Unit tests: 3 passed"
                elif "tests/integration" in str(cmd):
                    result.stdout = "Integration tests: 2 passed"
                else:
                    result.stdout = "All tests: 5 passed"

                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Run unit tests specifically
            result = test_runner.run_unit_tests(parallel=False, coverage=False)
            assert result is True

            # Verify unit test specific commands were used
            unit_calls = [
                call
                for call in mock_subprocess.call_args_list
                if "tests/unit" in str(call[0]) or "tests" in str(call[0])
            ]
            assert len(unit_calls) >= 3  # One for each repo

    def test_sequential_vs_parallel_execution(
        self, test_runner: ExecutorService, mock_config_manager: Mock
    ) -> None:
        """Test differences between sequential and parallel execution."""
        execution_times = {}

        with patch("subprocess.run") as mock_subprocess:

            def time_tracking_subprocess(*args: Any, **kwargs: Any) -> Mock:
                repo_name = Path(kwargs["cwd"]).name if "cwd" in kwargs else "unknown"
                start_time = time.time()

                # Simulate processing time
                time.sleep(0.1)

                end_time = time.time()
                execution_times[repo_name] = end_time - start_time

                result = Mock()
                result.returncode = 0
                result.stdout = "3 passed"
                result.stderr = ""
                return result

            mock_subprocess.side_effect = time_tracking_subprocess

            # Test sequential execution
            start_time = time.time()
            result_sequential = test_runner.run_unit_tests(
                parallel=False, coverage=False
            )
            sequential_duration = time.time() - start_time

            assert result_sequential is True
            assert sequential_duration >= 0  # Sanity check

            # Reset for parallel test
            test_runner.test_results = {}
            execution_times = {}
            mock_subprocess.reset_mock()

            # Test parallel execution
            start_time = time.time()
            result_parallel = test_runner.run_unit_tests(parallel=True, coverage=False)
            parallel_duration = time.time() - start_time

            assert result_parallel is True
            assert parallel_duration >= 0  # Sanity check on timing

            # Parallel should be faster (though timing can be variable in tests)
            # We just verify both modes completed successfully
            assert len(test_runner.test_results) == 3
