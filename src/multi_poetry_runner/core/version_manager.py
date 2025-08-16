"""Advanced version management functionality for coordinated releases."""

import json
import re
import subprocess
from datetime import datetime
from typing import Any

import toml
from rich.console import Console
from rich.table import Table

from ..utils.config import ConfigManager, RepositoryConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class VersionManager:
    """Manages semantic versioning and coordinated version bumps across repositories."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.workspace_root = config_manager.workspace_root
        self.version_history_file = self.workspace_root / ".version-history.json"

    def bump_version(
        self,
        repository: str,
        bump_type: str,
        alpha: bool = False,
        dry_run: bool = False,
        update_dependents: bool = True,
        dependents_bump: str = "patch",
        validate: bool = True,
    ) -> bool:
        """Bump version for a repository and optionally update all dependents.

        Args:
            repository: Repository name to bump
            bump_type: Type of bump ('patch', 'minor', 'major')
            alpha: Whether to create alpha version
            dry_run: Show what would be changed without making changes
            update_dependents: Whether to update dependent repositories
            dependents_bump: Type of bump for dependent repositories ('patch', 'minor', 'major')
            validate: Whether to run validation tests
        """

        console.print(
            f"\n[bold]Version Bump: {repository} ({bump_type}{' alpha' if alpha else ''})[/bold]"
        )

        # Get repository config
        repo = self.config_manager.get_repository(repository)
        if not repo:
            console.print(
                f"[red]Repository '{repository}' not found in configuration[/red]"
            )
            return False

        if not repo.path.exists():
            console.print(f"[red]Repository path does not exist: {repo.path}[/red]")
            return False

        try:
            # Step 1: Get current version and calculate new version
            current_version = self._get_current_version(repo)
            if not current_version:
                console.print(
                    f"[red]Could not determine current version for {repository}[/red]"
                )
                return False

            new_version = self._calculate_new_version(current_version, bump_type, alpha)
            console.print(
                f"Version bump: [yellow]{current_version}[/yellow] → [green]{new_version}[/green]"
            )

            if dry_run:
                console.print("[dim]DRY RUN MODE - No changes will be made[/dim]")

            # Step 2: Update repository version
            if not dry_run:
                self._update_repository_version(repo, new_version)
                console.print(
                    f"[green]✓[/green] Updated {repository} to version {new_version}"
                )
            else:
                console.print(
                    f"[dim]Would update {repository} to version {new_version}[/dim]"
                )

            # Step 3: Update dependent repositories
            dependents_updated = []
            if update_dependents:
                dependents = self._get_dependent_repositories(repository)
                if dependents:
                    console.print(
                        f"\n[bold]Updating {len(dependents)} dependent repositories:[/bold]"
                    )
                    console.print(
                        f"  [dim]Dependents will get {dependents_bump}{' alpha' if alpha else ''} version bump[/dim]"
                    )

                    for dependent_repo in dependents:
                        console.print(f"  Processing {dependent_repo.name}...")

                        if not dry_run:
                            # First update dependency version in dependent repo
                            dep_update_success = self._update_dependency_version(
                                dependent_repo, repo.package_name, new_version
                            )

                            if dep_update_success:
                                # Then bump the dependent repository's own version
                                dependent_current_version = self._get_current_version(
                                    dependent_repo
                                )
                                if dependent_current_version:
                                    dependent_new_version = self._calculate_new_version(
                                        dependent_current_version,
                                        dependents_bump,
                                        alpha,
                                    )

                                    try:
                                        self._update_repository_version(
                                            dependent_repo, dependent_new_version
                                        )
                                        dependents_updated.append(
                                            {
                                                "name": dependent_repo.name,
                                                "old_version": dependent_current_version,
                                                "new_version": dependent_new_version,
                                                "bump_type": dependents_bump,
                                            }
                                        )
                                        console.print(
                                            f"  [green]✓[/green] Updated {dependent_repo.name}: {dependent_current_version} → {dependent_new_version}"
                                        )
                                    except Exception as e:
                                        console.print(
                                            f"  [red]✗[/red] Failed to bump version for {dependent_repo.name}: {e}"
                                        )
                                else:
                                    console.print(
                                        f"  [yellow]?[/yellow] Could not determine current version for {dependent_repo.name}"
                                    )
                            else:
                                console.print(
                                    f"  [red]✗[/red] Failed to update dependency in {dependent_repo.name}"
                                )
                        else:
                            # Dry run mode - show what would happen
                            dependent_current_version = self._get_current_version(
                                dependent_repo
                            )
                            if dependent_current_version:
                                dependent_new_version = self._calculate_new_version(
                                    dependent_current_version, dependents_bump, alpha
                                )
                                dependents_updated.append(
                                    {
                                        "name": dependent_repo.name,
                                        "old_version": dependent_current_version,
                                        "new_version": dependent_new_version,
                                        "bump_type": dependents_bump,
                                    }
                                )
                                console.print(
                                    f"  [dim]Would update {dependent_repo.name}: {dependent_current_version} → {dependent_new_version}[/dim]"
                                )
                            else:
                                console.print(
                                    f"  [dim]Would update {dependent_repo.name} (could not determine current version)[/dim]"
                                )
                else:
                    console.print("[dim]No dependent repositories found[/dim]")

            # Step 4: Record version history
            if not dry_run:
                self._record_version_history(
                    repository,
                    current_version,
                    new_version,
                    bump_type,
                    alpha,
                    dependents_updated,
                )

            # Step 5: Run validation tests
            if validate and not dry_run:
                console.print("\n[bold]Running validation tests...[/bold]")
                validation_success = self._run_validation_tests(
                    repo, dependents_updated
                )
                if not validation_success:
                    console.print("[red]Validation tests failed[/red]")
                    return False

            # Step 6: Summary
            console.print(
                "\n[green bold]✓ Version bump completed successfully![/green bold]"
            )
            console.print(f"  Repository: {repository}")
            console.print(f"  Version: {current_version} → {new_version}")
            if dependents_updated:
                dependent_names = [dep["name"] for dep in dependents_updated]
                console.print(f"  Updated dependents: {', '.join(dependent_names)}")
                for dep in dependents_updated:
                    console.print(
                        f"    {dep['name']}: {dep['old_version']} → {dep['new_version']} ({dep['bump_type']})"
                    )

            return True

        except Exception as e:
            console.print(f"[red]Error during version bump: {e}[/red]")
            logger.error(f"Version bump failed for {repository}: {e}")
            return False

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

    def _calculate_new_version(
        self, current_version: str, bump_type: str, alpha: bool = False
    ) -> str:
        """Calculate new version based on current version and bump type."""

        # Parse current version
        # Support formats: "1.2.3", "1.2.3-alpha.1", "1.2.3+dev.123", etc.
        version_pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-alpha\.(\d+))?(?:\+.*)?$"
        match = re.match(version_pattern, current_version)

        if not match:
            raise ValueError(f"Unable to parse version: {current_version}")

        major, minor, patch, current_alpha = match.groups()
        major, minor, patch = int(major), int(minor), int(patch)
        current_alpha = int(current_alpha) if current_alpha else None

        # Calculate new version based on bump type and alpha flag
        if alpha:
            if current_alpha is not None:
                # Already an alpha version, just increment alpha number
                new_major, new_minor, new_patch = major, minor, patch
                new_alpha = current_alpha + 1
            else:
                # Convert to alpha version with bump
                new_alpha = 1
                if bump_type == "patch":
                    new_major, new_minor, new_patch = major, minor, patch + 1
                elif bump_type == "minor":
                    new_major, new_minor, new_patch = major, minor + 1, 0
                elif bump_type == "major":
                    new_major, new_minor, new_patch = major + 1, 0, 0
                else:
                    # Default case to prevent undefined variables
                    new_major, new_minor, new_patch = major, minor, patch

            return f"{new_major}.{new_minor}.{new_patch}-alpha.{new_alpha}"
        else:
            # Regular version bump (remove alpha if present)
            if current_alpha is not None:
                # If currently alpha, don't increment for release
                if bump_type == "patch":
                    new_major, new_minor, new_patch = major, minor, patch
                elif bump_type == "minor":
                    new_major, new_minor, new_patch = major, minor, 0
                elif bump_type == "major":
                    new_major, new_minor, new_patch = major, 0, 0
            else:
                # Normal increment for non-alpha versions
                if bump_type == "patch":
                    new_major, new_minor, new_patch = major, minor, patch + 1
                elif bump_type == "minor":
                    new_major, new_minor, new_patch = major, minor + 1, 0
                elif bump_type == "major":
                    new_major, new_minor, new_patch = major + 1, 0, 0

            return f"{new_major}.{new_minor}.{new_patch}"

    def _update_repository_version(self, repo: RepositoryConfig, version: str) -> None:
        """Update repository version using Poetry."""
        try:
            subprocess.run(
                ["poetry", "version", version],
                cwd=repo.path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Also update the lock file
            subprocess.run(
                ["poetry", "lock", "--no-update"],
                cwd=repo.path,
                capture_output=True,
                check=False,  # Don't fail if this doesn't work
            )

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to update version for {repo.name}: {e}") from e

    def _get_dependent_repositories(self, repository: str) -> list[RepositoryConfig]:
        """Get all repositories that depend on the given repository."""
        config = self.config_manager.load_config()
        dependents = []

        for repo in config.repositories:
            if repository in repo.dependencies:
                dependents.append(repo)

        return dependents

    def _update_dependency_version(
        self, dependent_repo: RepositoryConfig, package_name: str, version: str
    ) -> bool:
        """Update dependency version in a dependent repository."""
        pyproject_path = dependent_repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            logger.warning(f"No pyproject.toml found in {dependent_repo.name}")
            return False

        try:
            # Read current pyproject.toml
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            # Update dependency version
            dependencies = (
                pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            )

            # Try multiple package name variations (hyphen vs underscore)
            possible_names = [
                package_name,
                package_name.replace("-", "_"),
                package_name.replace("_", "-"),
            ]

            found_dependency = None
            actual_dep_name = None

            for dep_name in possible_names:
                if dep_name in dependencies:
                    found_dependency = dependencies[dep_name]
                    actual_dep_name = dep_name
                    break

            if found_dependency is None:
                logger.warning(
                    f"Dependency {package_name} (or variations) not found in {dependent_repo.name}"
                )
                logger.info(f"Available dependencies: {list(dependencies.keys())}")
                return False

            logger.info(
                f"Found dependency '{actual_dep_name}' in {dependent_repo.name}"
            )

            # Handle different dependency formats
            if isinstance(found_dependency, str):
                # Simple version string, update it
                dependencies[actual_dep_name] = f"^{version}"
            elif isinstance(found_dependency, dict):
                if "version" in found_dependency:
                    # Dict with version key
                    found_dependency["version"] = f"^{version}"
                elif "path" in found_dependency:
                    # Local path dependency - don't update version
                    logger.info(
                        f"Skipping version update for local path dependency {actual_dep_name} in {dependent_repo.name}"
                    )
                    return True
                else:
                    # Add version to existing dict
                    found_dependency["version"] = f"^{version}"

            # Write back to file
            with open(pyproject_path, "w") as f:
                toml.dump(pyproject_data, f)

            # Update lock file
            try:
                subprocess.run(
                    ["poetry", "lock"],
                    cwd=dependent_repo.path,
                    capture_output=True,
                    check=True,
                    timeout=60,
                )
            except subprocess.CalledProcessError:
                logger.warning(f"Failed to update lock file for {dependent_repo.name}")

            return True

        except Exception as e:
            logger.error(
                f"Failed to update dependency {package_name} in {dependent_repo.name}: {e}"
            )
            return False

    def _record_version_history(
        self,
        repository: str,
        old_version: str,
        new_version: str,
        bump_type: str,
        alpha: bool,
        dependents_updated: list[dict[str, str]],
    ) -> None:
        """Record version change in history file."""

        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "repository": repository,
            "old_version": old_version,
            "new_version": new_version,
            "bump_type": bump_type,
            "alpha": alpha,
            "dependents_updated": dependents_updated,
        }

        # Load existing history
        history = []
        if self.version_history_file.exists():
            try:
                with open(self.version_history_file) as f:
                    history = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                history = []

        # Add new entry
        history.append(history_entry)

        # Keep only last 100 entries
        history = history[-100:]

        # Save history
        with open(self.version_history_file, "w") as f:
            json.dump(history, f, indent=2)

    def _run_validation_tests(
        self, repo: RepositoryConfig, dependents_updated: list[dict[str, str]]
    ) -> bool:
        """Run validation tests after version bump."""

        def _test_repository(repo_config: RepositoryConfig, repo_name: str) -> bool:
            """Test a single repository and return True if tests pass or no tests exist."""
            console.print(f"  Testing {repo_name}...")
            try:
                result = subprocess.run(
                    ["poetry", "run", "pytest", "-x", "--tb=short"],
                    cwd=repo_config.path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode == 0:
                    console.print(f"  [green]✓[/green] Tests passed for {repo_name}")
                    return True
                elif result.returncode == 5:
                    # Exit code 5 means "no tests found" - this is OK
                    console.print(
                        f"  [yellow]?[/yellow] No tests found for {repo_name} (OK)"
                    )
                    return True
                else:
                    console.print(f"  [red]✗[/red] Tests failed for {repo_name}")
                    logger.error(
                        f"Test output for {repo_name}: {result.stdout}\n{result.stderr}"
                    )
                    return False

            except subprocess.TimeoutExpired:
                console.print(f"  [red]✗[/red] Tests timed out for {repo_name}")
                return False
            except FileNotFoundError:
                console.print(
                    f"  [yellow]?[/yellow] pytest not found for {repo_name} (OK)"
                )
                return True

        # Test the repository itself
        if not _test_repository(repo, repo.name):
            return False

        # Test dependent repositories
        for dependent_info in dependents_updated:
            dependent_name = dependent_info["name"]
            dependent_repo = self.config_manager.get_repository(dependent_name)
            if dependent_repo and dependent_repo.path.exists():
                if not _test_repository(dependent_repo, dependent_name):
                    return False

        return True

    def get_version_status(self, repository: str | None = None) -> dict[str, Any]:
        """Get version status for repositories."""
        config = self.config_manager.load_config()

        if repository:
            # Get status for specific repository
            repo = self.config_manager.get_repository(repository)
            if not repo:
                raise ValueError(f"Repository '{repository}' not found")
            repos_to_check = [repo]
        else:
            # Get status for all repositories
            repos_to_check = config.repositories

        status: dict[str, Any] = {
            "repositories": [],
            "dependency_graph": {},
            "version_history": self._get_recent_version_history(),
        }

        for repo in repos_to_check:
            repo_status: dict[str, Any] = {
                "name": repo.name,
                "package_name": repo.package_name,
                "current_version": None,
                "is_alpha": False,
                "dependencies": [],
                "dependents": [],
                "path_exists": repo.path.exists(),
            }

            if repo.path.exists():
                # Get current version
                current_version = self._get_current_version(repo)
                repo_status["current_version"] = current_version

                if current_version:
                    repo_status["is_alpha"] = "-alpha." in current_version

                # Get dependencies info
                repo_status["dependencies"] = self._get_dependency_info(repo)

                # Get dependents
                dependents = self._get_dependent_repositories(repo.name)
                repo_status["dependents"] = [dep.name for dep in dependents]

            status["repositories"].append(repo_status)
            status["dependency_graph"][repo.name] = repo_status["dependencies"]

        return status

    def _get_dependency_info(self, repo: RepositoryConfig) -> list[dict[str, Any]]:
        """Get detailed dependency information for a repository."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            return []

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            dependencies = (
                pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            )
            dependency_info = []

            for dep_name, dep_spec in dependencies.items():
                if dep_name == "python":
                    continue

                # Check if this is one of our managed dependencies
                dep_repo = self.config_manager.get_repository(dep_name)
                if dep_repo:
                    info = {
                        "name": dep_name,
                        "managed": True,
                        "current_version": (
                            self._get_current_version(dep_repo)
                            if dep_repo.path.exists()
                            else None
                        ),
                    }

                    if isinstance(dep_spec, dict):
                        info["required_version"] = dep_spec.get("version")
                        info["is_path"] = "path" in dep_spec
                        info["source"] = dep_spec.get("source", "pypi")
                    elif isinstance(dep_spec, str):
                        info["required_version"] = dep_spec
                        info["is_path"] = False
                        info["source"] = "pypi"

                    # Check compatibility
                    if (
                        info["current_version"]
                        and info["required_version"]
                        and not info["is_path"]
                    ):
                        info["compatible"] = self._is_version_compatible(
                            info["required_version"], info["current_version"]
                        )
                    else:
                        info["compatible"] = None

                    dependency_info.append(info)

            return dependency_info

        except (toml.TomlDecodeError, KeyError):
            return []

    def _is_version_compatible(self, requirement: str, version: str) -> bool:
        """Check if a version satisfies a requirement."""
        # Simple compatibility check - in production you'd want proper semver parsing
        if requirement.startswith("^"):
            req_version = requirement[1:]
            # For caret requirements, major version must match
            req_major = req_version.split(".")[0]
            ver_major = version.split(".")[0]
            return req_major == ver_major
        elif requirement.startswith("~"):
            req_version = requirement[1:]
            # For tilde requirements, major.minor must match
            req_parts = req_version.split(".")[:2]
            ver_parts = version.split(".")[:2]
            return req_parts == ver_parts
        elif requirement == version:
            return True
        else:
            # Default to compatible for other cases
            return True

    def _get_recent_version_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent version history."""
        if not self.version_history_file.exists():
            return []

        try:
            with open(self.version_history_file) as f:
                history = json.load(f)

            # Return most recent entries
            return history[-limit:] if history else []

        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def display_version_status(
        self, status: dict[str, Any], show_dependents: bool = False
    ) -> None:
        """Display version status in a formatted table."""

        console.print("\n[bold]Version Status[/bold]")

        # Main repository table
        table = Table(title="Repositories")
        table.add_column("Repository", style="cyan")
        table.add_column("Package", style="bright_blue")
        table.add_column("Version", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Dependencies", style="magenta")

        if show_dependents:
            table.add_column("Dependents", style="dim cyan")

        for repo in status["repositories"]:
            version = repo.get("current_version", "N/A")
            version_display = (
                f"[green]{version}[/green]" if version != "N/A" else "[dim]N/A[/dim]"
            )

            if repo.get("is_alpha"):
                version_type = "[yellow]Alpha[/yellow]"
            else:
                version_type = "[green]Release[/green]"

            # Dependencies summary
            deps = repo.get("dependencies", [])
            if deps:
                managed_deps = [d for d in deps if d.get("managed")]
                incompatible_count = len(
                    [d for d in managed_deps if d.get("compatible") is False]
                )

                if incompatible_count > 0:
                    deps_display = (
                        f"[red]{len(managed_deps)} ({incompatible_count} issues)[/red]"
                    )
                else:
                    deps_display = f"{len(managed_deps)} deps"
            else:
                deps_display = "[dim]None[/dim]"

            row = [
                repo["name"],
                repo["package_name"],
                version_display,
                version_type,
                deps_display,
            ]

            if show_dependents:
                dependents = repo.get("dependents", [])
                dependents_display = (
                    ", ".join(dependents) if dependents else "[dim]None[/dim]"
                )
                row.append(dependents_display)

            table.add_row(*row)

        console.print(table)

        # Show detailed dependency information if there are issues
        for repo in status["repositories"]:
            dependencies = repo.get("dependencies", [])
            incompatible_deps = [
                d for d in dependencies if d.get("compatible") is False
            ]

            if incompatible_deps:
                console.print(
                    f"\n[red bold]Dependency Issues in {repo['name']}:[/red bold]"
                )
                for dep in incompatible_deps:
                    console.print(
                        f"  [red]•[/red] {dep['name']}: requires {dep['required_version']}, but current is {dep['current_version']}"
                    )

        # Show recent version history
        history = status.get("version_history", [])
        if history:
            console.print("\n[bold]Recent Version Changes:[/bold]")
            history_table = Table(show_header=True, header_style="bold")
            history_table.add_column("Date", style="dim")
            history_table.add_column("Repository", style="cyan")
            history_table.add_column("Change", style="yellow")
            history_table.add_column("Dependents", style="green")

            for entry in reversed(history[-5:]):  # Show last 5 entries
                timestamp = entry.get("timestamp", "")
                date_str = timestamp.split("T")[0] if timestamp else "Unknown"

                repo_name = entry.get("repository", "Unknown")
                old_ver = entry.get("old_version", "")
                new_ver = entry.get("new_version", "")
                bump_type = entry.get("bump_type", "")
                alpha = entry.get("alpha", False)

                change_str = (
                    f"{old_ver} → {new_ver} ({bump_type}{'alpha' if alpha else ''})"
                )

                dependents = entry.get("dependents_updated", [])
                dependents_str = (
                    ", ".join(dependents) if dependents else "[dim]None[/dim]"
                )

                history_table.add_row(date_str, repo_name, change_str, dependents_str)

            console.print(history_table)

    def sync_dependency_versions(
        self, dry_run: bool = False, force: bool = False
    ) -> bool:
        """Synchronize dependency versions across all repositories."""

        console.print("\n[bold]Synchronizing Dependency Versions[/bold]")

        if dry_run:
            console.print("[dim]DRY RUN MODE - No changes will be made[/dim]")

        config = self.config_manager.load_config()

        # Build current version map
        version_map = {}
        for repo in config.repositories:
            if repo.path.exists():
                current_version = self._get_current_version(repo)
                if current_version:
                    version_map[repo.package_name] = {
                        "version": current_version,
                        "repo_name": repo.name,
                    }

        console.print(f"Found versions for {len(version_map)} repositories")

        # Check each repository for outdated dependencies
        updates_needed = []
        dependency_order = self.config_manager.get_dependency_order()

        for repo_name in dependency_order:
            repo = self.config_manager.get_repository(repo_name)
            if not repo or not repo.path.exists():
                continue

            dependencies = self._get_dependency_info(repo)

            for dep in dependencies:
                if not dep.get("managed") or dep.get("is_path"):
                    continue

                current_version = version_map.get(dep["name"], {}).get("version")
                required_version = dep.get("required_version", "")

                if current_version and required_version:
                    # Extract version without prefix
                    clean_required = required_version.lstrip("^~=")

                    if clean_required != current_version:
                        updates_needed.append(
                            {
                                "repo": repo,
                                "dependency": dep["name"],
                                "current_required": required_version,
                                "new_required": f"^{current_version}",
                                "actual_version": current_version,
                            }
                        )

        if not updates_needed:
            console.print(
                "[green]✓ All dependency versions are already synchronized[/green]"
            )
            return True

        console.print(
            f"\n[yellow]Found {len(updates_needed)} dependencies to update:[/yellow]"
        )

        # Show what will be updated
        for update in updates_needed:
            console.print(
                f"  {update['repo'].name}: {update['dependency']} "
                f"{update['current_required']} → {update['new_required']}"
            )

        if not force and not dry_run:
            if (
                not console.input("\nProceed with updates? [y/N]: ")
                .lower()
                .startswith("y")
            ):
                console.print("Sync cancelled")
                return False

        # Apply updates
        success_count = 0
        for update in updates_needed:
            if not dry_run:
                success = self._update_dependency_version(
                    update["repo"], update["dependency"], update["actual_version"]
                )
                if success:
                    success_count += 1
                    console.print(f"  [green]✓[/green] Updated {update['repo'].name}")
                else:
                    console.print(
                        f"  [red]✗[/red] Failed to update {update['repo'].name}"
                    )
            else:
                console.print(f"  [dim]Would update {update['repo'].name}[/dim]")
                success_count += 1

        if not dry_run:
            console.print(
                f"\n[green]✓ Successfully updated {success_count}/{len(updates_needed)} dependencies[/green]"
            )

        return success_count == len(updates_needed)
