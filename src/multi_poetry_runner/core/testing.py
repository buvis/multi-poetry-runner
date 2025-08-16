"""Testing functionality for MPR."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..utils.config import ConfigManager, RepositoryConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class TestRunner:
    """Runs various types of tests across repositories."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.workspace_root = config_manager.workspace_root
        self.test_results = {}

    def run_unit_tests(self, parallel: bool = False, coverage: bool = False) -> bool:
        """Run unit tests in all repositories."""
        config = self.config_manager.load_config()

        console.print("\n[bold]Running unit tests...[/bold]")

        if parallel:
            return self._run_tests_parallel(config.repositories, "unit", coverage)
        else:
            return self._run_tests_sequential(config.repositories, "unit", coverage)

    def run_integration_tests(
        self,
        parallel: bool = False,
        environment: str = "local",
        junit_output: bool = False,
    ) -> bool:
        """Run integration tests."""
        console.print("\n[bold]Running integration tests...[/bold]")

        if environment == "docker":
            return self._run_integration_tests_docker(junit_output)
        else:
            return self._run_integration_tests_local(parallel, junit_output)

    def _run_tests_sequential(
        self,
        repositories: list[RepositoryConfig],
        test_type: str,
        coverage: bool = False,
    ) -> bool:
        """Run tests sequentially across repositories."""

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Running {test_type} tests...", total=len(repositories)
            )

            all_passed = True

            for repo in repositories:
                if not repo.path.exists():
                    continue

                progress.update(task, description=f"Testing {repo.name}...")

                success = self._run_repository_tests(repo, test_type, coverage)
                self.test_results[repo.name] = {
                    "type": test_type,
                    "success": success,
                    "coverage": coverage,
                }

                if not success:
                    all_passed = False

                progress.advance(task)

        self._print_test_results()

        return all_passed

    def _run_tests_parallel(
        self,
        repositories: list[RepositoryConfig],
        test_type: str,
        coverage: bool = False,
    ) -> bool:
        """Run tests in parallel across repositories."""

        console.print(f"Running {test_type} tests in parallel...")

        all_passed = True

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(
                    self._run_repository_tests, repo, test_type, coverage
                ): repo
                for repo in repositories
                if repo.path.exists()
            }

            for future in as_completed(futures):
                repo = futures[future]

                try:
                    success = future.result()
                    self.test_results[repo.name] = {
                        "type": test_type,
                        "success": success,
                        "coverage": coverage,
                    }

                    if not success:
                        all_passed = False

                except Exception as e:
                    logger.error(f"Error running tests for {repo.name}: {e}")
                    self.test_results[repo.name] = {
                        "type": test_type,
                        "success": False,
                        "error": str(e),
                    }
                    all_passed = False

        self._print_test_results()

        return all_passed

    def _run_repository_tests(
        self, repo: RepositoryConfig, test_type: str, coverage: bool = False
    ) -> bool:
        """Run tests for a single repository."""

        if not (repo.path / "pyproject.toml").exists():
            logger.warning(f"No pyproject.toml found in {repo.name}, skipping tests")

            return True

        # Check if tests directory exists
        tests_dir = repo.path / "tests"

        if not tests_dir.exists():
            logger.info(f"No tests directory in {repo.name}, skipping")

            return True

        # Build pytest command
        cmd = ["poetry", "run", "pytest", "-v"]

        if coverage:
            cmd.extend(["--cov", "--cov-report=term", "--cov-report=xml"])

        # Add specific test directory if needed

        if test_type == "unit":
            if (tests_dir / "unit").exists():
                cmd.append(str(tests_dir / "unit"))
            else:
                cmd.append(str(tests_dir))
        elif test_type == "integration":
            if (tests_dir / "integration").exists():
                cmd.append(str(tests_dir / "integration"))

        try:
            result = subprocess.run(
                cmd, cwd=repo.path, capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                logger.info(f"✓ Tests passed for {repo.name}")

                return True
            else:
                logger.error(f"✗ Tests failed for {repo.name}")
                logger.error(result.stdout)
                logger.error(result.stderr)

                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Tests timed out for {repo.name}")

            return False
        except Exception as e:
            logger.error(f"Error running tests for {repo.name}: {e}")

            return False

    def _run_integration_tests_local(
        self, parallel: bool = False, junit_output: bool = False
    ) -> bool:
        """Run integration tests in local environment."""

        # Look for integration test configuration
        integration_config = self.workspace_root / "integration-tests.yaml"

        if not integration_config.exists():
            logger.info("No integration test configuration found, creating default")
            self._create_default_integration_config()

        # Run integration test framework
        cmd = ["python", "-m", "multi_poetry_runner.core.integration_framework"]
        cmd.append(str(integration_config))

        if junit_output:
            cmd.extend(["--junit-output"])

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes
            )

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.error("Integration tests timed out")

            return False
        except Exception as e:
            logger.error(f"Error running integration tests: {e}")

            return False

    def _run_integration_tests_docker(self, junit_output: bool = False) -> bool:
        """Run integration tests in Docker environment."""

        # Check if Docker is available

        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Docker is not available")

            return False

        # Look for docker-compose test configuration
        docker_compose_test = self.workspace_root / "docker-compose.test.yml"

        if not docker_compose_test.exists():
            logger.info("No Docker test configuration found, creating default")
            self._create_default_docker_config()

        try:
            # Build and run tests
            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    "docker-compose.test.yml",
                    "up",
                    "--build",
                    "--abort-on-container-exit",
                ],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=1800,
            )

            # Clean up
            subprocess.run(
                ["docker-compose", "-f", "docker-compose.test.yml", "down"],
                cwd=self.workspace_root,
                capture_output=True,
            )

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.error("Docker integration tests timed out")

            return False
        except Exception as e:
            logger.error(f"Error running Docker integration tests: {e}")

            return False

    def _create_default_integration_config(self) -> None:
        """Create default integration test configuration."""
        config = self.config_manager.load_config()

        integration_config = {
            "name": f"{config.name}-integration",
            "description": "Integration tests for the complete package stack",
            "environment": "local",
            "python_version": config.python_version,
            "packages": [],
            "tests": [
                "tests/integration/test_basic_integration.py",
                "tests/integration/test_data_flow.py",
            ],
            "timeout": 600,
            "parallel": False,
            "cleanup": True,
        }

        # Add packages from configuration

        for repo in config.repositories:
            package_config = {
                "name": repo.package_name,
                "source": "local",
                "location": str(repo.path),
                "dependencies": repo.dependencies,
            }
            integration_config["packages"].append(package_config)

        # Write configuration
        import yaml

        config_path = self.workspace_root / "integration-tests.yaml"
        with open(config_path, "w") as f:
            yaml.dump(integration_config, f, default_flow_style=False)

        # Create test directory and basic tests
        test_dir = self.workspace_root / "tests" / "integration"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Create basic integration test
        basic_test = test_dir / "test_basic_integration.py"

        if not basic_test.exists():
            basic_test.write_text(self._get_basic_integration_test_template())

    def _create_default_docker_config(self) -> None:
        """Create default Docker test configuration."""
        docker_compose_content = """
version: '3.8'

services:
  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.test
    volumes:
      - ./tests:/tests
      - ./reports:/reports
    environment:
      - PYTHONPATH=/app
    command: |
      python -m pytest /tests/integration
      --junit-xml=/reports/results.xml
      --html=/reports/report.html
      --self-contained-html
"""

        dockerfile_content = f"""
FROM python:{self.config_manager.load_config().python_version}-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy workspace
COPY . .

# Install all packages
RUN poetry config virtualenvs.create false
RUN for dir in repos/*/; do \\
        if [ -f "$dir/pyproject.toml" ]; then \\
            cd "$dir" && poetry install && cd /app; \\
        fi \\
    done

# Install test dependencies
RUN pip install pytest pytest-html pytest-timeout
"""

        # Write files
        (self.workspace_root / "docker-compose.test.yml").write_text(
            docker_compose_content.strip()
        )
        (self.workspace_root / "Dockerfile.test").write_text(dockerfile_content.strip())

    def _get_basic_integration_test_template(self) -> str:
        """Get template for basic integration test."""
        config = self.config_manager.load_config()

        imports = []
        test_code = []

        for repo in config.repositories:
            # Generate import statement
            package_name = repo.package_name.replace("-", "_")
            imports.append(f"    import {package_name}")

            # Generate basic test code
            test_code.append(f"    assert {package_name} is not None")

        template = f'''"""Basic integration tests."""

import pytest


def test_package_imports():
    """Test that all packages can be imported."""
{chr(10).join(imports)}

{chr(10).join(test_code)}


def test_basic_functionality():
    """Test basic functionality across packages."""
    # TODO: Add specific tests for your workflow
    pass


@pytest.mark.asyncio
async def test_async_operations():
    """Test async operations if applicable."""
    # TODO: Add async tests if needed
    pass
'''

        return template

    def _print_test_results(self) -> None:
        """Print test results in a formatted table."""

        if not self.test_results:
            return

        table = Table(title="Test Results")
        table.add_column("Repository", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Coverage", style="yellow")

        for repo_name, result in self.test_results.items():
            status_icon = "✓" if result["success"] else "✗"
            status_color = "green" if result["success"] else "red"
            coverage_info = "✓" if result.get("coverage") else ""

            table.add_row(
                repo_name,
                result["type"],
                f"[{status_color}]{status_icon}[/{status_color}]",
                coverage_info,
            )

        console.print(table)

        # Print summary
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results.values() if r["success"])
        failed_tests = total_tests - passed_tests

        console.print(
            f"\n[bold]Summary: {passed_tests}/{total_tests} passed, {failed_tests} failed[/bold]"
        )

    def generate_test_report(self, output_format: str = "json") -> Path | None:
        """Generate a test report."""

        if not self.test_results:
            return None

        report_data = {
            "timestamp": str(datetime.now()),
            "workspace": self.config_manager.load_config().name,
            "results": self.test_results,
            "summary": {
                "total": len(self.test_results),
                "passed": sum(1 for r in self.test_results.values() if r["success"]),
                "failed": sum(
                    1 for r in self.test_results.values() if not r["success"]
                ),
            },
        }

        # Ensure reports directory exists
        reports_dir = self.workspace_root / "reports"
        reports_dir.mkdir(exist_ok=True)

        if output_format == "json":
            report_path = reports_dir / "test-report.json"
            with open(report_path, "w") as f:
                json.dump(report_data, f, indent=2)
        elif output_format == "html":
            report_path = reports_dir / "test-report.html"
            html_content = self._generate_html_report(report_data)
            report_path.write_text(html_content)
        else:
            logger.error(f"Unsupported report format: {output_format}")

            return None

        logger.info(f"Test report generated: {report_path}")

        return report_path

    def _generate_html_report(self, report_data: dict[str, Any]) -> str:
        """Generate HTML test report."""

        html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Report - {workspace}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .results {{ margin: 20px 0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Test Report</h1>
        <p><strong>Workspace:</strong> {workspace}</p>
        <p><strong>Generated:</strong> {timestamp}</p>
    </div>

    <div class="summary">
        <h2>Summary</h2>
        <p>Total: {total}, Passed: <span class="passed">{passed}</span>, Failed: <span class="failed">{failed}</span></p>
    </div>

    <div class="results">
        <h2>Results</h2>
        <table>
            <tr>
                <th>Repository</th>
                <th>Type</th>
                <th>Status</th>
                <th>Coverage</th>
            </tr>
            {rows}
        </table>
    </div>
</body>
</html>
"""

        rows = []

        for repo_name, result in report_data["results"].items():
            status_class = "passed" if result["success"] else "failed"
            status_text = "✓ Passed" if result["success"] else "✗ Failed"
            coverage_text = "✓" if result.get("coverage") else ""

            row = f"""
            <tr>
                <td>{repo_name}</td>
                <td>{result["type"]}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{coverage_text}</td>
            </tr>
            """
            rows.append(row)

        return html_template.format(
            workspace=report_data["workspace"],
            timestamp=report_data["timestamp"],
            total=report_data["summary"]["total"],
            passed=report_data["summary"]["passed"],
            failed=report_data["summary"]["failed"],
            rows="".join(rows),
        )
