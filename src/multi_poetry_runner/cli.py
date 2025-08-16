#!/usr/bin/env python3
"""
Main CLI interface for Multi-Poetry Runner (MPR).
"""

import sys
import subprocess
import toml
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.logging import RichHandler
import logging

from .core.workspace import WorkspaceManager
from .core.dependencies import DependencyManager
from .core.release import ReleaseCoordinator
from .core.testing import TestRunner
from .core.hooks import GitHooksManager
from .core.version_manager import VersionManager
from .utils.config import ConfigManager
from .utils.logger import setup_logging

# Global console for rich output
console = Console()

# Version info
from . import __version__


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--config", "-c", type=click.Path(exists=True), help="Path to configuration file"
)
@click.option(
    "--workspace", "-w", type=click.Path(), help="Path to workspace directory"
)
@click.version_option(version=__version__)
@click.pass_context
def main(
    ctx: click.Context, verbose: bool, config: Optional[str], workspace: Optional[str]
) -> None:
    """Multi-Poetry Runner - Multi-repository development made easy."""

    # Set up logging
    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logging(log_level)

    # Initialize context
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_file"] = Path(config) if config else None
    ctx.obj["workspace_root"] = Path(workspace) if workspace else Path.cwd()

    # Initialize config manager
    try:
        ctx.obj["config_manager"] = ConfigManager(
            config_file=ctx.obj["config_file"], workspace_root=ctx.obj["workspace_root"]
        )
    except Exception as e:
        console.print(f"[red]Error initializing configuration: {e}[/red]")
        sys.exit(1)


@main.group()
@click.pass_context
def workspace(ctx: click.Context) -> None:
    """Manage development workspace."""
    pass


@workspace.command("init")
@click.argument("name")
@click.option("--python-version", default="3.11", help="Python version to use")
@click.pass_context
def workspace_init(ctx: click.Context, name: str, python_version: str) -> None:
    """Initialize a new workspace."""
    try:
        manager = WorkspaceManager(ctx.obj["config_manager"])
        manager.initialize_workspace(name, python_version)
        console.print(f"[green]✓ Workspace '{name}' initialized successfully[/green]")
    except Exception as e:
        console.print(f"[red]Error initializing workspace: {e}[/red]")
        sys.exit(1)


@workspace.command("setup")
@click.option("--ci-mode", is_flag=True, help="Run in CI mode")
@click.pass_context
def workspace_setup(ctx: click.Context, ci_mode: bool) -> None:
    """Set up the workspace (clone repos, install dependencies)."""
    try:
        manager = WorkspaceManager(ctx.obj["config_manager"])
        manager.setup_workspace(ci_mode=ci_mode)
        console.print("[green]✓ Workspace setup completed[/green]")
    except Exception as e:
        console.print(f"[red]Error setting up workspace: {e}[/red]")
        sys.exit(1)


@workspace.command("status")
@click.option("--check-permissions", is_flag=True, help="Check file permissions")
@click.pass_context
def workspace_status(ctx: click.Context, check_permissions: bool) -> None:
    """Show workspace status."""
    try:
        manager = WorkspaceManager(ctx.obj["config_manager"])
        status = manager.get_status(check_permissions=check_permissions)
        manager.display_status(status)
    except Exception as e:
        console.print(f"[red]Error getting workspace status: {e}[/red]")
        sys.exit(1)


@workspace.command("clean")
@click.option("--force", is_flag=True, help="Force cleanup without confirmation")
@click.pass_context
def workspace_clean(ctx: click.Context, force: bool) -> None:
    """Clean up workspace."""
    try:
        manager = WorkspaceManager(ctx.obj["config_manager"])
        manager.clean_workspace(force=force)
        console.print("[green]✓ Workspace cleaned[/green]")
    except Exception as e:
        console.print(f"[red]Error cleaning workspace: {e}[/red]")
        sys.exit(1)


@workspace.command("add-repo")
@click.argument("repo_url")
@click.option("--name", help="Repository name (default: auto-detect)")
@click.option("--depends", help="Comma-separated list of dependencies")
@click.option("--branch", default="main", help="Branch to clone")
@click.pass_context
def workspace_add_repo(
    ctx: click.Context,
    repo_url: str,
    name: Optional[str],
    depends: Optional[str],
    branch: str,
) -> None:
    """Add a repository to the workspace."""
    try:
        manager = WorkspaceManager(ctx.obj["config_manager"])
        dependencies = depends.split(",") if depends else []
        manager.add_repository(repo_url, name, dependencies, branch)
        console.print(f"[green]✓ Repository added successfully[/green]")
    except Exception as e:
        console.print(f"[red]Error adding repository: {e}[/red]")
        sys.exit(1)


@main.group()
@click.pass_context
def deps(ctx: click.Context) -> None:
    """Manage dependencies."""
    pass


@deps.command("switch")
@click.argument("mode", type=click.Choice(["local", "remote", "test"]))
@click.option("--dry-run", is_flag=True, help="Show what would be changed")
@click.pass_context
def deps_switch(ctx: click.Context, mode: str, dry_run: bool) -> None:
    """Switch between local, remote, and test dependencies.

    Modes:
    - local: Use path-based dependencies for development
    - remote: Use released packages from PyPI
    - test: Use test packages from test-PyPI
    """
    try:
        manager = DependencyManager(ctx.obj["config_manager"])

        if mode == "local":
            result = manager.switch_to_local(dry_run=dry_run)
        elif mode == "remote":
            result = manager.switch_to_remote(dry_run=dry_run)
        else:  # test
            result = manager.switch_to_test(dry_run=dry_run)

        if result:
            action = "Would switch" if dry_run else "Switched"
            console.print(f"[green]✓ {action} to {mode} dependencies[/green]")
        else:
            console.print(f"[red]Failed to switch to {mode} dependencies[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error switching dependencies: {e}[/red]")
        sys.exit(1)


@deps.command("status")
@click.option(
    "--verbose", "-v", is_flag=True, help="Show detailed dependency information"
)
@click.option(
    "--check-transitive", is_flag=True, help="Analyze transitive dependencies"
)
@click.pass_context
def deps_status(ctx: click.Context, verbose: bool, check_transitive: bool) -> None:
    """Show dependency status."""
    try:
        manager = DependencyManager(ctx.obj["config_manager"])
        status = manager.get_status()

        if check_transitive:
            # Add transitive dependency analysis
            transitive_analysis = manager.analyze_transitive_dependencies()
            status["transitive_analysis"] = transitive_analysis

        manager.display_status(
            status, verbose=verbose, show_transitive=check_transitive
        )
    except Exception as e:
        console.print(f"[red]Error getting dependency status: {e}[/red]")
        sys.exit(1)


@deps.command("update")
@click.option("--target-version", help="Target version for all packages")
@click.pass_context
def deps_update(ctx: click.Context, target_version: Optional[str]) -> None:
    """Update dependency versions."""
    try:
        manager = DependencyManager(ctx.obj["config_manager"])
        manager.update_versions(target_version=target_version)
        console.print("[green]✓ Dependencies updated[/green]")
    except Exception as e:
        console.print(f"[red]Error updating dependencies: {e}[/red]")
        sys.exit(1)


@main.group()
@click.pass_context
def release(ctx: click.Context) -> None:
    """Manage releases."""
    pass


@main.group()
@click.pass_context
def version(ctx: click.Context) -> None:
    """Manage versions and version bumps."""
    pass


@version.command("bump")
@click.argument("repository")
@click.argument("bump_type", type=click.Choice(["patch", "minor", "major"]))
@click.option(
    "--alpha", is_flag=True, help="Create alpha version (e.g., 0.1.6-alpha.1)"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be changed without making changes"
)
@click.option(
    "--update-dependents",
    is_flag=True,
    default=True,
    help="Update dependent repositories",
)
@click.option(
    "--dependents-bump",
    type=click.Choice(["patch", "minor", "major"]),
    default="patch",
    help="Bump type for dependent repositories (default: patch)",
)
@click.option(
    "--validate",
    is_flag=True,
    default=True,
    help="Run validation tests after version bump",
)
@click.pass_context
def version_bump(
    ctx: click.Context,
    repository: str,
    bump_type: str,
    alpha: bool,
    dry_run: bool,
    update_dependents: bool,
    dependents_bump: str,
    validate: bool,
) -> None:
    """Bump version for a repository and update all dependents.

    Examples:
      # Bump patch version to alpha for testing (dependents also get patch bump)
      mpr version bump buvis-pybase patch --alpha

      # Bump minor version, dependents get minor bump too
      mpr version bump buvis-pybase minor --alpha --dependents-bump minor

      # Bump major version to alpha, dependents get patch bump (default)
      mpr version bump buvis-pybase major --alpha

      # Bump minor without alpha, dependents get minor bump with alpha
      mpr version bump buvis-pybase minor --dependents-bump minor --alpha

      # Subsequent alpha bumps just increment alpha number
      mpr version bump buvis-pybase patch --alpha  # 0.1.6-alpha.2, 0.1.6-alpha.3, etc.
    """
    try:
        manager = VersionManager(ctx.obj["config_manager"])

        success = manager.bump_version(
            repository=repository,
            bump_type=bump_type,
            alpha=alpha,
            dry_run=dry_run,
            update_dependents=update_dependents,
            dependents_bump=dependents_bump,
            validate=validate,
        )

        if success:
            action = "Would bump" if dry_run else "Bumped"
            console.print(
                f"[green]✓ {action} {repository} version ({bump_type}{' alpha' if alpha else ''})[/green]"
            )
        else:
            console.print(f"[red]Failed to bump version for {repository}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error bumping version: {e}[/red]")
        sys.exit(1)


@version.command("status")
@click.option("--repository", help="Show status for specific repository only")
@click.option(
    "--show-dependents",
    is_flag=True,
    help="Show which repositories depend on each package",
)
@click.pass_context
def version_status(
    ctx: click.Context, repository: Optional[str], show_dependents: bool
) -> None:
    """Show version status for repositories."""
    try:
        manager = VersionManager(ctx.obj["config_manager"])
        status = manager.get_version_status(repository=repository)
        manager.display_version_status(status, show_dependents=show_dependents)
    except Exception as e:
        console.print(f"[red]Error getting version status: {e}[/red]")
        sys.exit(1)


@version.command("diagnose")
@click.option("--repository", help="Show diagnosis for specific repository only")
@click.pass_context
def version_diagnose(ctx: click.Context, repository: Optional[str]) -> None:
    """Diagnose version management issues and show dependency configurations."""
    try:
        manager = VersionManager(ctx.obj["config_manager"])
        config = manager.config_manager.load_config()

        console.print(f"\n[bold]Version Management Diagnosis[/bold]")

        if repository:
            repo = manager.config_manager.get_repository(repository)
            if not repo:
                console.print(f"[red]Repository '{repository}' not found[/red]")
                return
            repos_to_check = [repo]
        else:
            repos_to_check = config.repositories

        for repo in repos_to_check:
            console.print(f"\n[cyan bold]{repo.name}[/cyan bold]")
            console.print(f"  Package name: {repo.package_name}")
            console.print(f"  Path: {repo.path}")
            console.print(f"  Path exists: {'✓' if repo.path.exists() else '✗'}")

            if repo.path.exists():
                current_version = manager._get_current_version(repo)
                console.print(f"  Current version: {current_version or 'N/A'}")

                # Show pyproject.toml dependencies
                pyproject_path = repo.path / "pyproject.toml"
                if pyproject_path.exists():
                    try:
                        with open(pyproject_path, "r") as f:
                            pyproject_data = toml.load(f)

                        dependencies = (
                            pyproject_data.get("tool", {})
                            .get("poetry", {})
                            .get("dependencies", {})
                        )
                        console.print(f"  Dependencies in pyproject.toml:")

                        if dependencies:
                            for dep_name, dep_spec in dependencies.items():
                                if dep_name == "python":
                                    continue
                                console.print(f"    {dep_name}: {dep_spec}")
                        else:
                            console.print("    [dim]No dependencies found[/dim]")

                    except Exception as e:
                        console.print(f"  [red]Error reading pyproject.toml: {e}[/red]")
                else:
                    console.print(f"  [red]No pyproject.toml found[/red]")

                # Show expected dependencies based on config
                if repo.dependencies:
                    console.print(f"  Expected dependencies (from config):")
                    for dep_name in repo.dependencies:
                        dep_repo = manager.config_manager.get_repository(dep_name)
                        if dep_repo:
                            console.print(
                                f"    {dep_name} -> package: {dep_repo.package_name}"
                            )
                        else:
                            console.print(
                                f"    {dep_name} -> [red]not found in config[/red]"
                            )

                # Show who depends on this repository
                dependents = manager._get_dependent_repositories(repo.name)
                if dependents:
                    console.print(f"  Dependents:")
                    for dependent in dependents:
                        console.print(f"    {dependent.name}")
                else:
                    console.print(f"  [dim]No dependents[/dim]")
            else:
                console.print(f"  [red]Repository path does not exist[/red]")

    except Exception as e:
        console.print(f"[red]Error during diagnosis: {e}[/red]")
        sys.exit(1)


@version.command("sync")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be changed without making changes"
)
@click.option("--force", is_flag=True, help="Force sync even if there are conflicts")
@click.pass_context
def version_sync(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Synchronize dependency versions across all repositories."""
    try:
        manager = VersionManager(ctx.obj["config_manager"])

        success = manager.sync_dependency_versions(dry_run=dry_run, force=force)

        if success:
            action = "Would synchronize" if dry_run else "Synchronized"
            console.print(
                f"[green]✓ {action} dependency versions across all repositories[/green]"
            )
        else:
            console.print("[red]Failed to sync dependency versions[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error syncing versions: {e}[/red]")
        sys.exit(1)


@release.command("create")
@click.option(
    "--stage",
    type=click.Choice(["dev", "rc", "prod"]),
    required=True,
    help="Release stage",
)
@click.option(
    "--repositories",
    help="Comma-separated list of repositories to release (default: all)",
)
@click.option("--version", help="Default version for all repositories")
@click.option(
    "--repo-versions", help="JSON string mapping repository names to versions"
)
@click.option("--dry-run", is_flag=True, help="Perform dry run")
@click.option("--skip-tests", is_flag=True, help="Skip running tests")
@click.option("--force", is_flag=True, help="Continue despite failures")
@click.option("--parallel", is_flag=True, help="Process repos in parallel")
@click.pass_context
def release_create(
    ctx: click.Context,
    stage: str,
    repositories: Optional[str],
    version: Optional[str],
    repo_versions: Optional[str],
    dry_run: bool,
    skip_tests: bool,
    force: bool,
    parallel: bool,
) -> None:
    """Create a new release for specific repositories or all repositories.

    Examples:
      # Release all repositories with same version
      mpr release create --stage dev --version 1.2.0

      # Release specific repositories
      mpr release create --stage prod --repositories buvis-pybase,doogat-core

      # Release with different versions per repository
      mpr release create --stage rc --repo-versions '{"buvis-pybase": "0.2.1", "doogat-core": "0.3.0"}'
    """
    try:
        coordinator = ReleaseCoordinator(ctx.obj["config_manager"])

        # Parse repositories list
        repo_list = None
        if repositories:
            repo_list = [r.strip() for r in repositories.split(",")]

        # Parse repository versions
        repository_versions = None
        if repo_versions:
            import json

            try:
                repository_versions = json.loads(repo_versions)
            except json.JSONDecodeError:
                console.print(
                    f"[red]Invalid JSON in --repo-versions: {repo_versions}[/red]"
                )
                sys.exit(1)

        success = coordinator.create_release(
            stage=stage,
            repositories=repo_list,
            version=version,
            repository_versions=repository_versions,
            dry_run=dry_run,
            skip_tests=skip_tests,
            force=force,
            parallel=parallel,
        )

        if success:
            console.print(f"[green]✓ Release {stage} completed successfully[/green]")
        else:
            console.print(f"[red]Release {stage} failed[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error creating release: {e}[/red]")
        sys.exit(1)


@release.command("status")
@click.option("--verbose", is_flag=True, help="Show detailed status")
@click.pass_context
def release_status(ctx: click.Context, verbose: bool) -> None:
    """Show release status."""
    try:
        coordinator = ReleaseCoordinator(ctx.obj["config_manager"])
        status = coordinator.get_status(verbose=verbose)
        coordinator.display_status(status)
    except Exception as e:
        console.print(f"[red]Error getting release status: {e}[/red]")
        sys.exit(1)


@release.command("rollback")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def release_rollback(ctx: click.Context, confirm: bool) -> None:
    """Rollback a failed release."""
    try:
        coordinator = ReleaseCoordinator(ctx.obj["config_manager"])

        if not confirm:
            if not click.confirm("Are you sure you want to rollback the release?"):
                console.print("Rollback cancelled")
                return

        success = coordinator.rollback()

        if success:
            console.print("[green]✓ Release rollback completed[/green]")
        else:
            console.print("[red]Rollback failed[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error rolling back release: {e}[/red]")
        sys.exit(1)


@main.group()
@click.pass_context
def test(ctx: click.Context) -> None:
    """Run tests."""
    pass


@test.command("unit")
@click.option("--parallel", is_flag=True, help="Run tests in parallel")
@click.option("--coverage", is_flag=True, help="Generate coverage report")
@click.pass_context
def test_unit(ctx: click.Context, parallel: bool, coverage: bool) -> None:
    """Run unit tests in all repositories."""
    try:
        runner = TestRunner(ctx.obj["config_manager"])
        success = runner.run_unit_tests(parallel=parallel, coverage=coverage)

        if success:
            console.print("[green]✓ All unit tests passed[/green]")
        else:
            console.print("[red]Some unit tests failed[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error running unit tests: {e}[/red]")
        sys.exit(1)


@test.command("integration")
@click.option("--parallel", is_flag=True, help="Run tests in parallel")
@click.option(
    "--environment",
    type=click.Choice(["local", "docker"]),
    default="local",
    help="Test environment",
)
@click.option("--junit-output", is_flag=True, help="Generate JUnit XML output")
@click.pass_context
def test_integration(
    ctx: click.Context, parallel: bool, environment: str, junit_output: bool
) -> None:
    """Run integration tests."""
    try:
        runner = TestRunner(ctx.obj["config_manager"])
        success = runner.run_integration_tests(
            parallel=parallel, environment=environment, junit_output=junit_output
        )

        if success:
            console.print("[green]✓ All integration tests passed[/green]")
        else:
            console.print("[red]Some integration tests failed[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error running integration tests: {e}[/red]")
        sys.exit(1)


@test.command("all")
@click.option("--parallel", is_flag=True, help="Run tests in parallel")
@click.option("--coverage", is_flag=True, help="Generate coverage report")
@click.pass_context
def test_all(ctx: click.Context, parallel: bool, coverage: bool) -> None:
    """Run all tests."""
    try:
        runner = TestRunner(ctx.obj["config_manager"])

        # Run unit tests first
        unit_success = runner.run_unit_tests(parallel=parallel, coverage=coverage)

        if not unit_success:
            console.print("[red]Unit tests failed, skipping integration tests[/red]")
            sys.exit(1)

        # Run integration tests
        integration_success = runner.run_integration_tests(parallel=parallel)

        if unit_success and integration_success:
            console.print("[green]✓ All tests passed[/green]")
        else:
            console.print("[red]Some tests failed[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error running tests: {e}[/red]")
        sys.exit(1)


@main.group()
@click.pass_context
def hooks(ctx: click.Context) -> None:
    """Manage Git hooks."""
    pass


@hooks.command("install")
@click.option("--force", is_flag=True, help="Overwrite existing hooks")
@click.pass_context
def hooks_install(ctx: click.Context, force: bool) -> None:
    """Install Git hooks in all repositories."""
    try:
        manager = GitHooksManager(ctx.obj["config_manager"])
        manager.install_hooks(force=force)
        console.print("[green]✓ Git hooks installed[/green]")
    except Exception as e:
        console.print(f"[red]Error installing Git hooks: {e}[/red]")
        sys.exit(1)


@hooks.command("test")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.pass_context
def hooks_test(ctx: click.Context, verbose: bool) -> None:
    """Test Git hooks functionality."""
    try:
        manager = GitHooksManager(ctx.obj["config_manager"])
        success = manager.test_hooks(verbose=verbose)

        if success:
            console.print("[green]✓ All Git hooks working correctly[/green]")
        else:
            console.print("[red]Some Git hooks failed tests[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error testing Git hooks: {e}[/red]")
        sys.exit(1)


@hooks.command("uninstall")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def hooks_uninstall(ctx: click.Context, confirm: bool) -> None:
    """Uninstall Git hooks from all repositories."""
    try:
        if not confirm:
            if not click.confirm("Are you sure you want to uninstall Git hooks?"):
                console.print("Uninstall cancelled")
                return

        manager = GitHooksManager(ctx.obj["config_manager"])
        manager.uninstall_hooks()
        console.print("[green]✓ Git hooks uninstalled[/green]")
    except Exception as e:
        console.print(f"[red]Error uninstalling Git hooks: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
