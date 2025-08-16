"""Workspace management functionality."""

import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..utils.config import ConfigManager, RepositoryConfig, WorkspaceConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class WorkspaceManager:
    """Manages development workspace operations."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.workspace_root = config_manager.workspace_root

    def initialize_workspace(self, name: str, python_version: str = "3.11") -> None:
        """Initialize a new workspace."""
        logger.info(f"Initializing workspace '{name}'")

        # Create workspace directory structure
        directories = ["repos", "logs", "backups", "scripts", "tests"]

        for directory in directories:
            (self.workspace_root / directory).mkdir(parents=True, exist_ok=True)

        # Create initial configuration
        config = WorkspaceConfig(
            name=name, python_version=python_version, repositories=[]
        )

        self.config_manager.save_config(config)

        # Create .gitignore
        gitignore_content = """
# Virtual environments
.venv/
venv/
**/venv/
**/.venv/

# Poetry
poetry.lock
**/poetry.lock
dist/
**/dist/
*.egg-info/
**/*.egg-info/

# Python
__pycache__/
**/__pycache__/
*.py[cod]
**/*.py[cod]
*.so

# MPR
logs/
backups/
.dependency-mode

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
"""

        gitignore_path = self.workspace_root / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(gitignore_content.strip())

        # Create Makefile
        makefile_content = """
# Makefile for MPR workspace
.PHONY: help dev remote test clean status

help:
	@echo "Available commands:"
	@echo "  make dev     - Switch to local development mode"
	@echo "  make remote  - Switch to remote dependencies"
	@echo "  make test    - Run all tests"
	@echo "  make clean   - Clean workspace"
	@echo "  make status  - Show workspace status"

dev:
	mpr deps switch local

remote:
	mpr deps switch remote

test:
	mpr test all

clean:
	mpr workspace clean

status:
	mpr workspace status
"""

        makefile_path = self.workspace_root / "Makefile"
        if not makefile_path.exists():
            makefile_path.write_text(makefile_content.strip())

        logger.info(f"Workspace '{name}' initialized at {self.workspace_root}")

    def add_repository(
        self,
        repo_url: str,
        name: str | None = None,
        dependencies: list[str] | None = None,
        branch: str = "main",
    ) -> None:
        """Add a repository to the workspace configuration."""

        # Auto-detect name if not provided
        if name is None:
            parsed_url = urlparse(repo_url)
            path_parts = parsed_url.path.strip("/").split("/")
            if len(path_parts) >= 2:
                name = path_parts[-1].replace(".git", "")
            else:
                raise ValueError("Cannot auto-detect repository name from URL")

        # Auto-detect package name (assume same as repo name for now)
        package_name = name.replace("-", "_")

        repo_config = RepositoryConfig(
            name=name,
            url=repo_url,
            package_name=package_name,
            path=self.workspace_root / "repos" / name,
            branch=branch,
            dependencies=dependencies or [],
        )

        self.config_manager.add_repository(repo_config)
        logger.info(f"Added repository '{name}' to workspace")

    def setup_workspace(self, ci_mode: bool = False) -> None:
        """Set up the workspace by cloning repositories and setting up environments."""
        config = self.config_manager.load_config()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            # Clone repositories
            task = progress.add_task(
                "Cloning repositories...", total=len(config.repositories)
            )

            for repo in config.repositories:
                progress.update(task, description=f"Cloning {repo.name}...")
                self._clone_repository(repo)
                progress.advance(task)

            # Set up Poetry environments
            task = progress.add_task(
                "Setting up environments...", total=len(config.repositories)
            )

            for repo in config.repositories:
                progress.update(task, description=f"Setting up {repo.name}...")
                self._setup_poetry_environment(repo, ci_mode)
                progress.advance(task)

            # Install git hooks if not in CI mode
            if not ci_mode:
                progress.add_task("Installing Git hooks...", total=1)
                self._install_git_hooks()

    def _clone_repository(self, repo: RepositoryConfig) -> None:
        """Clone a single repository."""
        if repo.path.exists():
            logger.info(
                f"Repository {repo.name} already exists, pulling latest changes"
            )
            subprocess.run(
                ["git", "pull", "origin", repo.branch],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )
        else:
            logger.info(f"Cloning {repo.name} from {repo.url}")
            subprocess.run(
                ["git", "clone", "-b", repo.branch, repo.url, str(repo.path)],
                check=True,
                capture_output=True,
            )

    def _setup_poetry_environment(self, repo: RepositoryConfig, ci_mode: bool) -> None:
        """Set up Poetry environment for a repository."""
        if not (repo.path / "pyproject.toml").exists():
            logger.warning(f"No pyproject.toml found in {repo.name}, skipping")
            return

        # Configure Poetry
        env = {"POETRY_VIRTUALENVS_IN_PROJECT": "true"}

        # Install dependencies
        subprocess.run(
            ["poetry", "install"],
            cwd=repo.path,
            env={**subprocess.os.environ, **env},
            check=True,
            capture_output=True,
        )

        logger.info(f"Set up Poetry environment for {repo.name}")

    def _install_git_hooks(self) -> None:
        """Install Git hooks in all repositories."""
        from .hooks import GitHooksManager

        hooks_manager = GitHooksManager(self.config_manager)
        hooks_manager.install_hooks()

    def get_status(self, check_permissions: bool = False) -> dict[str, Any]:
        """Get workspace status."""
        config = self.config_manager.load_config()

        # Get MPR version
        from .. import __version__

        status = {
            "workspace": {
                "name": config.name,
                "root": str(self.workspace_root),
                "python_version": config.python_version,
                "mpr_version": __version__,
            },
            "repositories": [],
        }

        for repo in config.repositories:
            repo_status = {
                "name": repo.name,
                "path": str(repo.path),
                "exists": repo.path.exists(),
                "has_pyproject": (repo.path / "pyproject.toml").exists(),
                "has_venv": (repo.path / ".venv").exists(),
                "git_status": None,
                "git_branch": None,
                "package_version": None,
                "dependency_mode": None,
            }

            if repo.path.exists():
                # Get git status
                try:
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=repo.path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    repo_status["git_status"] = (
                        "clean" if not result.stdout.strip() else "dirty"
                    )
                except subprocess.CalledProcessError:
                    repo_status["git_status"] = "error"

                # Get current git branch
                try:
                    result = subprocess.run(
                        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        cwd=repo.path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    repo_status["git_branch"] = result.stdout.strip()
                except subprocess.CalledProcessError:
                    repo_status["git_branch"] = "unknown"

                # Get package version
                repo_status["package_version"] = self._get_package_version(repo)

                # Check dependency mode
                repo_status["dependency_mode"] = self._check_dependency_mode(repo)

            if check_permissions:
                repo_status["writable"] = self._check_write_permissions(repo.path)

            status["repositories"].append(repo_status)

        # Check for dependency mode marker
        marker_file = self.workspace_root / ".dependency-mode"
        if marker_file.exists():
            status["workspace"]["dependency_mode"] = (
                marker_file.read_text().strip().split("\n")[0]
            )
        else:
            status["workspace"]["dependency_mode"] = "remote"

        return status

    def _check_dependency_mode(self, repo: RepositoryConfig) -> str:
        """Check repository dependency mode (local, remote, test, or mixed)."""
        pyproject_path = repo.path / "pyproject.toml"
        if not pyproject_path.exists():
            return "unknown"

        try:
            import toml

            pyproject_data = toml.load(pyproject_path)
            dependencies = (
                pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            )

            path_deps = []
            version_deps = []
            test_deps = []

            for dep_name, dep_spec in dependencies.items():
                # Skip python dependency
                if dep_name == "python":
                    continue

                if isinstance(dep_spec, dict):
                    if "path" in dep_spec:
                        path_deps.append(dep_name)
                    elif "source" in dep_spec and dep_spec["source"] == "test-pypi":
                        test_deps.append(dep_name)
                    elif "version" in dep_spec:
                        # Check if it's from test-pypi source
                        if dep_spec.get("source") == "test-pypi":
                            test_deps.append(dep_name)
                        else:
                            version_deps.append(dep_name)
                elif isinstance(dep_spec, str):
                    # Standard version dependency
                    version_deps.append(dep_name)

            # Determine mode based on dependency types
            if path_deps and not version_deps and not test_deps:
                return "local"
            elif test_deps and not version_deps and not path_deps:
                return "test"
            elif version_deps and not path_deps and not test_deps:
                return "remote"
            elif path_deps or version_deps or test_deps:
                return "mixed"
            else:
                return "none"

        except Exception as e:
            logger.warning(f"Error analyzing dependencies for {repo.name}: {e}")
            return "error"

    def _get_package_version(self, repo: RepositoryConfig) -> str:
        """Get the version declared in pyproject.toml."""
        pyproject_path = repo.path / "pyproject.toml"
        if not pyproject_path.exists():
            return "unknown"

        try:
            import toml

            pyproject_data = toml.load(pyproject_path)

            # Check tool.poetry.version first (Poetry format)
            if "tool" in pyproject_data and "poetry" in pyproject_data["tool"]:
                if "version" in pyproject_data["tool"]["poetry"]:
                    return pyproject_data["tool"]["poetry"]["version"]

            # Check project.version (PEP 621 format)
            if "project" in pyproject_data and "version" in pyproject_data["project"]:
                return pyproject_data["project"]["version"]

            # Check if version is defined dynamically
            if "project" in pyproject_data and "dynamic" in pyproject_data["project"]:
                if "version" in pyproject_data["project"]["dynamic"]:
                    return "dynamic"

            return "not found"

        except Exception as e:
            logger.warning(f"Error parsing pyproject.toml for {repo.name}: {e}")
            return "error"

    def _check_write_permissions(self, path: Path) -> bool:
        """Check if path is writable."""
        if not path.exists():
            return False

        try:
            test_file = path / ".mpr_write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except (PermissionError, OSError):
            return False

    def display_status(self, status: dict[str, Any]) -> None:
        """Display workspace status in a formatted table."""

        # Workspace info
        console.print(f"\n[bold]Workspace: {status['workspace']['name']}[/bold]")
        console.print(f"Root: {status['workspace']['root']}")
        console.print(f"Python: {status['workspace']['python_version']}")
        console.print(f"MPR Version: {status['workspace']['mpr_version']}")
        console.print(f"Dependency Mode: {status['workspace']['dependency_mode']}")

        # Repositories table
        table = Table(title="Repositories")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Version", style="bright_magenta")
        table.add_column("Branch", style="bright_yellow")
        table.add_column("Git", style="yellow")
        table.add_column("Dependencies", style="magenta")
        table.add_column("Virtual Env", style="blue")

        for repo in status["repositories"]:
            status_icon = "✓" if repo["exists"] else "✗"
            package_version = repo.get("package_version", "unknown")
            git_branch = repo.get("git_branch", "unknown")
            git_status = repo.get("git_status", "unknown")
            dep_mode = repo.get("dependency_mode", "unknown")
            venv_status = "✓" if repo.get("has_venv", False) else "✗"

            table.add_row(
                repo["name"],
                status_icon,
                package_version,
                git_branch,
                git_status,
                dep_mode,
                venv_status,
            )

        console.print(table)

    def clean_workspace(self, force: bool = False) -> None:
        """Clean up workspace artifacts."""
        if not force:
            console.print("This will remove:")
            console.print("- Log files")
            console.print("- Backup files")
            console.print("- Virtual environments")
            console.print("- Build artifacts")

            if not console.input("Continue? [y/N] ").lower().startswith("y"):
                return

        # Clean directories
        for directory in ["logs", "backups"]:
            dir_path = self.workspace_root / directory
            if dir_path.exists():
                shutil.rmtree(dir_path)
                dir_path.mkdir()

        # Clean each repository
        config = self.config_manager.load_config()
        for repo in config.repositories:
            if repo.path.exists():
                # Remove virtual environment
                venv_path = repo.path / ".venv"
                if venv_path.exists():
                    shutil.rmtree(venv_path)

                # Remove build artifacts
                for pattern in ["dist", "build", "*.egg-info", "__pycache__"]:
                    for path in repo.path.rglob(pattern):
                        if path.is_dir():
                            shutil.rmtree(path)
                        else:
                            path.unlink()

        # Remove dependency mode marker
        marker_file = self.workspace_root / ".dependency-mode"
        if marker_file.exists():
            marker_file.unlink()

        logger.info("Workspace cleaned successfully")
