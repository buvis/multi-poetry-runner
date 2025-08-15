# Multi-Poetry Runner (MPR)

A comprehensive toolset for managing multi-repository Python projects with interdependent packages using Poetry. MPR supports modern development workflows with feature branches, coordinated dependency management, and automated testing across multiple repositories.

## Key Features

- **Workspace Management**: Set up and manage development workspaces across multiple repositories
- **Three-Stage Dependency Management**: Switch between local, test-PyPI, and production dependencies
- **Branch-Based Development**: Support for feature branches with proper integration testing
- **Version Management**: Automated version bumping and dependency synchronization
- **Release Coordination**: Coordinate releases across multiple repositories (publishing via GitHub Actions)
- **Integration Testing**: Run tests across all packages at different stages
- **Git Hooks**: Prevent accidental commits of local development configurations

## Installation

```bash
# From PyPI (when available)
pip install multi-poetry-runner

# From Source
git clone https://github.com/your-org/multi-poetry-runner.git
cd multi-poetry-runner
poetry install

# Development Installation
poetry install --with dev,test
```

## Quick Start

### 1. Initialize Workspace

```bash
mkdir my-workspace && cd my-workspace
mpr workspace init my-workspace --python-version 3.11
```

Creates structure:
```
my-workspace/
├── mpr-config.yaml       # Main configuration
├── Makefile             # Convenient shortcuts
├── repos/               # Repository directory
├── logs/                # Log files
└── tests/               # Integration tests
```

### 2. Add Repositories with Dependencies

```bash
# Base library (no dependencies)
mpr workspace add-repo git@github.com:buvis/buvis-pybase.git

# Core library (depends on buvis-pybase)
mpr workspace add-repo git@github.com:doogat/doogat-core.git --depends buvis-pybase

# Integrations (depends on both)
mpr workspace add-repo git@github.com:doogat/doogat-integrations.git --depends buvis-pybase,doogat-core

# Scripts (depends on all)
mpr workspace add-repo git@github.com:buvis/scripts.git --depends buvis-pybase,doogat-core,doogat-integrations
```

### 3. Set Up Environment

```bash
mpr workspace setup  # Clones repos, sets up Poetry envs, installs dependencies and git hooks
mpr workspace status # Check everything is ready
```

## Core Workflows

### Three-Stage Dependency Management

MPR supports three dependency modes for different development phases:

| Stage | Command | Purpose | Dependencies |
|-------|---------|---------|--------------|
| **Local** | `mpr deps switch local` | Active development | Path-based (`../package`) |
| **Test** | `mpr deps switch test` | Integration testing | Test-PyPI packages |
| **Remote** | `mpr deps switch remote` | Production ready | PyPI packages |

### Complete Feature Development Workflow

#### 1. Start Feature Development

```bash
# Create feature branches
cd repos/buvis-pybase && git checkout -b feature/new-api
cd ../doogat-core && git checkout -b feature/new-api

# Switch to local mode for cross-repo development
cd ../../
mpr deps switch local

# Develop and test continuously
mpr test unit
mpr test integration
```

#### 2. Prepare for Integration Testing

```bash
# Switch to remote dependencies for clean commits
mpr deps switch remote

# Commit changes in each repository
cd repos/buvis-pybase
git add . && git commit -m "feat: add new API endpoints"
git push origin feature/new-api

# Repeat for other repos...
```

#### 3. Version Management

```bash
# Check current versions
mpr version status

# Bump versions with control over dependents
mpr version bump buvis-pybase patch --alpha  # Default: dependents get patch bump
mpr version bump buvis-pybase minor --alpha --dependents-bump minor  # All get minor
mpr version bump buvis-pybase major --alpha --dependents-bump major  # All get major

# What happens automatically:
# - Updates target repository version
# - Updates all dependent repositories to use new version
# - Updates Poetry lock files
# - Runs validation tests
```

#### 4. Testing & Release

```bash
# Test with updated versions
mpr test integration --environment docker
mpr test all --parallel

# Create release branches
cd repos/buvis-pybase
git checkout -b release/v0.1.6-alpha.1
git push origin release/v0.1.6-alpha.1

# After PR approval and merge
mpr release create --stage prod --repo-versions '{
  "buvis-pybase": "0.1.6",
  "doogat-core": "0.3.0",
  "doogat-integrations": "0.2.1"
}'

# Push tags to trigger GitHub Actions publishing
cd repos/buvis-pybase
git push origin --tags
```

## Command Reference

### Essential Commands

| Category | Command | Description |
|----------|---------|-------------|
| **Workspace** | `mpr workspace init <name>` | Initialize new workspace |
| | `mpr workspace setup` | Set up repositories and environments |
| | `mpr workspace status` | Show workspace status |
| | `mpr workspace add-repo <url>` | Add repository to workspace |
| **Dependencies** | `mpr deps switch <local\|test\|remote>` | Switch dependency mode |
| | `mpr deps status` | Show dependency status |
| | `mpr deps update` | Update dependency versions |
| **Versions** | `mpr version bump <repo> <type>` | Bump version (patch/minor/major) |
| | `mpr version bump <repo> <type> --alpha` | Create alpha version |
| | `mpr version bump <repo> <type> --dependents-bump <type>` | Control dependent bumps |
| | `mpr version status` | Show version status |
| **Testing** | `mpr test unit` | Run unit tests |
| | `mpr test integration` | Run integration tests |
| | `mpr test all` | Run all tests |
| **Releases** | `mpr release create --stage <dev\|rc\|prod>` | Create release |
| | `mpr release status` | Show release status |
| **Git Hooks** | `mpr hooks install` | Install git hooks |
| | `mpr hooks test` | Test hooks functionality |

### Makefile Shortcuts

```bash
make dev      # Switch to local development
make remote   # Switch to remote dependencies
make test     # Run all tests
make status   # Show status
make clean    # Clean workspace
```

## Configuration

Example `mpr-config.yaml`:

```yaml
version: "1.0"
workspace:
  name: "my-workspace"
  python_version: "3.11"

repositories:
  - name: "buvis-pybase"
    url: "https://github.com/buvis/buvis-pybase.git"
    package_name: "buvis-pybase"
    branch: "main"
    dependencies: []
    source: "test-pypi"

  - name: "doogat-core"
    url: "https://github.com/doogat/doogat-core.git"
    package_name: "doogat-core"
    branch: "main"
    dependencies: ["buvis-pybase"]
    source: "test-pypi"

settings:
  auto_install_hooks: true
  use_test_pypi: true
  parallel_jobs: 4
  
  poetry:
    virtualenvs_in_project: true
    virtualenvs_create: true
  
  testing:
    unit_test_timeout: 300
    integration_test_timeout: 1800
    coverage_threshold: 80
  
  releases:
    auto_tag: true
    auto_push_tags: false
    changelog_generation: true
```

## Advanced Scenarios

### Version Bumping Examples

```bash
# Basic bumping (dependents get patch by default)
mpr version bump buvis-pybase minor --alpha
# Result: buvis-pybase 0.1.5 → 0.2.0-alpha.1
#         dependents: patch bump + alpha

# Coordinated minor release
mpr version bump buvis-pybase minor --alpha --dependents-bump minor
# Result: All repositories get minor + alpha

# Breaking changes
mpr version bump buvis-pybase major --alpha --dependents-bump major
# Result: All repositories get major + alpha

# Mixed impact
mpr version bump buvis-pybase patch --alpha --dependents-bump minor
# Result: Base gets patch, dependents get minor (all with alpha)

# Iterative alpha testing
mpr version bump buvis-pybase patch --alpha  # → 0.1.6-alpha.1
mpr version bump buvis-pybase patch --alpha  # → 0.1.6-alpha.2
```

### Release Management Examples

```bash
# Release all with same version
mpr release create --stage prod --version 1.2.0

# Release specific repositories
mpr release create --stage dev --repositories buvis-pybase,doogat-core --version 0.3.0

# Different versions per repository
mpr release create --stage rc --repo-versions '{
  "buvis-pybase": "0.2.1",
  "doogat-core": "0.4.0",
  "doogat-integrations": "0.3.2"
}'

# Emergency hotfix
cd repos/buvis-pybase && git checkout -b hotfix/critical-fix
# Make fixes...
mpr deps switch remote
mpr version bump buvis-pybase patch  # No alpha for hotfixes
mpr test integration
mpr release create --stage prod --repositories buvis-pybase --version 0.1.7
```

## Publishing via GitHub Actions

MPR handles version management while GitHub Actions handles publishing for security and automation.

### Recommended GitHub Actions Workflow

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  release:
    types: [published]
  push:
    tags:
      - "v*"

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Install Poetry
        uses: snok/install-poetry@v1
      - name: Install dependencies
        run: poetry install
      - name: Run tests
        run: poetry run pytest
      - name: Build package
        run: poetry build
      - name: Publish to PyPI
        env:
          POETRY_PYPI_TOKEN_PYPI: ${{ secrets.PYPI_TOKEN }}
        run: poetry publish
```

### Integration Workflow

1. **MPR**: Version bumping, dependency coordination, tagging, testing
2. **GitHub Actions**: Building packages, publishing to PyPI

```bash
# Develop and test
mpr deps switch local
# Make changes...

# Prepare release
mpr deps switch remote
mpr version bump buvis-pybase patch --alpha
mpr test all

# Create release and push tags
mpr release create --stage prod --repositories buvis-pybase --version 0.1.6
cd repos/buvis-pybase
git push origin --tags  # Triggers GitHub Actions
```

## Best Practices

### Development Workflow

1. **Always check status before starting**: `mpr workspace status && mpr version status`
2. **Use feature branches**: `git checkout -b feature/new-functionality`
3. **Test locally before version bumps**: `mpr deps switch local && mpr test all`
4. **Switch to remote before committing**: `mpr deps switch remote`
5. **Use alpha versions for testing**: `mpr version bump repo patch --alpha`
6. **Create meaningful commits**: Use conventional commit format (feat:, fix:, breaking:)

### Version Management

- **Patch** (`0.1.5` → `0.1.6`): Bug fixes, no API changes
- **Minor** (`0.1.5` → `0.2.0`): New features, backward compatible
- **Major** (`0.1.5` → `1.0.0`): Breaking changes

### CI/CD Integration

```yaml
# Example GitHub Actions workflow for feature branches
name: Feature Testing
on:
  push:
    branches: [feature/*]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup MPR
        run: |
          pip install multi-poetry-runner
          mpr workspace setup --ci-mode
      - name: Test with local dependencies
        run: |
          mpr deps switch local
          mpr test unit --parallel
      - name: Integration testing
        run: |
          mpr release create --stage dev --version dev-${{ github.sha }}
          mpr test integration --junit-output
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Permission denied | `chmod -R u+w repos/` |
| Git hooks preventing commits | `mpr deps switch remote` before committing |
| Tests failing | `mpr test unit --verbose` or test individual repos |
| Release failures | `mpr release status --verbose` and check logs |

### Getting Help

- `mpr --help` - General help
- `mpr <command> --help` - Command-specific help
- `mpr --verbose <command>` - Verbose output
- Check logs in `logs/mpr.log` or `~/.mpr/logs/mpr.log`

## Migration from Manual Process

```bash
# Set up MPR workspace
mpr workspace init my-workspace

# Add existing repositories
mpr workspace add-repo <your-repo-urls>

# Import existing repos
mv existing-repo repos/
mpr workspace setup

# Verify
mpr workspace status
mpr test all
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `poetry run pytest`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
