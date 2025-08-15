# Changelog

All notable changes to Multi-Poetry Runner (MPR) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - Development

### In Progress
- Initial development of Multi-Poetry Runner
- Core functionality implementation
- Documentation and project structure setup

### Planned Features
- Workspace management functionality
  - Initialize new workspaces
  - Add repositories with dependency tracking
  - Setup development environments automatically
- Three-stage dependency management
  - Local development with path-based dependencies
  - Test environment with test-PyPI packages
  - Production with PyPI packages
- Version management system
  - Automated version bumping
  - Alpha version support for testing
  - Dependent repository updates
  - Configurable bump types for dependents
- Release coordination
  - Development, RC, and production stages
  - Multi-repository release support
  - Rollback capabilities
- Testing infrastructure
  - Unit test runner
  - Integration test support
  - Coverage reporting
  - Parallel test execution
- Git hooks management
  - Prevent commits with local dependencies
  - Automatic installation in repositories
- Rich CLI interface
  - Organized command groups
  - Detailed status displays
  - Progress indicators
  - Colored output

### Project Setup
- Created initial project structure
- Added comprehensive .gitignore
- Set up pyproject.toml with dependencies
- Created pre-commit configuration
- Added contribution guidelines
- Prepared installation script (for future use)
- Drafted comprehensive README documentation

### Target Dependencies
- Python ^3.11
- Poetry for package management
- Click for CLI
- Rich for terminal UI
- GitPython for repository management
- PyYAML for configuration
- Toml for pyproject.toml parsing
- Jinja2 for templates
- Docker SDK for container support
- Pytest for testing

---

*Note: This project is currently in initial development. No releases have been made yet.*
