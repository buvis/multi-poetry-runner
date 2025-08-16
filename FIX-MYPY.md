# MyPy Errors Fix Plan

## Overview
This document outlines a comprehensive plan to fix all 69 mypy errors found in the multi-poetry-runner project. The errors are categorized by type and severity, with specific solutions for each category.

## Error Categories Summary

| Category | Count | Priority | Files Affected |
|----------|-------|----------|----------------|
| Test Function Type Annotations | 35 | Medium | `tests/` directory |
| Collection Mutability Issues | 10 | High | Core modules |
| None/Union Type Handling | 8 | High | Core modules |
| Any Return Type Issues | 6 | High | Core modules |
| Variable Type Annotations | 4 | Medium | Core modules |
| Generator Return Types | 3 | Medium | Test fixtures |
| Assignment Type Mismatches | 3 | High | Core modules |

## Detailed Fix Plan

### 1. Test Function Type Annotations (35 errors)
**Priority: Medium** - These don't affect runtime but improve development experience

**Files affected:**
- `tests/test_workspace.py` (15 errors)
- `tests/test_config.py` (10 errors)
- `tests/test_cli.py` (10 errors)

**Solution:**
Add proper type annotations to all test functions and fixtures:

```python
# Before:
def test_function(workspace_manager):
    pass

@pytest.fixture
def temp_workspace():
    pass

# After:
def test_function(workspace_manager: WorkspaceManager) -> None:
    pass

@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    pass
```

**Implementation steps:**
1. Add `from typing import Generator` imports where needed
2. Fix all `@pytest.fixture` return types to `Generator[Type, None, None]`
3. Add `-> None` to all test functions
4. Add proper parameter types based on fixture types

### 2. Collection Mutability Issues (10 errors)
**Priority: High** - These can cause runtime errors

**Files affected:**
- `src/multi_poetry_runner/core/hooks.py` (6 errors)
- `src/multi_poetry_runner/core/dependencies.py` (2 errors)
- `src/multi_poetry_runner/core/workspace.py` (2 errors)

**Problem:** Code tries to call `.append()` or use indexed assignment on immutable collections like `Sequence[str]` or `Collection[str]`.

**Solution:**
Change type annotations from immutable to mutable collections:

```python
# Before:
dependencies: Sequence[str] = []
packages: Collection[str] = []

# After:
dependencies: list[str] = []
packages: list[str] = []
```

**Specific fixes needed:**
- Line 591 in `dependencies.py`: Change `Sequence[str]` to `list[str]`
- Line 1131 in `release.py`: Change `Sequence[str]` to `list[str]`
- Lines 306, 311, 315 in `workspace.py`: Change `Collection[str]` to `list[str]`
- Lines 291, 298, 303, 306, 309, 312 in `hooks.py`: Fix object typing

### 3. None/Union Type Handling (8 errors)
**Priority: High** - These can cause AttributeError at runtime

**Files affected:**
- `src/multi_poetry_runner/core/release.py` (3 errors)
- `src/multi_poetry_runner/core/version_manager.py` (1 error)

**Problem:** Code operates on variables that could be `None` without proper null checks.

**Solution:**
Add null checks before accessing attributes:

```python
# Before:
def some_function() -> str:
    path = get_path()  # Returns Path | None
    path.mkdir()  # Error: Item "None" has no attribute "mkdir"

# After:
def some_function() -> str:
    path = get_path()  # Returns Path | None
    if path is not None:
        path.mkdir()
    else:
        raise ValueError("Path cannot be None")
```

**Specific fixes:**
- Lines 204, 209, 222 in `release.py`: Add null checks for `Path | None`
- Line 806 in `version_manager.py`: Handle `RepositoryConfig | None`

### 4. Any Return Type Issues (6 errors)
**Priority: High** - These defeat the purpose of type checking

**Files affected:**
- `src/multi_poetry_runner/core/version_manager.py` (1 error)
- `src/multi_poetry_runner/core/dependencies.py` (1 error)
- `src/multi_poetry_runner/core/workspace.py` (2 errors)
- `src/multi_poetry_runner/core/release.py` (1 error)
- `tests/test_config.py` (1 error)

**Problem:** Functions declared to return specific types but actually return `Any`.

**Solution:**
Ensure proper type casting or fix the return type:

```python
# Before:
def get_version() -> str | None:
    data = some_function()  # Returns Any
    return data.get("version")  # Error: returning Any

# After:
def get_version() -> str | None:
    data = some_function()  # Returns Any
    version = data.get("version")
    return str(version) if version is not None else None
```

### 5. Variable Type Annotations (4 errors)
**Priority: Medium** - Improves code clarity

**Files affected:**
- `src/multi_poetry_runner/core/dependencies.py` (2 errors)
- `src/multi_poetry_runner/core/testing.py` (2 errors)

**Solution:**
Add explicit type annotations:

```python
# Before:
repo_status = {}
all_packages = {}

# After:
repo_status: dict[str, Any] = {}
all_packages: dict[str, Package] = {}
```

### 6. Module Attribute Errors (1 error)
**Priority: High** - This indicates a missing import

**File:** `src/multi_poetry_runner/core/workspace.py:224`

**Problem:** `Module has no attribute "os"`

**Solution:**
Add missing import: `import os`

### 7. Object Type Issues in hooks.py (6 errors)
**Priority: High** - Multiple attribute access errors on `object` type

**File:** `src/multi_poetry_runner/core/hooks.py`

**Problem:** Variables typed as `object` but expected to have list/dict methods.

**Solution:**
Review the code to determine correct types and update annotations:

```python
# Before:
def some_function():
    result: object = get_data()
    result.append(item)  # Error: object has no attribute append

# After:
def some_function():
    result: list[Any] = get_data()
    result.append(item)
```

## Implementation Order

### Phase 1: Critical Runtime Issues (High Priority)
1. Fix None/Union type handling (8 errors)
2. Fix collection mutability issues (10 errors)
3. Fix Any return type issues (6 errors)
4. Fix object type issues in hooks.py (6 errors)
5. Fix missing import in workspace.py (1 error)

### Phase 2: Code Quality Improvements (Medium Priority)
1. Add variable type annotations (4 errors)
2. Fix generator return types in tests (3 errors)
3. Add test function type annotations (35 errors)

## Commands to Run

```bash
# Check progress after each phase
poetry run mypy . --ignore-missing-imports

# Run with specific error codes to focus on categories
poetry run mypy . --ignore-missing-imports --disable-error-code=no-untyped-def

# Final verification
poetry run mypy . --ignore-missing-imports --strict
```

## Validation Steps

1. **After Phase 1:** Run `poetry run mypy . --ignore-missing-imports` - should have ≤35 errors (only test annotations)
2. **After Phase 2:** Run `poetry run mypy . --ignore-missing-imports` - should have 0 errors
3. **Final check:** Run full test suite to ensure no regressions: `poetry run pytest`
4. **Integration test:** Run core functionality to ensure typing fixes don't break runtime behavior

## Expected Outcome

After implementing all fixes:
- ✅ 0 mypy errors
- ✅ Better IDE support and autocomplete
- ✅ Improved code maintainability
- ✅ Prevention of common runtime type errors
- ✅ No breaking changes to existing functionality

## Notes

- All fixes should maintain backward compatibility
- Priority should be given to fixing runtime-critical type issues first
- Test the application after each phase to ensure no regressions
- Consider adding `--strict` mode to mypy configuration after all fixes are complete
