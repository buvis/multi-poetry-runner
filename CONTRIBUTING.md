# Contributing to Multi-Poetry Runner

Thank you for your interest in contributing to Multi-Poetry Runner (MPR)! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

By participating in this project, you agree to abide by our code of conduct:

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Accept feedback gracefully
- Prioritize the project's best interests

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a new branch for your feature or bugfix
4. Make your changes
5. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Poetry for dependency management
- Git

### Installation

1. Clone your fork:
```bash
git clone https://github.com/YOUR-USERNAME/multi-poetry-runner.git
cd multi-poetry-runner
```

2. Install Poetry if you haven't already:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

3. Install dependencies:
```bash
poetry install --with dev,test
```

4. Activate the virtual environment:
```bash
poetry shell
```

5. Install pre-commit hooks:
```bash
pre-commit install
```

## How to Contribute

### Types of Contributions

- **Bug Fixes**: Fix reported issues
- **Features**: Implement new functionality
- **Documentation**: Improve or add documentation
- **Tests**: Add missing tests or improve existing ones
- **Performance**: Optimize code performance
- **Refactoring**: Improve code structure and readability

### Finding Issues to Work On

- Check the [Issues](https://github.com/buvis/multi-poetry-runner/issues) page
- Look for issues labeled `good first issue` for beginners
- Issues labeled `help wanted` need assistance
- Feel free to create new issues for bugs or feature requests

## Coding Standards

### Code Style

We use the following tools to maintain code quality:

- **Black** for code formatting
- **Ruff** for linting
- **mypy** for type checking

Run all checks:
```bash
# Format code
poetry run black .

# Check linting
poetry run ruff check .

# Fix linting issues
poetry run ruff check --fix .

# Type checking
poetry run mypy .
```

### Code Guidelines

1. **Type Hints**: All functions should have type hints
```python
def process_data(input_data: str, validate: bool = True) -> dict[str, Any]:
    """Process input data and return results."""
    ...
```

2. **Docstrings**: Use Google-style docstrings
```python
def example_function(param1: str, param2: int) -> bool:
    """Brief description of function.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When input is invalid
    """
    ...
```

3. **Error Handling**: Use specific exception types
```python
# Good
try:
    result = process_data(data)
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise

# Bad
try:
    result = process_data(data)
except:
    pass
```

4. **Logging**: Use the project's logger
```python
from multi_poetry_runner.utils.logger import get_logger

logger = get_logger(__name__)

def my_function():
    logger.info("Starting process")
    logger.debug(f"Processing with params: {params}")
    logger.error("An error occurred", exc_info=True)
```

## Testing

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=multi_poetry_runner --cov-report=html

# Run specific test file
poetry run pytest tests/test_workspace.py

# Run with verbose output
poetry run pytest -v

# Run specific test
poetry run pytest tests/test_workspace.py::test_initialize_workspace
```

### Writing Tests

1. Place tests in the `tests/` directory
2. Name test files with `test_` prefix
3. Use descriptive test names
4. Include both positive and negative test cases
5. Mock external dependencies

Example test:
```python
import pytest
from unittest.mock import Mock, patch

from multi_poetry_runner.core.workspace import WorkspaceManager

def test_workspace_initialization(tmp_path):
    """Test workspace initialization creates required directories."""
    config_manager = Mock()
    config_manager.workspace_root = tmp_path

    manager = WorkspaceManager(config_manager)
    manager.initialize_workspace("test-workspace", "3.11")

    assert (tmp_path / "repos").exists()
    assert (tmp_path / "logs").exists()
    assert (tmp_path / ".gitignore").exists()
```

### Test Coverage

We aim for at least 80% test coverage. Check coverage with:
```bash
poetry run pytest --cov=multi_poetry_runner --cov-report=term-missing
```

## Documentation

### Types of Documentation

1. **Code Documentation**: Docstrings in code
2. **User Documentation**: README.md and guides
3. **API Documentation**: Generated from docstrings
4. **Examples**: Sample code and use cases

### Documentation Guidelines

- Write clear, concise documentation
- Include code examples where appropriate
- Keep documentation up-to-date with code changes
- Use proper Markdown formatting
- Spell-check your documentation

### Building Documentation

If Sphinx is set up:
```bash
cd docs
poetry run make html
```

## Submitting Changes

### Pull Request Process

1. **Create a branch**:
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

2. **Make your changes**:
- Write clean, documented code
- Add tests for new functionality
- Update documentation as needed

3. **Commit your changes**:
```bash
git add .
git commit -m "feat: add new feature"
# or
git commit -m "fix: resolve issue with X"
```

Use conventional commit messages:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `test:` for test additions/changes
- `refactor:` for code refactoring
- `style:` for formatting changes
- `chore:` for maintenance tasks

4. **Push to your fork**:
```bash
git push origin feature/your-feature-name
```

5. **Create a Pull Request**:
- Go to GitHub and create a PR from your branch
- Fill in the PR template
- Link related issues
- Ensure CI checks pass

### PR Requirements

Before submitting a PR, ensure:

- [ ] All tests pass
- [ ] Code is formatted with Black
- [ ] Ruff linting passes
- [ ] Type hints are added
- [ ] Documentation is updated
- [ ] CHANGELOG.md is updated (for significant changes)
- [ ] Commit messages follow conventions

### Review Process

1. PRs require at least one review
2. Address review comments
3. Keep PRs focused and reasonable in size
4. Be patient and respectful during reviews

## Reporting Issues

### Bug Reports

When reporting bugs, include:

1. **Description**: Clear description of the bug
2. **Steps to Reproduce**: Detailed steps to reproduce the issue
3. **Expected Behavior**: What should happen
4. **Actual Behavior**: What actually happens
5. **Environment**:
   - MPR version
   - Python version
   - Operating system
   - Poetry version
6. **Logs**: Relevant error messages or logs
7. **Screenshots**: If applicable

### Feature Requests

For feature requests, provide:

1. **Use Case**: Describe the problem you're trying to solve
2. **Proposed Solution**: Your suggested implementation
3. **Alternatives**: Other solutions you've considered
4. **Additional Context**: Any other relevant information

## Getting Help

If you need help:

1. Check the [documentation](README.md)
2. Search existing [issues](https://github.com/buvis/multi-poetry-runner/issues)
3. Ask in discussions (if enabled)
4. Create a new issue with your question

## Recognition

Contributors will be recognized in:
- The project's AUTHORS file
- Release notes
- Project documentation

Thank you for contributing to Multi-Poetry Runner!
