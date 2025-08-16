"""Dependency management functionality."""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import toml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..utils.config import ConfigManager, RepositoryConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class DependencyManager:
    """Manages dependency switching and version synchronization."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.workspace_root = config_manager.workspace_root

    def switch_to_local(self, dry_run: bool = False) -> bool:
        """Switch all repositories to use local path dependencies."""
        # Create backup
        if not dry_run:
            self._create_backup()

        # Process repositories in dependency order
        dependency_order = self.config_manager.get_dependency_order()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            task = progress.add_task(
                "Switching to local dependencies...", total=len(dependency_order)
            )

            for repo_name in dependency_order:
                repo = self.config_manager.get_repository(repo_name)
                if repo:
                    progress.update(task, description=f"Processing {repo_name}...")

                    if not dry_run:
                        self._switch_repo_to_local(repo)
                    else:
                        console.print(
                            f"[dim]Would switch {repo_name} to local dependencies[/dim]"
                        )

                    progress.advance(task)

        # Create marker file
        if not dry_run:
            self._create_dependency_marker("local")

        return True

    def switch_to_remote(self, dry_run: bool = False) -> bool:
        """Switch all repositories to use remote version dependencies."""
        # Process repositories in dependency order
        dependency_order = self.config_manager.get_dependency_order()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            task = progress.add_task(
                "Switching to remote dependencies...", total=len(dependency_order)
            )

            for repo_name in dependency_order:
                repo = self.config_manager.get_repository(repo_name)
                if repo:
                    progress.update(task, description=f"Processing {repo_name}...")

                    if not dry_run:
                        self._switch_repo_to_remote(repo)
                    else:
                        console.print(
                            f"[dim]Would switch {repo_name} to remote dependencies[/dim]"
                        )

                    progress.advance(task)

        # Remove marker file
        if not dry_run:
            self._remove_dependency_marker()

        return True

    def switch_to_test(self, dry_run: bool = False) -> bool:
        """Switch all repositories to use test-pypi dependencies."""
        # Process repositories in dependency order
        dependency_order = self.config_manager.get_dependency_order()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            task = progress.add_task(
                "Switching to test dependencies...", total=len(dependency_order)
            )

            for repo_name in dependency_order:
                repo = self.config_manager.get_repository(repo_name)
                if repo:
                    progress.update(task, description=f"Processing {repo_name}...")

                    if not dry_run:
                        self._switch_repo_to_test(repo)
                    else:
                        console.print(
                            f"[dim]Would switch {repo_name} to test dependencies[/dim]"
                        )

                    progress.advance(task)

        # Create marker file
        if not dry_run:
            self._create_dependency_marker("test")

        return True

    def _switch_repo_to_local(self, repo: RepositoryConfig) -> None:
        """Switch a single repository to local dependencies."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            logger.warning(f"No pyproject.toml found in {repo.name}")
            return

        # Get dependencies for this repository

        for dep_name in repo.dependencies:
            dep_repo = self.config_manager.get_repository(dep_name)
            if not dep_repo:
                logger.warning(f"Dependency {dep_name} not found in configuration")
                continue

            if not dep_repo.path.exists():
                logger.warning(
                    f"Dependency {dep_name} path does not exist: {dep_repo.path}"
                )
                continue

            # Remove existing dependency
            self._remove_poetry_dependency(repo, dep_repo.package_name)

            # Add as editable local dependency
            relative_path = self._get_relative_path(repo.path, dep_repo.path)
            self._add_poetry_local_dependency(
                repo, dep_repo.package_name, relative_path
            )

        logger.info(f"Switched {repo.name} to local dependencies")

    def _switch_repo_to_remote(self, repo: RepositoryConfig) -> None:
        """Switch a single repository to remote dependencies."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            logger.warning(f"No pyproject.toml found in {repo.name}")
            return

        # Get current versions of dependencies
        for dep_name in repo.dependencies:
            dep_repo = self.config_manager.get_repository(dep_name)
            if not dep_repo:
                continue

            # Get current version from dependency's pyproject.toml
            current_version = self._get_current_version(dep_repo)
            if not current_version:
                logger.warning(f"Could not determine version for {dep_name}")
                continue

            # Remove existing dependency
            self._remove_poetry_dependency(repo, dep_repo.package_name)

            # Add version-based dependency
            source = dep_repo.source if hasattr(dep_repo, "source") else "pypi"
            self._add_poetry_remote_dependency(
                repo, dep_repo.package_name, current_version, source
            )

        # Update lock file
        self._update_lock_file(repo)

        logger.info(f"Switched {repo.name} to remote dependencies")

    def _switch_repo_to_test(self, repo: RepositoryConfig) -> None:
        """Switch a single repository to test-pypi dependencies."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            logger.warning(f"No pyproject.toml found in {repo.name}")
            return

        # Get current versions of dependencies
        for dep_name in repo.dependencies:
            dep_repo = self.config_manager.get_repository(dep_name)
            if not dep_repo:
                continue

            # Get current version from dependency's pyproject.toml
            current_version = self._get_current_version(dep_repo)
            if not current_version:
                logger.warning(f"Could not determine version for {dep_name}")
                continue

            # Remove existing dependency
            self._remove_poetry_dependency(repo, dep_repo.package_name)

            # Add test-pypi dependency
            self._add_poetry_test_dependency(
                repo, dep_repo.package_name, current_version
            )

        # Update lock file
        self._update_lock_file(repo)

        logger.info(f"Switched {repo.name} to test dependencies")

    def _remove_poetry_dependency(
        self, repo: RepositoryConfig, package_name: str
    ) -> None:
        """Remove a dependency using Poetry."""
        try:
            subprocess.run(
                ["poetry", "remove", package_name],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # Dependency might not exist, which is fine
            pass

    def _add_poetry_local_dependency(
        self, repo: RepositoryConfig, package_name: str, path: str
    ) -> None:
        """Add a local editable dependency using Poetry."""
        try:
            # First remove any existing dependency to avoid conflicts
            subprocess.run(
                ["poetry", "remove", package_name],
                cwd=repo.path,
                capture_output=True,
                check=False,  # Don't fail if package doesn't exist
            )

            # Add as editable dependency
            subprocess.run(
                ["poetry", "add", "--editable", path],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # If normal add fails, try adding without dependency resolution
            logger.warning(
                f"Normal poetry add failed for {package_name}, trying direct pyproject.toml edit"
            )
            self._add_local_dependency_direct(repo, package_name, path)

    def _add_local_dependency_direct(
        self, repo: RepositoryConfig, package_name: str, path: str
    ) -> None:
        """Add local dependency by directly editing pyproject.toml."""
        pyproject_path = repo.path / "pyproject.toml"

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            # Initialize dependencies if not exists
            if "tool" not in pyproject_data:
                pyproject_data["tool"] = {}
            if "poetry" not in pyproject_data["tool"]:
                pyproject_data["tool"]["poetry"] = {}
            if "dependencies" not in pyproject_data["tool"]["poetry"]:
                pyproject_data["tool"]["poetry"]["dependencies"] = {}

            # Add/update the dependency
            pyproject_data["tool"]["poetry"]["dependencies"][package_name] = {
                "path": path,
                "develop": True,
            }

            # Write back
            with open(pyproject_path, "w") as f:
                toml.dump(pyproject_data, f)

            logger.info(
                f"Directly added local dependency {package_name} to {repo.name}"
            )

        except Exception as e:
            logger.error(f"Failed to directly edit pyproject.toml for {repo.name}: {e}")
            raise

    def _add_poetry_remote_dependency(
        self,
        repo: RepositoryConfig,
        package_name: str,
        version: str,
        source: str = "pypi",
    ) -> None:
        """Add a remote version dependency using Poetry."""
        version_spec = f"^{version}"

        if source == "test-pypi":
            # Add with specific source
            subprocess.run(
                [
                    "poetry",
                    "add",
                    f"{package_name}@{version_spec}",
                    "--source",
                    "test-pypi",
                ],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )
        else:
            subprocess.run(
                ["poetry", "add", f"{package_name}@{version_spec}"],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )

    def _add_poetry_test_dependency(
        self, repo: RepositoryConfig, package_name: str, version: str
    ) -> None:
        """Add a test-pypi dependency using Poetry."""
        try:
            # First ensure test-pypi source is configured
            self._ensure_test_pypi_source(repo)

            # Add dependency from test-pypi
            version = f"^{version}"
            subprocess.run(
                [
                    "poetry",
                    "source",
                    "add",
                    "test-pypi",
                    "https://test.pypi.org/simple/",
                    "--priority",
                    "explicit",
                ],
                cwd=repo.path,
                capture_output=True,
                check=False,  # Don't fail if source already exists
            )

            # Add package from test-pypi source
            result = subprocess.run(
                [
                    "poetry",
                    "add",
                    f"{package_name}=={version}",
                    "--source",
                    "test-pypi",
                ],
                cwd=repo.path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # Fallback: try with direct pyproject.toml edit
                logger.warning(
                    f"Poetry add from test-pypi failed for {package_name}, trying direct edit"
                )
                self._add_test_dependency_direct(repo, package_name, version)

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Failed to add test dependency {package_name}, trying direct edit: {e}"
            )
            self._add_test_dependency_direct(repo, package_name, version)

    def _ensure_test_pypi_source(self, repo: RepositoryConfig) -> None:
        """Ensure test-pypi source is configured in pyproject.toml."""
        pyproject_path = repo.path / "pyproject.toml"

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            # Initialize tool.poetry.source if not exists
            if "tool" not in pyproject_data:
                pyproject_data["tool"] = {}
            if "poetry" not in pyproject_data["tool"]:
                pyproject_data["tool"]["poetry"] = {}
            if "source" not in pyproject_data["tool"]["poetry"]:
                pyproject_data["tool"]["poetry"]["source"] = []

            # Check if test-pypi source already exists
            sources = pyproject_data["tool"]["poetry"]["source"]
            test_pypi_exists = any(
                source.get("name") == "test-pypi" for source in sources
            )

            if not test_pypi_exists:
                # Add test-pypi source
                sources.append(
                    {
                        "name": "test-pypi",
                        "url": "https://test.pypi.org/simple/",
                        "priority": "explicit",
                    }
                )

                # Write back
                with open(pyproject_path, "w") as f:
                    toml.dump(pyproject_data, f)

                logger.info(f"Added test-pypi source to {repo.name}")

        except Exception as e:
            logger.warning(f"Failed to configure test-pypi source for {repo.name}: {e}")

    def _add_test_dependency_direct(
        self, repo: RepositoryConfig, package_name: str, version: str
    ) -> None:
        """Add test dependency by directly editing pyproject.toml."""
        pyproject_path = repo.path / "pyproject.toml"

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            # Initialize dependencies if not exists
            if "tool" not in pyproject_data:
                pyproject_data["tool"] = {}
            if "poetry" not in pyproject_data["tool"]:
                pyproject_data["tool"]["poetry"] = {}
            if "dependencies" not in pyproject_data["tool"]["poetry"]:
                pyproject_data["tool"]["poetry"]["dependencies"] = {}

            # Add/update the dependency with test-pypi source
            pyproject_data["tool"]["poetry"]["dependencies"][package_name] = {
                "version": f"^{version}",
                "source": "test-pypi",
            }

            # Write back
            with open(pyproject_path, "w") as f:
                toml.dump(pyproject_data, f)

            logger.info(f"Directly added test dependency {package_name} to {repo.name}")

        except Exception as e:
            logger.error(f"Failed to directly edit pyproject.toml for {repo.name}: {e}")
            raise

    def _get_current_version(self, repo: RepositoryConfig) -> str | None:
        """Get current version from repository's pyproject.toml."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            return None

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            return pyproject_data.get("tool", {}).get("poetry", {}).get("version")
        except (toml.TomlDecodeError, KeyError):
            return None

    def _get_relative_path(self, from_path: Path, to_path: Path) -> str:
        """Get relative path from one repository to another."""
        # For repositories in the same workspace, they should be at the same level
        # e.g., repos/doogat-core -> repos/buvis-pybase should be "../buvis-pybase"

        try:
            # Simple case: both repositories are siblings in repos/ directory
            to_name = to_path.name

            # Check if both are in repos/ directory
            if (
                from_path.parent.name == "repos"
                and to_path.parent.name == "repos"
                and from_path.parent == to_path.parent
            ):
                return f"../{to_name}"

            # Fallback: calculate proper relative path
            from_resolved = from_path.resolve()
            to_resolved = to_path.resolve()

            relative_path = to_resolved.relative_to(from_resolved.parent)
            return str(relative_path)

        except ValueError:
            # Last resort: use absolute path
            logger.warning(
                f"Could not calculate relative path from {from_path} to {to_path}, using absolute path"
            )
            return str(to_path.resolve())

    def _update_lock_file(self, repo: RepositoryConfig) -> None:
        """Update Poetry lock file."""
        try:
            # Try with --no-update first (older Poetry versions)
            subprocess.run(
                ["poetry", "lock", "--no-update"],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # Fallback for newer Poetry versions
            subprocess.run(
                ["poetry", "lock"], cwd=repo.path, check=True, capture_output=True
            )

    def _create_backup(self) -> None:
        """Create backup of all pyproject.toml files."""
        config = self.config_manager.load_config()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.config_manager.get_backups_path() / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)

        for repo in config.repositories:
            pyproject_path = repo.path / "pyproject.toml"
            if pyproject_path.exists():
                backup_path = backup_dir / f"{repo.name}_pyproject.toml"
                shutil.copy2(pyproject_path, backup_path)

        logger.info(f"Created backup in {backup_dir}")

    def _create_dependency_marker(self, mode: str) -> None:
        """Create marker file indicating dependency mode."""
        marker_file = self.workspace_root / ".dependency-mode"
        content = f"{mode}\n{datetime.now().isoformat()}\n"
        marker_file.write_text(content)

    def _remove_dependency_marker(self) -> None:
        """Remove dependency mode marker file."""
        marker_file = self.workspace_root / ".dependency-mode"
        if marker_file.exists():
            marker_file.unlink()

    def get_status(self) -> dict[str, Any]:
        """Get dependency status for all repositories."""
        config = self.config_manager.load_config()
        status = {"workspace_mode": self._get_workspace_mode(), "repositories": []}

        for repo in config.repositories:
            repo_status = {
                "name": repo.name,
                "version": None,
                "path_dependencies": [],
                "version_dependencies": [],
                "test_dependencies": [],
                "dependency_details": {},
                "compatibility_issues": [],
                "mode": "unknown",
            }

            if repo.path.exists():
                # Get repository version
                repo_status["version"] = self._get_current_version(repo)

                # Analyze dependencies with detailed information
                detailed_analysis = self._analyze_repo_dependencies_detailed(repo)
                repo_status.update(detailed_analysis)
            else:
                # Repository path doesn't exist
                repo_status["mode"] = "missing"

            status["repositories"].append(repo_status)

        return status

    def _get_workspace_mode(self) -> str:
        """Get current workspace dependency mode."""
        marker_file = self.workspace_root / ".dependency-mode"
        if marker_file.exists():
            return marker_file.read_text().strip().split("\n")[0]
        return "remote"

    def _analyze_repo_dependencies_detailed(
        self, repo: RepositoryConfig
    ) -> dict[str, Any]:
        """Analyze dependencies for a single repository with detailed information."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            return {"mode": "no_pyproject"}

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)
        except toml.TomlDecodeError:
            return {"mode": "invalid_toml"}

        dependencies = (
            pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        )

        path_deps = []
        version_deps = []
        test_deps = []
        dependency_details = {}
        compatibility_issues = []

        for dep_name, dep_spec in dependencies.items():
            if dep_name == "python":
                continue

            dep_info = {
                "name": dep_name,
                "type": "unknown",
                "version": None,
                "source": None,
                "path": None,
                "actual_version": None,
                "compatible": None,
            }

            if isinstance(dep_spec, dict):
                if "path" in dep_spec:
                    path_deps.append(dep_name)
                    dep_info["type"] = "path"
                    dep_info["path"] = dep_spec["path"]
                    dep_info["source"] = "local"

                    # Try to get version from path target
                    dep_repo = self.config_manager.get_repository(dep_name)
                    if dep_repo and dep_repo.path.exists():
                        dep_info["actual_version"] = self._get_current_version(dep_repo)

                elif "source" in dep_spec and dep_spec["source"] == "test-pypi":
                    test_deps.append(dep_name)
                    dep_info["type"] = "test"
                    dep_info["version"] = dep_spec.get("version")
                    dep_info["source"] = "test-pypi"

                elif "version" in dep_spec:
                    version_deps.append(dep_name)
                    dep_info["type"] = "version"
                    dep_info["version"] = dep_spec["version"]
                    dep_info["source"] = dep_spec.get("source", "pypi")

            elif isinstance(dep_spec, str):
                version_deps.append(dep_name)
                dep_info["type"] = "version"
                dep_info["version"] = dep_spec
                dep_info["source"] = "pypi"

            # Check compatibility for version-based dependencies
            if dep_info["version"]:
                dep_repo = self.config_manager.get_repository(dep_name)
                if dep_repo and dep_repo.path.exists():
                    actual_version = self._get_current_version(dep_repo)
                    dep_info["actual_version"] = actual_version

                    if actual_version:
                        is_compatible = self._is_version_compatible(
                            dep_info["version"], actual_version
                        )
                        dep_info["compatible"] = is_compatible

                        if not is_compatible:
                            compatibility_issues.append(
                                {
                                    "dependency": dep_name,
                                    "required": dep_info["version"],
                                    "actual": actual_version,
                                }
                            )

            dependency_details[dep_name] = dep_info

        # Determine mode
        if path_deps and not version_deps and not test_deps:
            mode = "local"
        elif test_deps and not version_deps and not path_deps:
            mode = "test"
        elif version_deps and not path_deps and not test_deps:
            mode = "remote"
        elif path_deps or version_deps or test_deps:
            mode = "mixed"
        else:
            mode = "none"

        return {
            "path_dependencies": path_deps,
            "version_dependencies": version_deps,
            "test_dependencies": test_deps,
            "dependency_details": dependency_details,
            "compatibility_issues": compatibility_issues,
            "mode": mode,
        }

    def _analyze_repo_dependencies(self, repo: RepositoryConfig) -> dict[str, Any]:
        """Analyze dependencies for a single repository."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            return {"mode": "no_pyproject"}

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)
        except toml.TomlDecodeError:
            return {"mode": "invalid_toml"}

        dependencies = (
            pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        )

        path_deps = []
        version_deps = []
        test_deps = []

        for dep_name, dep_spec in dependencies.items():
            if dep_name == "python":
                continue

            if isinstance(dep_spec, dict):
                if "path" in dep_spec:
                    path_deps.append(dep_name)
                elif "source" in dep_spec and dep_spec["source"] == "test-pypi":
                    test_deps.append(dep_name)
                elif "version" in dep_spec:
                    version_deps.append(dep_name)
            elif isinstance(dep_spec, str):
                version_deps.append(dep_name)

        # Determine mode
        if path_deps and not version_deps and not test_deps:
            mode = "local"
        elif test_deps and not version_deps and not path_deps:
            mode = "test"
        elif version_deps and not path_deps and not test_deps:
            mode = "remote"
        elif path_deps or version_deps or test_deps:
            mode = "mixed"
        else:
            mode = "none"

        return {
            "path_dependencies": path_deps,
            "version_dependencies": version_deps,
            "test_dependencies": test_deps,
            "mode": mode,
        }

    def display_status(
        self,
        status: dict[str, Any],
        verbose: bool = False,
        show_transitive: bool = False,
    ) -> None:
        """Display dependency status in a formatted table."""
        console.print(
            f"\n[bold]Workspace Dependency Mode: {status['workspace_mode']}[/bold]"
        )

        # Main repository overview table
        table = Table(title="Repository Overview")
        table.add_column("Repository", style="cyan")
        table.add_column("Version", style="bright_blue")
        table.add_column("Mode", style="green")
        table.add_column("Dependencies", style="yellow")
        table.add_column("Compatibility", style="magenta")

        for repo in status["repositories"]:
            mode_color = {
                "local": "green",
                "remote": "blue",
                "test": "bright_yellow",
                "mixed": "yellow",
                "none": "dim",
                "unknown": "red",
                "missing": "red",
            }.get(repo["mode"], "white")

            # Repository version
            repo_version = repo.get("version", "N/A")
            version_display = (
                f"[bright_blue]{repo_version}[/bright_blue]"
                if repo_version != "N/A"
                else "[dim]N/A[/dim]"
            )

            # Dependencies summary
            all_deps = (
                repo.get("path_dependencies", [])
                + repo.get("version_dependencies", [])
                + repo.get("test_dependencies", [])
            )
            deps_summary = f"{len(all_deps)} deps" if all_deps else "No deps"

            # Compatibility status
            compatibility_issues = repo.get("compatibility_issues", [])
            if compatibility_issues:
                compat_display = f"[red]{len(compatibility_issues)} issues[/red]"
            elif all_deps:
                compat_display = "[green]✓[/green]"
            else:
                compat_display = "[dim]-[/dim]"

            table.add_row(
                repo["name"],
                version_display,
                f"[{mode_color}]{repo['mode']}[/{mode_color}]",
                deps_summary,
                compat_display,
            )

        console.print(table)

        # Show detailed dependency information if verbose or if there are any dependencies
        show_details = verbose or any(
            repo.get("dependency_details") for repo in status["repositories"]
        )

        if show_details:
            for repo in status["repositories"]:
                dependency_details = repo.get("dependency_details", {})
                compatibility_issues = repo.get("compatibility_issues", [])

                if dependency_details or compatibility_issues:
                    console.print(
                        f"\n[bold cyan]{repo['name']}[/bold cyan] [dim](v{repo.get('version', 'N/A')})[/dim]"
                    )

                    if dependency_details:
                        dep_table = Table(show_header=True, header_style="bold")
                        dep_table.add_column("Dependency", style="cyan")
                        dep_table.add_column("Type", style="yellow")
                        dep_table.add_column("Required", style="magenta")
                        dep_table.add_column("Actual", style="bright_blue")
                        dep_table.add_column("Source", style="green")
                        dep_table.add_column("Status", style="white")

                        for dep_name, dep_info in dependency_details.items():
                            dep_type = dep_info.get("type", "unknown")
                            required_version = dep_info.get(
                                "version", dep_info.get("path", "-")
                            )
                            actual_version = dep_info.get("actual_version", "N/A")
                            source = dep_info.get("source", "unknown")

                            # Status determination
                            if dep_info.get("compatible") is True:
                                status_display = "[green]✓ Compatible[/green]"
                            elif dep_info.get("compatible") is False:
                                status_display = "[red]✗ Incompatible[/red]"
                            elif dep_type == "path":
                                status_display = "[yellow]Local dev[/yellow]"
                            else:
                                status_display = "[dim]Unknown[/dim]"

                            # Format required version display
                            if dep_type == "path":
                                required_display = (
                                    f"[yellow]{required_version}[/yellow]"
                                )
                            else:
                                required_display = required_version or "-"

                            # Format actual version display
                            if actual_version != "N/A":
                                actual_display = (
                                    f"[bright_blue]{actual_version}[/bright_blue]"
                                )
                            else:
                                actual_display = "[dim]N/A[/dim]"

                            dep_table.add_row(
                                dep_name,
                                dep_type,
                                required_display,
                                actual_display,
                                source,
                                status_display,
                            )

                        console.print(dep_table)

                    # Show compatibility issues if any
                    if compatibility_issues:
                        console.print("\n[red bold]Compatibility Issues:[/red bold]")
                        for issue in compatibility_issues:
                            console.print(
                                f"  [red]•[/red] {issue['dependency']}: requires {issue['required']}, but actual is {issue['actual']}"
                            )

        # Show transitive dependency analysis if requested
        if show_transitive and "transitive_analysis" in status:
            self._display_transitive_analysis(status["transitive_analysis"])

        # Summary of issues
        total_issues = sum(
            len(repo.get("compatibility_issues", [])) for repo in status["repositories"]
        )
        if total_issues > 0:
            console.print(
                f"\n[red bold]⚠ Total compatibility issues: {total_issues}[/red bold]"
            )
            console.print(
                "[yellow]Run 'mpr deps update' to resolve version conflicts[/yellow]"
            )
        else:
            console.print(
                "\n[green bold]✓ All dependencies are compatible[/green bold]"
            )

    def analyze_transitive_dependencies(self) -> dict[str, Any]:
        """Analyze transitive dependencies across all repositories."""
        config = self.config_manager.load_config()

        # Build all packages info
        all_packages = {}

        for repo in config.repositories:
            if not repo.path.exists():
                continue

            # Get current version
            current_version = self._get_current_version(repo)
            all_packages[repo.package_name] = {
                "repo_name": repo.name,
                "version": current_version,
                "direct_dependencies": [],
            }

            # Get dependencies
            pyproject_path = repo.path / "pyproject.toml"
            if pyproject_path.exists():
                try:
                    with open(pyproject_path) as f:
                        pyproject_data = toml.load(f)

                    dependencies = (
                        pyproject_data.get("tool", {})
                        .get("poetry", {})
                        .get("dependencies", {})
                    )

                    for dep_name, dep_spec in dependencies.items():
                        if dep_name == "python":
                            continue

                        # Check if this is one of our managed dependencies
                        dep_repo = self.config_manager.get_repository(dep_name)
                        if dep_repo:
                            all_packages[repo.package_name][
                                "direct_dependencies"
                            ].append(
                                {
                                    "name": dep_name,
                                    "package_name": dep_repo.package_name,
                                    "spec": dep_spec,
                                }
                            )
                except toml.TomlDecodeError:
                    continue

        # Find transitive dependency issues
        transitive_issues = []
        dependency_chains = {}

        # Build dependency chains
        for package_name, package_info in all_packages.items():
            chains = self._build_dependency_chains(package_name, all_packages, set())
            dependency_chains[package_name] = chains

        # Check for version conflicts in chains
        for package_name, chains in dependency_chains.items():
            for chain in chains:
                if len(chain) > 2:  # Only check transitive dependencies (length > 2)
                    for i in range(len(chain) - 1):
                        current_pkg = chain[i]
                        next_pkg = chain[i + 1]

                        # Check if version requirements are satisfied
                        current_info = all_packages.get(current_pkg)
                        if current_info:
                            for dep in current_info["direct_dependencies"]:
                                if dep["package_name"] == next_pkg:
                                    next_info = all_packages.get(next_pkg)
                                    if next_info and next_info["version"]:
                                        # Check compatibility
                                        if (
                                            isinstance(dep["spec"], dict)
                                            and "version" in dep["spec"]
                                        ):
                                            required_version = dep["spec"]["version"]
                                        elif isinstance(dep["spec"], str):
                                            required_version = dep["spec"]
                                        else:
                                            continue

                                        if not self._is_version_compatible(
                                            required_version, next_info["version"]
                                        ):
                                            transitive_issues.append(
                                                {
                                                    "chain": " → ".join(chain),
                                                    "dependency": next_pkg,
                                                    "required_by": current_pkg,
                                                    "required_version": required_version,
                                                    "actual_version": next_info[
                                                        "version"
                                                    ],
                                                }
                                            )

        return {
            "dependency_graph": all_packages,
            "dependency_chains": dependency_chains,
            "transitive_issues": transitive_issues,
        }

    def _build_dependency_chains(
        self, package_name: str, all_packages: dict[str, Any], visited: set
    ) -> list[list[str]]:
        """Build dependency chains starting from a package."""
        if package_name in visited:
            return []  # Circular dependency detected

        visited.add(package_name)
        chains = []

        package_info = all_packages.get(package_name)
        if not package_info:
            return [[package_name]]

        # If no dependencies, this is a leaf node
        if not package_info["direct_dependencies"]:
            return [[package_name]]

        # Build chains for each dependency
        for dep in package_info["direct_dependencies"]:
            dep_package_name = dep["package_name"]
            sub_chains = self._build_dependency_chains(
                dep_package_name, all_packages, visited.copy()
            )

            for sub_chain in sub_chains:
                chains.append([package_name] + sub_chain)

        return chains

    def _display_transitive_analysis(self, analysis: dict[str, Any]) -> None:
        """Display transitive dependency analysis."""
        console.print("\n[bold]Transitive Dependency Analysis[/bold]")

        # Show dependency chains
        dependency_chains = analysis.get("dependency_chains", {})
        if dependency_chains:
            console.print("\n[bold yellow]Dependency Chains:[/bold yellow]")
            for package_name, chains in dependency_chains.items():
                if chains:
                    console.print(f"\n[cyan]{package_name}[/cyan]:")
                    for chain in chains:
                        if len(chain) > 1:
                            chain_display = " → ".join(chain)
                            console.print(f"  {chain_display}")

        # Show transitive issues
        transitive_issues = analysis.get("transitive_issues", [])
        if transitive_issues:
            console.print("\n[red bold]Transitive Dependency Issues:[/red bold]")
            for issue in transitive_issues:
                console.print(f"  [red]•[/red] {issue['chain']}")
                console.print(
                    f"    {issue['dependency']}: required {issue['required_version']} by {issue['required_by']}, but actual is {issue['actual_version']}"
                )
        else:
            console.print("\n[green]✓ No transitive dependency issues found[/green]")

    def update_versions(self, target_version: str | None = None) -> None:
        """Update dependency versions across all repositories."""
        config = self.config_manager.load_config()

        if target_version:
            # Set all repositories to the same version
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:

                task = progress.add_task(
                    "Updating versions...", total=len(config.repositories)
                )

                for repo in config.repositories:
                    if repo.path.exists():
                        progress.update(task, description=f"Updating {repo.name}...")
                        self._set_repo_version(repo, target_version)
                        progress.advance(task)
        else:
            # Auto-detect versions and update configuration
            console.print("Auto-detecting current versions...")

            for repo in config.repositories:
                if repo.path.exists():
                    version = self._get_current_version(repo)
                    if version:
                        console.print(f"  {repo.name}: {version}")
                    else:
                        console.print(
                            f"  {repo.name}: [red]Could not detect version[/red]"
                        )

    def _set_repo_version(self, repo: RepositoryConfig, version: str) -> None:
        """Set version for a repository using Poetry."""
        try:
            subprocess.run(
                ["poetry", "version", version],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )
            logger.info(f"Set {repo.name} version to {version}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set version for {repo.name}: {e}")

    def check_compatibility(self) -> bool:
        """Check if all dependencies are compatible."""
        config = self.config_manager.load_config()
        compatible = True

        console.print("\n[bold]Checking dependency compatibility...[/bold]")

        for repo in config.repositories:
            if not repo.path.exists():
                continue

            console.print(f"\nChecking {repo.name}:")

            for dep_name in repo.dependencies:
                dep_repo = self.config_manager.get_repository(dep_name)
                if not dep_repo:
                    console.print(
                        f"  [red]✗ {dep_name}: Not found in configuration[/red]"
                    )
                    compatible = False
                    continue

                # Get required version
                required_version = self._get_required_version(
                    repo, dep_repo.package_name
                )
                if not required_version:
                    console.print(
                        f"  [yellow]? {dep_name}: Version requirement not found[/yellow]"
                    )
                    continue

                # Get actual version
                actual_version = self._get_current_version(dep_repo)
                if not actual_version:
                    console.print(
                        f"  [red]✗ {dep_name}: Cannot determine actual version[/red]"
                    )
                    compatible = False
                    continue

                # Check compatibility
                if self._is_version_compatible(required_version, actual_version):
                    console.print(
                        f"  [green]✓ {dep_name}: {required_version} (actual: {actual_version})[/green]"
                    )
                else:
                    console.print(
                        f"  [red]✗ {dep_name}: Required {required_version}, actual {actual_version}[/red]"
                    )
                    compatible = False

        return compatible

    def _get_required_version(
        self, repo: RepositoryConfig, package_name: str
    ) -> str | None:
        """Get required version for a dependency."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            return None

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            dependencies = (
                pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            )
            dep_spec = dependencies.get(package_name)

            if isinstance(dep_spec, str):
                return dep_spec
            elif isinstance(dep_spec, dict):
                return dep_spec.get("version")

            return None
        except (toml.TomlDecodeError, KeyError):
            return None

    def _is_version_compatible(self, requirement: str, version: str) -> bool:
        """Check if a version satisfies a requirement."""
        # Simple compatibility check - can be enhanced with proper version parsing
        if requirement.startswith("^"):
            # Caret requirement
            req_version = requirement[1:]
            req_parts = req_version.split(".")
            ver_parts = version.split(".")

            if len(req_parts) > 0 and len(ver_parts) > 0:
                return req_parts[0] == ver_parts[0]

        elif requirement.startswith("~"):
            # Tilde requirement
            req_version = requirement[1:]
            req_parts = req_version.split(".")
            ver_parts = version.split(".")

            if len(req_parts) >= 2 and len(ver_parts) >= 2:
                return req_parts[0] == ver_parts[0] and req_parts[1] == ver_parts[1]

        elif requirement == version:
            # Exact match
            return True

        # Default to compatible for now
        return True
