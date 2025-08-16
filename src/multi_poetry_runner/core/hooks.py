"""Git hooks management functionality."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from ..utils.config import ConfigManager, RepositoryConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class GitHooksManager:
    """Manages Git hooks across repositories."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.workspace_root = config_manager.workspace_root

    def install_hooks(self, force: bool = False) -> None:
        """Install Git hooks in all repositories."""
        config = self.config_manager.load_config()

        console.print("\n[bold]Installing Git hooks...[/bold]")

        # Create hooks directory in workspace
        hooks_dir = self.workspace_root / "hooks"
        hooks_dir.mkdir(exist_ok=True)

        # Generate hook templates
        self._create_hook_templates(hooks_dir)

        # Install hooks in each repository
        for repo in config.repositories:
            if repo.path.exists():
                self._install_repo_hooks(repo, hooks_dir, force)

        console.print("[green]✓ Git hooks installed successfully[/green]")

    def _create_hook_templates(self, hooks_dir: Path) -> None:
        """Create Git hook templates."""

        # Pre-commit hook template
        pre_commit_hook = self._get_pre_commit_hook_template()
        (hooks_dir / "pre-commit").write_text(pre_commit_hook)
        (hooks_dir / "pre-commit").chmod(0o755)

        # Pre-push hook template (optional)
        pre_push_hook = self._get_pre_push_hook_template()
        (hooks_dir / "pre-push").write_text(pre_push_hook)
        (hooks_dir / "pre-push").chmod(0o755)

        logger.info(f"Created hook templates in {hooks_dir}")

    def _install_repo_hooks(
        self, repo: RepositoryConfig, hooks_dir: Path, force: bool = False
    ) -> None:
        """Install hooks in a single repository."""

        git_hooks_dir = repo.path / ".git" / "hooks"
        if not git_hooks_dir.exists():
            logger.warning(f"No .git/hooks directory in {repo.name}")
            return

        # Install pre-commit hook
        self._install_single_hook(repo, hooks_dir, "pre-commit", force)

        # Install pre-push hook if it exists
        if (hooks_dir / "pre-push").exists():
            self._install_single_hook(repo, hooks_dir, "pre-push", force)

        logger.info(f"Installed hooks in {repo.name}")

    def _install_single_hook(
        self,
        repo: RepositoryConfig,
        hooks_dir: Path,
        hook_name: str,
        force: bool = False,
    ) -> None:
        """Install a single hook in a repository."""

        source_hook = hooks_dir / hook_name
        target_hook = repo.path / ".git" / "hooks" / hook_name

        # Backup existing hook
        if target_hook.exists() and not force:
            backup_path = target_hook.with_suffix(".backup")
            if not backup_path.exists():
                shutil.copy2(target_hook, backup_path)
                logger.info(f"Backed up existing {hook_name} hook in {repo.name}")

        # Copy new hook
        shutil.copy2(source_hook, target_hook)
        target_hook.chmod(0o755)

    def _get_pre_commit_hook_template(self) -> str:
        """Get pre-commit hook template."""
        return """#!/bin/bash
# Pre-commit hook for MPR managed repositories
# This hook prevents committing local path dependencies

set -euo pipefail

# Configuration
HOOK_VERSION="1.0.0"
WORKSPACE_ROOT="$(git rev-parse --show-toplevel)"
PYPROJECT_FILE="pyproject.toml"

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

# Functions
print_error() {
    echo -e "${RED}ERROR:${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}WARNING:${NC} $1" >&2
}

print_info() {
    echo -e "${GREEN}INFO:${NC} $1"
}

# Check if we should skip the hook
if [ "${SKIP_MPR_HOOKS:-}" = "1" ]; then
    print_warning "Skipping MPR hooks (SKIP_MPR_HOOKS=1)"
    exit 0
fi

# Check if pyproject.toml is being committed
if ! git diff --cached --name-only | grep -q "^${PYPROJECT_FILE}$"; then
    exit 0
fi

print_info "Validating pyproject.toml..."

# Get staged content
staged_content=$(git show ":${PYPROJECT_FILE}" 2>/dev/null || cat "${PYPROJECT_FILE}")

# Check for local path dependencies
if echo "$staged_content" | grep -q 'path = '; then
    print_error "Local path dependencies detected in pyproject.toml"
    echo ""
    echo "Found the following path dependencies:"
    echo "$staged_content" | grep 'path = ' | while IFS= read -r line; do
        echo "  $line"
    done
    echo ""
    echo "Please run 'mpr deps switch remote' before committing"
    exit 1
fi

# Check for editable installs
if echo "$staged_content" | grep -q 'develop = true'; then
    print_error "Editable installs (develop = true) detected in pyproject.toml"
    echo ""
    echo "Please run 'mpr deps switch remote' before committing"
    exit 1
fi

# Check for absolute paths
if echo "$staged_content" | grep -E '"/home/|"/Users/|"C:\\\\|"/opt/|"/var/'; then
    print_error "Absolute paths detected in pyproject.toml"
    echo ""
    echo "Use relative paths or environment variables instead"
    exit 1
fi

# Check for dependency mode marker
if [ -f "$WORKSPACE_ROOT/.dependency-mode" ]; then
    mode=$(head -n1 "$WORKSPACE_ROOT/.dependency-mode")
    if [ "$mode" = "local" ]; then
        print_error "Repository is in local dependency mode"
        echo ""
        echo "Please run 'mpr deps switch remote' before committing"
        exit 1
    fi
fi

print_info "✓ pyproject.toml validation passed"
exit 0
"""

    def _get_pre_push_hook_template(self) -> str:
        """Get pre-push hook template."""
        return """#!/bin/bash
# Pre-push hook for MPR managed repositories
# Additional validation before pushing

set -euo pipefail

# Check if we should skip the hook
if [ "${SKIP_MPR_HOOKS:-}" = "1" ]; then
    echo "Skipping MPR hooks (SKIP_MPR_HOOKS=1)"
    exit 0
fi

# Validate that we're not in local dependency mode
WORKSPACE_ROOT="$(git rev-parse --show-toplevel)"
if [ -f "$WORKSPACE_ROOT/.dependency-mode" ]; then
    mode=$(head -n1 "$WORKSPACE_ROOT/.dependency-mode")
    if [ "$mode" = "local" ]; then
        echo "ERROR: Cannot push while in local dependency mode"
        echo "Please run 'mpr deps switch remote' first"
        exit 1
    fi
fi

# Additional checks can be added here
exit 0
"""

    def uninstall_hooks(self) -> None:
        """Uninstall Git hooks from all repositories."""
        config = self.config_manager.load_config()

        console.print("\n[bold]Uninstalling Git hooks...[/bold]")

        for repo in config.repositories:
            if repo.path.exists():
                self._uninstall_repo_hooks(repo)

        console.print("[green]✓ Git hooks uninstalled[/green]")

    def _uninstall_repo_hooks(self, repo: RepositoryConfig) -> None:
        """Uninstall hooks from a single repository."""

        git_hooks_dir = repo.path / ".git" / "hooks"
        if not git_hooks_dir.exists():
            return

        # Remove MPR hooks
        hooks_to_remove = ["pre-commit", "pre-push"]

        for hook_name in hooks_to_remove:
            hook_path = git_hooks_dir / hook_name
            backup_path = hook_path.with_suffix(".backup")

            # Remove MPR hook
            if hook_path.exists():
                hook_path.unlink()

            # Restore backup if it exists
            if backup_path.exists():
                shutil.move(backup_path, hook_path)
                logger.info(f"Restored backup {hook_name} hook in {repo.name}")

        logger.info(f"Uninstalled hooks from {repo.name}")

    def test_hooks(self, verbose: bool = False) -> bool:
        """Test Git hooks functionality."""
        config = self.config_manager.load_config()

        console.print("\n[bold]Testing Git hooks...[/bold]")

        all_passed = True
        test_results = {}

        for repo in config.repositories:
            if repo.path.exists():
                result = self._test_repo_hooks(repo, verbose)
                test_results[repo.name] = result
                if not result["success"]:
                    all_passed = False

        # Display results
        self._display_hook_test_results(test_results)

        return all_passed

    def _test_repo_hooks(
        self, repo: RepositoryConfig, verbose: bool = False
    ) -> dict[str, Any]:
        """Test hooks in a single repository."""

        result = {"success": True, "tests": [], "errors": []}

        git_hooks_dir = repo.path / ".git" / "hooks"
        if not git_hooks_dir.exists():
            result["success"] = False
            result["errors"].append("No .git/hooks directory")
            return result

        # Test pre-commit hook exists and is executable
        pre_commit_hook = git_hooks_dir / "pre-commit"
        if pre_commit_hook.exists():
            if pre_commit_hook.stat().st_mode & 0o111:  # Check if executable
                result["tests"].append("pre-commit hook exists and is executable")

                # Test hook functionality with a dummy test
                test_success = self._test_pre_commit_hook(repo, verbose)
                if test_success:
                    result["tests"].append("pre-commit hook validation works")
                else:
                    result["success"] = False
                    result["errors"].append("pre-commit hook validation failed")
            else:
                result["success"] = False
                result["errors"].append("pre-commit hook is not executable")
        else:
            result["success"] = False
            result["errors"].append("pre-commit hook not found")

        return result

    def _test_pre_commit_hook(
        self, repo: RepositoryConfig, verbose: bool = False
    ) -> bool:
        """Test pre-commit hook functionality."""

        # Create a test scenario - temporarily add a path dependency
        pyproject_path = repo.path / "pyproject.toml"
        if not pyproject_path.exists():
            return True  # No pyproject.toml to test

        # Read original content
        original_content = pyproject_path.read_text()

        try:
            # Add a dummy path dependency
            test_content = (
                original_content
                + '\\n[tool.poetry.dependencies.test-package]\\npath = "../test"\\n'
            )
            pyproject_path.write_text(test_content)

            # Stage the file
            subprocess.run(
                ["git", "add", "pyproject.toml"],
                cwd=repo.path,
                check=True,
                capture_output=True,
            )

            # Try to run pre-commit hook
            hook_path = repo.path / ".git" / "hooks" / "pre-commit"
            result = subprocess.run(
                [str(hook_path)], cwd=repo.path, capture_output=True, text=True
            )

            # Hook should fail (return non-zero) because of path dependency
            success = result.returncode != 0

            if verbose and not success:
                logger.warning(f"Pre-commit hook test output: {result.stdout}")
                logger.warning(f"Pre-commit hook test error: {result.stderr}")

            return success

        except Exception as e:
            if verbose:
                logger.error(f"Error testing pre-commit hook: {e}")
            return False
        finally:
            # Restore original content
            pyproject_path.write_text(original_content)

            # Unstage the file
            subprocess.run(
                ["git", "reset", "HEAD", "pyproject.toml"],
                cwd=repo.path,
                capture_output=True,
            )

    def _display_hook_test_results(
        self, test_results: dict[str, dict[str, Any]]
    ) -> None:
        """Display hook test results."""

        table = Table(title="Git Hook Test Results")
        table.add_column("Repository", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Tests Passed", style="blue")
        table.add_column("Errors", style="red")

        for repo_name, result in test_results.items():
            status_icon = "✓" if result["success"] else "✗"
            status_color = "green" if result["success"] else "red"

            tests_passed = len(result["tests"])
            errors_count = len(result["errors"])

            table.add_row(
                repo_name,
                f"[{status_color}]{status_icon}[/{status_color}]",
                str(tests_passed),
                str(errors_count) if errors_count > 0 else "",
            )

        console.print(table)

        # Show detailed errors if any
        for repo_name, result in test_results.items():
            if result["errors"]:
                console.print(f"\\n[red]Errors in {repo_name}:[/red]")
                for error in result["errors"]:
                    console.print(f"  - {error}")

    def get_hook_status(self) -> dict[str, Any]:
        """Get status of Git hooks across repositories."""
        config = self.config_manager.load_config()

        status = {"workspace": config.name, "repositories": []}

        for repo in config.repositories:
            repo_status = {
                "name": repo.name,
                "path": str(repo.path),
                "hooks_installed": False,
                "hooks": {},
            }

            if repo.path.exists():
                git_hooks_dir = repo.path / ".git" / "hooks"
                if git_hooks_dir.exists():
                    # Check each hook
                    for hook_name in ["pre-commit", "pre-push"]:
                        hook_path = git_hooks_dir / hook_name
                        repo_status["hooks"][hook_name] = {
                            "exists": hook_path.exists(),
                            "executable": hook_path.exists()
                            and bool(hook_path.stat().st_mode & 0o111),
                            "is_mpr_hook": self._is_mpr_hook(hook_path),
                        }

                    # Determine if hooks are installed
                    repo_status["hooks_installed"] = any(
                        hook_info["exists"] and hook_info["is_mpr_hook"]
                        for hook_info in repo_status["hooks"].values()
                    )

            status["repositories"].append(repo_status)

        return status

    def _is_mpr_hook(self, hook_path: Path) -> bool:
        """Check if a hook is a MPR-managed hook."""
        if not hook_path.exists():
            return False

        try:
            content = hook_path.read_text()
            return "MPR managed repositories" in content or "SKIP_MPR_HOOKS" in content
        except Exception:
            return False

    def display_hook_status(self, status: dict[str, Any]) -> None:
        """Display Git hook status."""

        console.print(
            f"\\n[bold]Git Hook Status for workspace: {status['workspace']}[/bold]"
        )

        table = Table(title="Repository Hook Status")
        table.add_column("Repository", style="cyan")
        table.add_column("Hooks Installed", style="green")
        table.add_column("Pre-commit", style="yellow")
        table.add_column("Pre-push", style="blue")

        for repo in status["repositories"]:
            hooks_installed = "✓" if repo["hooks_installed"] else "✗"

            pre_commit_status = self._format_hook_status(
                repo["hooks"].get("pre-commit", {})
            )
            pre_push_status = self._format_hook_status(
                repo["hooks"].get("pre-push", {})
            )

            table.add_row(
                repo["name"], hooks_installed, pre_commit_status, pre_push_status
            )

        console.print(table)

    def _format_hook_status(self, hook_info: dict[str, bool]) -> str:
        """Format hook status for display."""
        if not hook_info.get("exists", False):
            return "Not found"
        elif not hook_info.get("executable", False):
            return "Not executable"
        elif not hook_info.get("is_mpr_hook", False):
            return "Not MPR hook"
        else:
            return "✓ Installed"
