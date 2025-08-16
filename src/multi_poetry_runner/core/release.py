"""Release coordination functionality."""

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any

import toml
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..utils.config import ConfigManager, RepositoryConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class ReleaseStage(Enum):
    """Release stages."""

    DEV = "dev"
    RC = "rc"
    PROD = "prod"


class ReleaseStatus(Enum):
    """Release status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ReleaseCoordinator:
    """Coordinates releases across multiple repositories."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.workspace_root = config_manager.workspace_root
        self.backups: dict[str, Any] = {}
        self.release_results: dict[str, ReleaseStatus] = {}

    def create_release(
        self,
        stage: str,
        repositories: list[str] | None = None,
        version: str | None = None,
        repository_versions: dict[str, str] | None = None,
        dry_run: bool = False,
        skip_tests: bool = False,
        force: bool = False,
        parallel: bool = False,
    ) -> bool:
        """Create a release for specific repositories or all repositories.

        Args:
            stage: Release stage (dev, rc, prod)
            repositories: List of repository names to release (None for all)
            version: Default version for all repositories
            repository_versions: Dict mapping repository names to specific versions
            dry_run: Perform dry run without making changes
            skip_tests: Skip running tests
            force: Continue despite failures
            parallel: Process repos in parallel where possible
        """

        release_stage = ReleaseStage(stage)
        config = self.config_manager.load_config()

        # Determine which repositories to release
        if repositories:
            repos_to_release: list[RepositoryConfig] = []
            for repo_name in repositories:
                repo = self.config_manager.get_repository(repo_name)
                if repo:
                    repos_to_release.append(repo)
                else:
                    logger.error(f"Repository '{repo_name}' not found in configuration")
                    return False
        else:
            repos_to_release = config.repositories

        logger.info(
            f"Starting {stage} release for repositories: {[r.name for r in repos_to_release]}"
        )

        if dry_run:
            console.print(
                "[yellow]Running in DRY RUN mode - no changes will be made[/yellow]"
            )

        # Validate repository versions
        if repository_versions:
            for repo_name in repository_versions:
                if not any(r.name == repo_name for r in repos_to_release):
                    logger.error(
                        f"Repository '{repo_name}' specified in versions but not in release list"
                    )
                    return False

        # Create backups
        if not dry_run:
            self._create_backups()

        # Get release order (only for repositories being released)
        all_repo_names = [r.name for r in repos_to_release]
        release_order = [
            name
            for name in self.config_manager.get_dependency_order()
            if name in all_repo_names
        ]

        # Process repositories
        success = True

        if parallel and stage == "dev":
            # Only allow parallel for dev releases of independent packages
            success = self._process_repositories_parallel(
                release_order,
                release_stage,
                repos_to_release,
                version,
                repository_versions,
                dry_run,
                skip_tests,
            )
        else:
            success = self._process_repositories_sequential(
                release_order,
                release_stage,
                repos_to_release,
                version,
                repository_versions,
                dry_run,
                skip_tests,
                force,
            )

        # Update dependent repositories if this is a production release
        if success and release_stage == ReleaseStage.PROD and not dry_run:
            console.print("\n[bold]Updating dependent repositories...[/bold]")
            success = self._update_dependent_repositories(repos_to_release)

        # Create tags for production releases only after everything succeeds
        if success and release_stage == ReleaseStage.PROD and not dry_run:
            console.print("\n[bold]Creating release tags...[/bold]")
            for repo in repos_to_release:
                new_version = self._get_current_version(repo)
                if new_version:
                    self._tag_release(repo, new_version)

            # Push all commits and tags to remote
            console.print("\n[bold]Pushing changes to remote...[/bold]")
            for repo in repos_to_release:
                try:
                    # Push the main branch
                    subprocess.run(["git", "push"], cwd=repo.path, check=True)
                    logger.info(f"Pushed commits to remote for {repo.name}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to push commits for {repo.name}: {e}")
                    # Don't fail the release for push errors, just log them

        # Run integration tests if all individual releases succeeded
        if success and not skip_tests and not dry_run:
            console.print("\n[bold]Running integration tests...[/bold]")
            success = self._run_integration_tests()

        # Handle results
        if success:
            console.print(
                f"\n[green]✓ {stage.upper()} release completed successfully![/green]"
            )
            self._print_release_summary()
        else:
            console.print(f"\n[red]✗ {stage.upper()} release failed[/red]")
            if not dry_run and not force:
                console.print("Rolling back changes...")
                self._rollback_release()

        return success

    def _create_backups(self) -> None:
        """Create backups of all repository states."""
        config = self.config_manager.load_config()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.config_manager.get_backups_path() / f"release_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        for repo in config.repositories:
            if repo.path.exists():
                repo_backup = {
                    "pyproject_toml": None,
                    "git_commit": None,
                    "backup_dir": backup_dir / repo.name,
                }

                # Create repo backup directory
                repo_backup["backup_dir"].mkdir(exist_ok=True)

                # Backup pyproject.toml
                pyproject_path = repo.path / "pyproject.toml"
                if pyproject_path.exists():
                    backup_path = repo_backup["backup_dir"] / "pyproject.toml"
                    shutil.copy2(pyproject_path, backup_path)
                    repo_backup["pyproject_toml"] = backup_path

                # Get current git commit
                try:
                    result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=repo.path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    repo_backup["git_commit"] = result.stdout.strip()
                except subprocess.CalledProcessError:
                    logger.warning(f"Could not get git commit for {repo.name}")

                self.backups[repo.name] = repo_backup

        logger.info(f"Created backups in {backup_dir}")

    def _process_repositories_sequential(
        self,
        release_order: list[str],
        stage: ReleaseStage,
        repos_to_release: list[RepositoryConfig],
        version: str | None,
        repository_versions: dict[str, str] | None,
        dry_run: bool,
        skip_tests: bool,
        force: bool,
    ) -> bool:
        """Process repositories sequentially."""

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:

            task = progress.add_task(
                "Releasing repositories...", total=len(release_order)
            )

            for repo_name in release_order:
                repo = next((r for r in repos_to_release if r.name == repo_name), None)
                if not repo:
                    continue

                progress.update(task, description=f"Processing {repo_name}...")

                # Determine version for this repository
                repo_version = None
                if repository_versions and repo_name in repository_versions:
                    repo_version = repository_versions[repo_name]
                elif version:
                    repo_version = version

                success = self._process_single_repository(
                    repo, stage, repo_version, dry_run, skip_tests
                )

                if not success:
                    if force:
                        logger.warning(
                            f"Repository {repo_name} failed but continuing due to --force"
                        )
                        self.release_results[repo_name] = ReleaseStatus.FAILED
                    else:
                        logger.error(f"Repository {repo_name} failed, stopping release")
                        return False
                else:
                    self.release_results[repo_name] = ReleaseStatus.SUCCESS

                progress.advance(task)

        return True

    def _process_repositories_parallel(
        self,
        release_order: list[str],
        stage: ReleaseStage,
        repos_to_release: list[RepositoryConfig],
        version: str | None,
        repository_versions: dict[str, str] | None,
        dry_run: bool,
        skip_tests: bool,
    ) -> bool:
        """Process independent repositories in parallel."""

        # Only process repositories with no dependencies in parallel
        independent_repos = [repo for repo in repos_to_release if not repo.dependencies]
        dependent_repos = [repo for repo in repos_to_release if repo.dependencies]

        success = True

        # Process independent repos in parallel
        if independent_repos:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}

                for repo in independent_repos:
                    # Determine version for this repository
                    repo_version = None
                    if repository_versions and repo.name in repository_versions:
                        repo_version = repository_versions[repo.name]
                    elif version:
                        repo_version = version

                    future = executor.submit(
                        self._process_single_repository,
                        repo,
                        stage,
                        repo_version,
                        dry_run,
                        skip_tests,
                    )
                    futures[future] = repo

                for future in as_completed(futures):
                    repo = futures[future]
                    try:
                        result = future.result()
                        self.release_results[repo.name] = (
                            ReleaseStatus.SUCCESS if result else ReleaseStatus.FAILED
                        )
                        if not result:
                            success = False
                    except Exception as e:
                        logger.error(f"Error processing {repo.name}: {e}")
                        self.release_results[repo.name] = ReleaseStatus.FAILED
                        success = False

        # Process dependent repos sequentially
        if success and dependent_repos:
            for repo in dependent_repos:
                # Determine version for this repository
                repo_version = None
                if repository_versions and repo.name in repository_versions:
                    repo_version = repository_versions[repo.name]
                elif version:
                    repo_version = version

                result = self._process_single_repository(
                    repo, stage, repo_version, dry_run, skip_tests
                )
                self.release_results[repo.name] = (
                    ReleaseStatus.SUCCESS if result else ReleaseStatus.FAILED
                )
                if not result:
                    success = False
                    break

        return success

    def _process_single_repository(
        self,
        repo: RepositoryConfig,
        stage: ReleaseStage,
        version: str | None,
        dry_run: bool,
        skip_tests: bool,
    ) -> bool:
        """Process a single repository for release."""

        logger.info(f"Processing {repo.name} for {stage.value} release")

        if not repo.path.exists():
            logger.error(f"Repository {repo.name} does not exist at {repo.path}")
            return False

        try:
            # Step 1: Update version
            new_version = self._determine_version(repo, stage, version)

            # Check if this version has already been released (for production releases)
            if stage == ReleaseStage.PROD and not dry_run:
                if self._version_already_released(repo, new_version):
                    logger.warning(
                        f"Version {new_version} has already been released for {repo.name}"
                    )
                    console.print(
                        f"[yellow]Version {new_version} already exists for {repo.name}, skipping[/yellow]"
                    )
                    return True  # Consider this successful since the version exists

            if not dry_run:
                self._update_repository_version(repo, new_version)

            # Step 2: Update dependency versions
            if not dry_run:
                self._update_dependency_versions(repo)

            # Step 3: Update lock file
            if not dry_run:
                self._update_lock_file(repo)

            # Step 4: Run tests
            if not skip_tests and not dry_run:
                if not self._run_repository_tests(repo):
                    raise Exception("Tests failed")

            # Step 5: Commit changes
            if not dry_run:
                self._commit_changes(repo, f"Release version {new_version}")

            # Note: Tagging happens later in the main release process after dependent updates

            if dry_run:
                console.print(f"[dim]Would release {repo.name} as {new_version}[/dim]")
            else:
                logger.info(f"Successfully released {repo.name} version {new_version}")

            return True

        except Exception as e:
            logger.error(f"Failed to process {repo.name}: {e}")
            return False

    def _version_already_released(self, repo: RepositoryConfig, version: str) -> bool:
        """Check if a version has already been released by looking for the tag."""
        tag = f"v{version}"

        try:
            result = subprocess.run(
                ["git", "tag", "-l", tag],
                cwd=repo.path,
                capture_output=True,
                text=True,
                check=True,
            )

            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            logger.warning(f"Could not check for existing tags in {repo.name}")
            return False

    def _determine_version(
        self, repo: RepositoryConfig, stage: ReleaseStage, version: str | None
    ) -> str:
        """Determine the version for a repository."""
        if version:
            base_version = version
        else:
            # Get current version
            current_version = self._get_current_version(repo)
            if current_version:
                base_version = current_version
            else:
                raise ValueError(f"Cannot determine version for {repo.name}")

        # Format version based on stage
        if stage == ReleaseStage.DEV:
            # Development version with timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            return f"{base_version}+dev.{timestamp}"
        elif stage == ReleaseStage.RC:
            # Release candidate
            return f"{base_version}rc1"
        else:
            # Production release
            return base_version

    def _get_current_version(self, repo: RepositoryConfig) -> str | None:
        """Get current version from repository."""
        pyproject_path = repo.path / "pyproject.toml"

        if not pyproject_path.exists():
            return None

        try:
            with open(pyproject_path) as f:
                pyproject_data = toml.load(f)

            return pyproject_data.get("tool", {}).get("poetry", {}).get("version")
        except (toml.TomlDecodeError, KeyError):
            return None

    def _update_repository_version(self, repo: RepositoryConfig, version: str) -> None:
        """Update repository version using Poetry."""
        subprocess.run(
            ["poetry", "version", version],
            cwd=repo.path,
            check=True,
            capture_output=True,
        )

    def _update_dependency_versions(self, repo: RepositoryConfig) -> None:
        """Update dependency versions in repository."""
        # This would update dependencies to use the new versions
        # For now, we'll assume dependencies are already correctly set
        pass

    def _update_lock_file(self, repo: RepositoryConfig) -> None:
        """Update Poetry lock file."""
        try:
            # Try standard lock first
            subprocess.run(
                ["poetry", "lock"],
                cwd=repo.path,
                check=True,
                capture_output=True,
                timeout=60,  # Add timeout to prevent hanging
            )
        except subprocess.CalledProcessError:
            logger.warning(
                f"Standard poetry lock failed for {repo.name}, trying --regenerate"
            )
            try:
                # Fallback to regenerate lock file when standard lock fails
                subprocess.run(
                    ["poetry", "lock", "--regenerate"],
                    cwd=repo.path,
                    check=True,
                    capture_output=True,
                    timeout=120,  # Longer timeout for regenerate
                )
                logger.info(f"Successfully regenerated lock file for {repo.name}")
            except subprocess.CalledProcessError as regenerate_error:
                logger.error(
                    f"Both standard and regenerate lock failed for {repo.name}"
                )
                raise regenerate_error
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Poetry lock timed out for {repo.name}, trying --regenerate"
            )
            try:
                subprocess.run(
                    ["poetry", "lock", "--regenerate"],
                    cwd=repo.path,
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
                logger.info(
                    f"Successfully regenerated lock file for {repo.name} after timeout"
                )
            except subprocess.CalledProcessError as regenerate_error:
                logger.error(f"Lock regeneration failed for {repo.name} after timeout")
                raise regenerate_error

    def _run_repository_tests(self, repo: RepositoryConfig) -> bool:
        """Run tests for a repository."""
        try:
            subprocess.run(
                ["poetry", "run", "pytest", "-v"],
                cwd=repo.path,
                check=True,
                capture_output=True,
                timeout=300,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _commit_changes(self, repo: RepositoryConfig, message: str) -> None:
        """Commit changes in repository."""
        # Add files
        subprocess.run(
            ["git", "add", "pyproject.toml", "poetry.lock"], cwd=repo.path, check=True
        )

        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=repo.path, check=True)

    def _commit_dependency_changes(self, repo: RepositoryConfig, message: str) -> None:
        """Commit dependency changes in repository (pyproject.toml only)."""
        # Add only pyproject.toml - poetry.lock will be updated after package is published
        subprocess.run(["git", "add", "pyproject.toml"], cwd=repo.path, check=True)

        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=repo.path, check=True)

    def _tag_release(self, repo: RepositoryConfig, version: str) -> None:
        """Create git tag for release."""
        tag = f"v{version}"

        # Check if tag already exists
        try:
            result = subprocess.run(
                ["git", "tag", "-l", tag],
                cwd=repo.path,
                capture_output=True,
                text=True,
                check=True,
            )

            if result.stdout.strip():
                logger.warning(
                    f"Tag {tag} already exists in {repo.name}, skipping tag creation"
                )
                return
        except subprocess.CalledProcessError:
            logger.warning(f"Could not check for existing tags in {repo.name}")

        # Create the tag
        try:
            subprocess.run(
                ["git", "tag", "-a", tag, "-m", f"Release {tag}"],
                cwd=repo.path,
                check=True,
            )
            logger.info(f"Created tag {tag} in {repo.name}")

            # Push the tag to remote
            subprocess.run(["git", "push", "origin", tag], cwd=repo.path, check=True)
            logger.info(f"Pushed tag {tag} to remote for {repo.name}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create or push tag {tag} in {repo.name}: {e}")
            raise

    def _update_dependent_repositories(
        self, released_repos: list[RepositoryConfig]
    ) -> bool:
        """Update dependent repositories to use the new released versions with cascading updates."""
        # Create a map of released repository versions
        released_versions: dict[str, str] = {}
        for repo in released_repos:
            new_version = self._get_current_version(repo)
            if new_version:
                released_versions[repo.name] = new_version
                # Also try with package name variations
                released_versions[repo.package_name] = new_version
                released_versions[repo.package_name.replace("-", "_")] = new_version
                released_versions[repo.package_name.replace("_", "-")] = new_version

        # Find all repositories that need updates (direct and cascading dependencies)
        all_dependents = self._find_all_dependent_repositories(released_repos)

        if not all_dependents:
            console.print("[dim]No dependent repositories found[/dim]")
            return True

        console.print(f"Found {len(all_dependents)} dependent repositories to update:")
        for dep_repo in all_dependents:
            console.print(f"  - {dep_repo.name}")

        # Process dependents in dependency order to handle cascading updates
        dependency_order = self.config_manager.get_dependency_order()
        ordered_dependents = [
            repo
            for repo_name in dependency_order
            for repo in all_dependents
            if repo.name == repo_name
        ]

        # Track which repositories have been updated in this release cycle
        updated_in_this_cycle: dict[str, str | None] = {
            repo.name: self._get_current_version(repo) for repo in released_repos
        }
        success_count = 0

        for dep_repo in ordered_dependents:
            try:
                console.print(f"  Updating {dep_repo.name}...")

                # Check which dependencies need updating
                dependencies_updated = False

                # Check for direct dependencies on released repos
                for released_repo in released_repos:
                    released_version = released_versions.get(released_repo.name)
                    if released_version and self._update_dependency_version(
                        dep_repo, released_repo.package_name, released_version
                    ):
                        dependencies_updated = True

                # Check for dependencies on other repos that were updated in this cycle
                for updated_repo_name, updated_version in updated_in_this_cycle.items():
                    if updated_repo_name in [r.name for r in released_repos]:
                        continue  # Already handled above

                    updated_repo = self.config_manager.get_repository(updated_repo_name)
                    if updated_repo and self._update_dependency_version(
                        dep_repo, updated_repo.package_name, updated_version or ""
                    ):
                        dependencies_updated = True

                if dependencies_updated:
                    # Bump the dependent repository's version
                    current_dep_version = self._get_current_version(dep_repo)
                    new_dep_version = None
                    if current_dep_version:
                        new_dep_version = self._calculate_dependent_version_bump(
                            current_dep_version
                        )
                        self._update_repository_version(dep_repo, new_dep_version)
                        console.print(
                            f"    Bumped {dep_repo.name} version: {current_dep_version} → {new_dep_version}"
                        )

                        # Track this update for cascading to other dependents
                        updated_in_this_cycle[dep_repo.name] = new_dep_version

                    # Skip lock file update for dependent repositories - will be done after package is published
                    # The CI/CD pipeline will handle poetry lock after the dependency is available

                    # Check if there are actually changes to commit
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=dep_repo.path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    if result.stdout.strip():
                        # Build commit message with all updated dependencies
                        updated_deps: list[str] = []
                        for released_repo in released_repos:
                            if released_repo.name in updated_in_this_cycle:
                                version_str = updated_in_this_cycle[released_repo.name]
                                if version_str:
                                    updated_deps.append(
                                        f"{released_repo.package_name}@{version_str}"
                                    )

                        # Add other cascading updates
                        for (
                            updated_repo_name,
                            updated_version,
                        ) in updated_in_this_cycle.items():
                            if (
                                updated_repo_name
                                not in [r.name for r in released_repos]
                                and updated_repo_name != dep_repo.name
                            ):
                                updated_repo = self.config_manager.get_repository(
                                    updated_repo_name
                                )
                                if (
                                    updated_repo
                                    and updated_repo_name in dep_repo.dependencies
                                ):
                                    if updated_version:
                                        updated_deps.append(
                                            f"{updated_repo.package_name}@{updated_version}"
                                        )

                        # Remove duplicates while preserving order
                        unique_deps: list[str] = []
                        seen = set()
                        for dep in updated_deps:
                            if dep not in seen:
                                unique_deps.append(dep)
                                seen.add(dep)

                        commit_message = (
                            f"Update dependencies: {', '.join(unique_deps)}"
                        )

                        # Add version bump info to commit message
                        if current_dep_version and new_dep_version:
                            commit_message += f"; bump version to {new_dep_version}"

                        self._commit_dependency_changes(dep_repo, commit_message)
                        console.print(f"  [green]✓[/green] Updated {dep_repo.name}")
                    else:
                        # No changes needed, dependency was already at correct version
                        console.print(
                            f"  [green]✓[/green] {dep_repo.name} already at correct version"
                        )

                    success_count += 1
                else:
                    console.print(
                        f"  [yellow]?[/yellow] No updates needed for {dep_repo.name}"
                    )
                    success_count += 1  # Consider this successful

            except Exception as e:
                console.print(f"  [red]✗[/red] Failed to update {dep_repo.name}: {e}")
                logger.error(
                    f"Failed to update dependent repository {dep_repo.name}: {e}"
                )

        if success_count == len(ordered_dependents):
            console.print(
                f"[green]✓ Successfully updated all {len(ordered_dependents)} dependent repositories[/green]"
            )
            return True
        else:
            console.print(
                f"[yellow]Updated {success_count}/{len(ordered_dependents)} dependent repositories[/yellow]"
            )
            return False

    def _find_all_dependent_repositories(
        self, released_repos: list[RepositoryConfig]
    ) -> list[RepositoryConfig]:
        """Find all repositories that depend on the released repos, including cascading dependencies."""
        config = self.config_manager.load_config()
        released_repo_names = {repo.name for repo in released_repos}
        all_dependents: list[RepositoryConfig] = []
        dependent_names = set()  # Track names to avoid duplicates

        # Use a queue to process dependencies level by level
        to_process = list(released_repo_names)
        processed = set()

        while to_process:
            current_repo_name = to_process.pop(0)
            if current_repo_name in processed:
                continue

            processed.add(current_repo_name)

            # Find direct dependents of current repo
            for repo in config.repositories:
                if repo.name in released_repo_names:
                    continue  # Skip repositories we just released

                if not repo.path.exists():
                    continue

                # Check if this repo depends on current repo
                if current_repo_name in repo.dependencies:
                    if repo.name not in dependent_names:
                        all_dependents.append(repo)
                        dependent_names.add(repo.name)
                        # Add this repo to be processed for cascading dependencies
                        to_process.append(repo.name)

        return all_dependents

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
                logger.info(
                    f"Dependency {package_name} (or variations) not found in {dependent_repo.name}"
                )
                return False

            logger.info(
                f"Found dependency '{actual_dep_name}' in {dependent_repo.name}"
            )

            # Store the original value to check if we actually made a change
            original_dependency = None
            new_version_spec = f"^{version}"
            changed = False

            # Handle different dependency formats
            if isinstance(found_dependency, str):
                # Simple version string
                original_dependency = found_dependency
                if found_dependency != new_version_spec:
                    dependencies[actual_dep_name] = new_version_spec
                    changed = True
            elif isinstance(found_dependency, dict):
                if "version" in found_dependency:
                    # Dict with version key
                    original_dependency = found_dependency["version"]
                    if found_dependency["version"] != new_version_spec:
                        found_dependency["version"] = new_version_spec
                        changed = True
                elif "path" in found_dependency:
                    # Local path dependency - don't update version
                    logger.info(
                        f"Skipping version update for local path dependency {actual_dep_name} in {dependent_repo.name}"
                    )
                    return False
                else:
                    # Add version to existing dict
                    found_dependency["version"] = new_version_spec
                    changed = True

            if changed:
                # Write back to file
                with open(pyproject_path, "w") as f:
                    toml.dump(pyproject_data, f)
                logger.info(
                    f"Updated {actual_dep_name} from {original_dependency} to {new_version_spec} in {dependent_repo.name}"
                )
                return True
            else:
                logger.info(
                    f"Dependency {actual_dep_name} in {dependent_repo.name} already at version {original_dependency}"
                )
                return False

        except Exception as e:
            logger.error(
                f"Failed to update dependency {package_name} in {dependent_repo.name}: {e}"
            )
            return False

    def _calculate_dependent_version_bump(self, current_version: str) -> str:
        """Calculate the next version for a dependent repository when dependencies are updated.

        Rules:
        - If already alpha: increment alpha number (e.g., 1.2.3-alpha.1 -> 1.2.3-alpha.2)
        - If not alpha: increment patch and add alpha.1 (e.g., 1.2.3 -> 1.2.4-alpha.1)
        """
        import re

        # Parse current version - support formats like "1.2.3", "1.2.3-alpha.1", etc.
        version_pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-alpha\.(\d+))?(?:\+.*)?$"
        match = re.match(version_pattern, current_version)

        if not match:
            # If we can't parse it, just append alpha.1
            logger.warning(
                f"Could not parse version {current_version}, appending -alpha.1"
            )
            return f"{current_version}-alpha.1"

        major, minor, patch, alpha = match.groups()
        major, minor, patch = int(major), int(minor), int(patch)
        alpha = int(alpha) if alpha else None

        if alpha is not None:
            # Already an alpha version, just increment alpha number
            new_alpha = alpha + 1
            return f"{major}.{minor}.{patch}-alpha.{new_alpha}"
        else:
            # Not alpha, increment patch and add alpha.1
            new_patch = patch + 1
            return f"{major}.{minor}.{new_patch}-alpha.1"

    def _run_integration_tests(self) -> bool:
        """Run integration tests."""
        # This would run the integration test framework
        # For now, return True
        return True

    def _rollback_release(self) -> None:
        """Rollback failed release."""
        console.print("Rolling back release changes...")

        for repo_name, backup in self.backups.items():
            repo = self.config_manager.get_repository(repo_name)
            if not repo:
                continue

            try:
                # Restore pyproject.toml
                if backup["pyproject_toml"]:
                    shutil.copy2(backup["pyproject_toml"], repo.path / "pyproject.toml")

                # Reset git
                if backup["git_commit"]:
                    subprocess.run(
                        ["git", "reset", "--hard", backup["git_commit"]],
                        cwd=repo.path,
                        check=True,
                    )

                # Clean up any orphaned tags created during failed release
                self._cleanup_orphaned_tags(repo, backup["git_commit"])

                # Update lock file during rollback
                try:
                    subprocess.run(
                        ["poetry", "lock"],
                        cwd=repo.path,
                        check=True,
                        capture_output=True,
                        timeout=60,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    # If standard lock fails during rollback, try regenerate
                    logger.warning(
                        f"Standard lock failed during rollback for {repo.name}, trying --regenerate"
                    )
                    subprocess.run(
                        ["poetry", "lock", "--regenerate"],
                        cwd=repo.path,
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )

                self.release_results[repo_name] = ReleaseStatus.ROLLED_BACK
                logger.info(f"Rolled back {repo_name}")

            except Exception as e:
                logger.error(f"Failed to rollback {repo_name}: {e}")

    def _cleanup_orphaned_tags(
        self, repo: RepositoryConfig, backup_commit: str
    ) -> None:
        """Clean up tags that point to commits that are no longer in the branch after rollback."""
        try:
            # Get all tags
            result = subprocess.run(
                ["git", "tag", "-l"],
                cwd=repo.path,
                capture_output=True,
                text=True,
                check=True,
            )

            if not result.stdout.strip():
                return

            tags = result.stdout.strip().split("\n")

            for tag in tags:
                if not tag.strip():
                    continue

                try:
                    # Get the commit that the tag points to
                    tag_commit_result = subprocess.run(
                        ["git", "rev-list", "-n", "1", tag],
                        cwd=repo.path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    tag_commit = tag_commit_result.stdout.strip()

                    # Check if this commit is reachable from current HEAD
                    reachable_result = subprocess.run(
                        ["git", "merge-base", "--is-ancestor", tag_commit, "HEAD"],
                        cwd=repo.path,
                        capture_output=True,
                        text=True,
                    )

                    # If exit code is not 0, the tag commit is not an ancestor of HEAD (orphaned)
                    if reachable_result.returncode != 0:
                        logger.warning(f"Removing orphaned tag {tag} from {repo.name}")
                        subprocess.run(
                            ["git", "tag", "-d", tag],
                            cwd=repo.path,
                            check=True,
                            capture_output=True,
                        )

                except subprocess.CalledProcessError:
                    # If we can't check this tag, skip it
                    continue

        except subprocess.CalledProcessError:
            logger.warning(f"Could not clean up orphaned tags in {repo.name}")

    def _print_release_summary(self) -> None:
        """Print release summary."""
        table = Table(title="Release Summary")
        table.add_column("Repository", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Version", style="yellow")

        for repo_name, status in self.release_results.items():
            repo = self.config_manager.get_repository(repo_name)
            version = self._get_current_version(repo) if repo else "unknown"

            status_icon = {
                ReleaseStatus.SUCCESS: "✓",
                ReleaseStatus.FAILED: "✗",
                ReleaseStatus.ROLLED_BACK: "↺",
            }.get(status, "?")

            status_color = {
                ReleaseStatus.SUCCESS: "green",
                ReleaseStatus.FAILED: "red",
                ReleaseStatus.ROLLED_BACK: "yellow",
            }.get(status, "white")

            table.add_row(
                repo_name,
                f"[{status_color}]{status_icon} {status.value}[/{status_color}]",
                version,
            )

        console.print(table)

    def get_status(self, verbose: bool = False) -> dict[str, Any]:
        """Get release status."""
        config = self.config_manager.load_config()
        status = {"workspace": config.name, "repositories": []}

        for repo in config.repositories:
            repo_status = {
                "name": repo.name,
                "current_version": self._get_current_version(repo),
                "last_release": self._get_last_release_info(repo),
                "pending_changes": self._get_pending_changes(repo),
            }

            if verbose:
                repo_status["detailed_status"] = self._get_detailed_status(repo)

            status["repositories"].append(repo_status)

        return status

    def _get_last_release_info(self, repo: RepositoryConfig) -> dict[str, str] | None:
        """Get information about the last release."""
        if not repo.path.exists():
            return None

        try:
            # Get latest tag
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=repo.path,
                capture_output=True,
                text=True,
                check=True,
            )

            tag = result.stdout.strip()

            # Get tag date
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cd", "--date=iso", tag],
                cwd=repo.path,
                capture_output=True,
                text=True,
                check=True,
            )

            date = result.stdout.strip()

            return {"tag": tag, "date": date}

        except subprocess.CalledProcessError:
            return None

    def _get_pending_changes(self, repo: RepositoryConfig) -> bool:
        """Check if repository has pending changes."""
        if not repo.path.exists():
            return False

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo.path,
                capture_output=True,
                text=True,
                check=True,
            )

            return bool(result.stdout.strip())

        except subprocess.CalledProcessError:
            return False

    def _get_detailed_status(self, repo: RepositoryConfig) -> dict[str, Any]:
        """Get detailed repository status."""
        # Implementation for detailed status
        return {}

    def display_status(self, status: dict[str, Any]) -> None:
        """Display release status."""
        console.print(
            f"\n[bold]Release Status for workspace: {status['workspace']}[/bold]"
        )

        table = Table(title="Repositories")
        table.add_column("Name", style="cyan")
        table.add_column("Current Version", style="green")
        table.add_column("Last Release", style="yellow")
        table.add_column("Pending Changes", style="red")

        for repo in status["repositories"]:
            last_release = repo.get("last_release")
            last_release_str = last_release["tag"] if last_release else "None"

            pending_icon = "✓" if repo.get("pending_changes") else ""

            table.add_row(
                repo["name"],
                repo.get("current_version", "Unknown"),
                last_release_str,
                pending_icon,
            )

        console.print(table)

    def rollback(self) -> bool:
        """Rollback the last release."""
        if not self.backups:
            console.print("[red]No backup found to rollback[/red]")
            return False

        self._rollback_release()
        console.print("[green]Release rollback completed[/green]")
        return True
