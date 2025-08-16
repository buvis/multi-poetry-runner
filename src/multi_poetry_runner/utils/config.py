"""Configuration management utilities."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RepositoryConfig:
    """Configuration for a repository."""

    name: str
    url: str
    package_name: str
    path: Path
    branch: str = "main"
    dependencies: list[str] = field(default_factory=list)
    source: str = "pypi"  # pypi, test-pypi, local


@dataclass
class WorkspaceConfig:
    """Workspace configuration."""

    name: str
    python_version: str = "3.11"
    repositories: list[RepositoryConfig] = field(default_factory=list)


class ConfigManager:
    """Manages MPR configuration files."""

    def __init__(
        self, config_file: Path | None = None, workspace_root: Path | None = None
    ):
        self.workspace_root = workspace_root or Path.cwd()
        self.config_file = config_file or self.workspace_root / "mpr-config.yaml"
        self._config: WorkspaceConfig | None = None

    def load_config(self) -> WorkspaceConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")

        with open(self.config_file) as f:
            data = yaml.safe_load(f)

        # Parse repositories
        repositories = []
        for repo_data in data.get("repositories", []):
            repo = RepositoryConfig(
                name=repo_data["name"],
                url=repo_data["url"],
                package_name=repo_data["package_name"],
                path=self.workspace_root / "repos" / repo_data["name"],
                branch=repo_data.get("branch", "main"),
                dependencies=repo_data.get("dependencies", []),
                source=repo_data.get("source", "pypi"),
            )
            repositories.append(repo)

        self._config = WorkspaceConfig(
            name=data["workspace"]["name"],
            python_version=data["workspace"].get("python_version", "3.11"),
            repositories=repositories,
        )

        return self._config

    def save_config(self, config: WorkspaceConfig) -> None:
        """Save configuration to file."""
        data: dict[str, Any] = {
            "version": "1.0",
            "workspace": {"name": config.name, "python_version": config.python_version},
            "repositories": [],
        }

        for repo in config.repositories:
            repo_data = {
                "name": repo.name,
                "url": repo.url,
                "package_name": repo.package_name,
                "branch": repo.branch,
                "dependencies": repo.dependencies,
                "source": repo.source,
            }
            data["repositories"].append(repo_data)

        # Ensure directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        self._config = config

    def get_repository(self, name: str) -> RepositoryConfig | None:
        """Get repository configuration by name."""
        config = self.load_config()
        for repo in config.repositories:
            if repo.name == name:
                return repo
        return None

    def add_repository(self, repo: RepositoryConfig) -> None:
        """Add a repository to the configuration."""
        config = self.load_config()

        # Check if repository already exists
        for existing_repo in config.repositories:
            if existing_repo.name == repo.name:
                raise ValueError(f"Repository {repo.name} already exists")

        config.repositories.append(repo)
        self.save_config(config)

    def get_dependency_order(self) -> list[str]:
        """Get repositories in dependency order (topological sort)."""
        config = self.load_config()

        # Build dependency graph
        graph: dict[str, list[str]] = {}
        for repo in config.repositories:
            graph[repo.name] = repo.dependencies

        # Topological sort
        visited = set()
        temp_visited = set()
        result = []

        def visit(node: str) -> None:
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving {node}")
            if node in visited:
                return

            temp_visited.add(node)

            for dep in graph.get(node, []):
                visit(dep)

            temp_visited.remove(node)
            visited.add(node)
            result.append(node)

        for repo_name in graph:
            visit(repo_name)

        return result

    @property
    def workspace_root(self) -> Path:
        """Get workspace root directory."""
        return self._workspace_root

    @workspace_root.setter
    def workspace_root(self, value: Path) -> None:
        """Set workspace root directory."""
        self._workspace_root = value.resolve()

    def get_repos_path(self) -> Path:
        """Get path to repositories directory."""
        return self.workspace_root / "repos"

    def get_logs_path(self) -> Path:
        """Get path to logs directory."""
        return self.workspace_root / "logs"

    def get_backups_path(self) -> Path:
        """Get path to backups directory."""
        return self.workspace_root / "backups"

    def get_config_template(self) -> dict[str, Any]:
        """Get a template configuration."""
        return {
            "version": "1.0",
            "workspace": {"name": "my-workspace", "python_version": "3.11"},
            "repositories": [
                {
                    "name": "buvis-pybase",
                    "url": "https://github.com/buvis/buvis-pybase.git",
                    "package_name": "buvis-pybase",
                    "branch": "main",
                    "dependencies": [],
                    "source": "pypi",
                },
                {
                    "name": "doogat-core",
                    "url": "https://github.com/doogat/doogat-core.git",
                    "package_name": "doogat-core",
                    "branch": "main",
                    "dependencies": ["buvis-pybase"],
                    "source": "test-pypi",
                },
            ],
            "settings": {
                "auto_install_hooks": True,
                "use_test_pypi": True,
                "parallel_jobs": 4,
                "timeout": 3600,
            },
        }
