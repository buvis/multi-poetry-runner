"""Configuration templates for MPR."""

# Default workspace configuration template
WORKSPACE_CONFIG_TEMPLATE = """
version: "1.0"
workspace:
  name: "{name}"
  python_version: "{python_version}"

repositories:
  - name: "buvis-pybase"
    url: "https://github.com/buvis/buvis-pybase.git"
    package_name: "buvis-pybase"
    branch: "main"
    dependencies: []
    source: "pypi"
    
  - name: "doogat-core"
    url: "https://github.com/doogat/doogat-core.git"
    package_name: "doogat-core"
    branch: "main"
    dependencies: ["buvis-pybase"]
    source: "pypi"

settings:
  auto_install_hooks: true
  use_test_pypi: true
  parallel_jobs: 4
  timeout: 3600
"""

# Makefile template
MAKEFILE_TEMPLATE = """
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

# .gitignore template
GITIGNORE_TEMPLATE = """
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

# Integration test configuration template
INTEGRATION_TEST_CONFIG_TEMPLATE = """
name: "{workspace_name}-integration"
description: "Integration tests for the complete package stack"
environment: "local"
python_version: "{python_version}"

packages:
{packages}

tests:
  - "tests/integration/test_basic_integration.py"
  - "tests/integration/test_data_flow.py"

timeout: 600
parallel: false
cleanup: true
"""

# Docker compose test template
DOCKER_COMPOSE_TEST_TEMPLATE = """
version: '3.8'

services:
  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.test
    volumes:
      - ./tests:/tests
      - ./reports:/reports
    environment:
      - PYTHONPATH=/app
    command: |
      python -m pytest /tests/integration 
      --junit-xml=/reports/results.xml 
      --html=/reports/report.html
      --self-contained-html
"""

# Dockerfile for testing
DOCKERFILE_TEST_TEMPLATE = """
FROM python:{python_version}-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy workspace
COPY . .

# Install all packages
RUN poetry config virtualenvs.create false
RUN for dir in repos/*/; do \\
        if [ -f "$dir/pyproject.toml" ]; then \\
            cd "$dir" && poetry install && cd /app; \\
        fi \\
    done

# Install test dependencies
RUN pip install pytest pytest-html pytest-timeout
"""

# Basic integration test template
BASIC_INTEGRATION_TEST_TEMPLATE = '''"""Basic integration tests."""

import pytest
{imports}


def test_package_imports():
    """Test that all packages can be imported."""
{import_tests}


def test_basic_functionality():
    """Test basic functionality across packages."""
    # TODO: Add specific tests for your workflow
    pass


@pytest.mark.asyncio
async def test_async_operations():
    """Test async operations if applicable."""
    # TODO: Add async tests if needed
    pass
'''
