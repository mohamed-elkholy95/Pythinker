# Testing & Linting Quick Reference

**Last Updated:** 2026-02-11 (Context7 Validated)

## 🔧 Setup

```bash
conda activate pythinker
cd backend
pip install -r requirements-dev.txt
pip install -r tests/requirements.txt
```

## 🧹 Linting Commands

### Basic Usage
```bash
# Check all files
ruff check .

# Auto-fix all fixable issues
ruff check --fix .

# Format code
ruff format .

# One-liner: fix + format
ruff check --fix . && ruff format .
```

### Targeted Checks
```bash
# Check only specific rules
ruff check --select S,ASYNC .  # Security + Async

# Ignore specific rules
ruff check --ignore E501,S105 .

# Check single file
ruff check app/main.py
```

### Output Options
```bash
# Show detailed output
ruff check --output-format=full .

# Show only errors (no warnings)
ruff check --output-format=concise .

# Generate JSON report
ruff check --output-format=json . > ruff-report.json
```

## 🧪 Testing Commands

### Basic Usage
```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Run specific test file
pytest tests/test_file.py

# Run specific test function
pytest tests/test_file.py::test_function_name
```

### Parallel Execution (NEW)
```bash
# Auto-detect CPU count (fastest)
pytest -n auto

# Use specific worker count
pytest -n 4

# Disable parallel (debugging)
pytest -n 0
```

### Test Selection
```bash
# By marker
pytest -m unit                    # Only unit tests
pytest -m "integration and not slow"  # Integration, not slow
pytest -m "not requires_network"  # Skip network tests

# By keyword
pytest -k "test_user"            # Tests with "user" in name
pytest -k "not integration"      # Exclude integration tests

# By path
pytest tests/unit/               # Only unit tests directory
pytest tests/integration/test_api.py  # Single integration file
```

### Coverage
```bash
# Run with coverage (default)
pytest --cov=app

# Show missing lines
pytest --cov=app --cov-report=term-missing

# Generate HTML report
pytest --cov=app --cov-report=html
open htmlcov/index.html

# Skip coverage (faster)
pytest -p no:cov -o addopts=
```

### Timeout Protection (NEW)
```bash
# Global timeout (5 minutes per test)
pytest --timeout=300

# Show which tests are slow
pytest --durations=10
```

### Debugging
```bash
# Show local variables on failure (default)
pytest --showlocals

# Drop into debugger on failure
pytest --pdb

# Stop on first failure
pytest -x

# Show print statements
pytest -s

# More detailed traceback
pytest --tb=long
```

### Watch Mode (Continuous Testing)
```bash
# Install pytest-watch
pip install pytest-watch

# Run tests on file change
ptw -- -v
```

## 🔍 Common Workflows

### Pre-Commit Check
```bash
# Full validation (runs in CI)
ruff check --fix . && ruff format . && pytest
```

### Fast Development Loop
```bash
# Format + run specific tests
ruff format . && pytest -n auto -m unit
```

### Debugging Failing Test
```bash
# Single test with full output
pytest tests/test_file.py::test_name -v --tb=long --showlocals -s
```

### Security Audit
```bash
# Run only security checks
ruff check --select S .

# Run security + audit dependencies
ruff check --select S . && pip-audit
```

### Performance Check
```bash
# Run only performance lint rules
ruff check --select PERF .

# Show slowest tests
pytest --durations=20
```

## 📊 Understanding Output

### Ruff Rule Codes
- **E/W:** Style errors (pycodestyle)
- **F:** Logic errors (Pyflakes)
- **I:** Import sorting (isort)
- **B:** Buggy code patterns (bugbear)
- **S:** Security issues (bandit)
- **ASYNC:** Async/await anti-patterns
- **PERF:** Performance anti-patterns
- **FURB:** Modern Python idioms
- **T20:** Print statements
- **ERA:** Commented-out code

### Pytest Markers
- `unit` - Fast, mocked tests
- `integration` - Tests with external services
- `slow` - Long-running tests
- `e2e` - End-to-end tests
- `requires_network` - Needs network access
- `requires_database` - Needs database
- `flaky` - Non-deterministic tests

## 🚀 CI/CD Integration

### GitHub Actions Example
```yaml
- name: Lint
  run: |
    conda activate pythinker
    cd backend
    ruff check .
    ruff format --check .

- name: Test
  run: |
    conda activate pythinker
    cd backend
    pytest -n auto --cov=app --cov-report=xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./backend/coverage.xml
```

## 🛠️ Troubleshooting

### Ruff Issues

**"Unknown rule code"**
```bash
# Update ruff to latest version
pip install --upgrade ruff
```

**"Too many violations"**
```bash
# See all violations (no limit)
ruff check --show-files .

# Fix incrementally by rule
ruff check --fix --select F .  # Fix Pyflakes first
ruff check --fix --select I .  # Then imports
```

### Pytest Issues

**"No tests collected"**
```bash
# Verify test discovery
pytest --collect-only

# Check test paths
pytest --fixtures
```

**"Async fixture warnings"**
```bash
# Update pytest-asyncio
pip install --upgrade pytest-asyncio

# Check asyncio_mode setting in pyproject.toml
```

**"Tests hanging"**
```bash
# Add timeout protection
pytest --timeout=60

# Identify slow tests
pytest --durations=0
```

## 📚 Resources

- **Ruff Docs:** https://docs.astral.sh/ruff
- **Ruff Rules:** https://docs.astral.sh/ruff/rules
- **Pytest Docs:** https://docs.pytest.org
- **Context7 Validation:** See `TESTING_AND_LINTING_ENHANCEMENT.md`

## 🎯 Best Practices

1. ✅ Run `ruff check --fix` before committing
2. ✅ Use `pytest -n auto` for faster feedback
3. ✅ Mark tests with appropriate markers (`@pytest.mark.unit`)
4. ✅ Use `--showlocals` when debugging failures
5. ✅ Keep coverage above 24% (project minimum)
6. ✅ Review security violations (S rules) carefully
7. ✅ Add timeouts for slow/flaky tests
8. ✅ Use `--strict-markers` to catch typos
