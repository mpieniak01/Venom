# Test Artifacts Policy: CLEAN vs PRESERVE

## Overview

This policy defines a unified approach to managing test artifacts in the Venom repository. The goal is to prevent test pollution in runtime directories while maintaining diagnostic capabilities.

## Operating Modes

### CLEAN Mode (Default)

**Purpose**: Maintain clean runtime environment after tests

**Behavior**:
- Test artifacts are written to isolated temporary directories
- All test data is automatically removed after test completion
- Runtime directories (`data/*`, `logs/*`) remain unpolluted
- Suitable for CI/CD pipelines and local development

**When to use**:
- Regular local testing (`make test`)
- CI/CD pipelines (always)
- Pre-commit/pre-push validation
- Quality gate validation

### PRESERVE Mode (Opt-in)

**Purpose**: Retain test artifacts for debugging and analysis

**Behavior**:
- Test artifacts are written to persistent directories
- Artifacts remain available after test completion
- Artifact location is logged for easy access
- Suitable for debugging test failures or analyzing behavior

**When to use**:
- Debugging failing tests
- Analyzing test behavior
- Development of new test scenarios
- Investigating edge cases

## Environment Variables

### `VENOM_TEST_ARTIFACT_MODE`

Controls the artifact retention strategy.

**Values**:
- `clean` (default): Remove artifacts after tests
- `preserve`: Keep artifacts for analysis

**Examples**:
```bash
# Default CLEAN mode
make test

# Explicit CLEAN mode
VENOM_TEST_ARTIFACT_MODE=clean make test

# PRESERVE mode
VENOM_TEST_ARTIFACT_MODE=preserve make test
```

### `VENOM_TEST_ARTIFACT_DIR`

Overrides the default artifact directory location.

**Default**: `test-results/tmp/session-{timestamp}`

**Example**:
```bash
VENOM_TEST_ARTIFACT_DIR=/tmp/my-test-artifacts make test
```

## Artifact Directory Structure

```
test-results/
└── tmp/
    └── session-{timestamp}/
        ├── timelines/          # Chronos timeline snapshots
        ├── synthetic_training/ # Dream engine outputs
        ├── training/           # Academy training artifacts
        ├── logs/               # Test-specific logs
        └── metadata.json       # Session metadata
```

## Test Implementation Guidelines

### Using the Artifact Fixture

Tests should use the `test_artifact_dir` fixture for all artifact paths:

```python
def test_creates_artifacts(test_artifact_dir):
    """Test that creates artifacts in isolated directory."""
    output_file = test_artifact_dir / "output.json"
    output_file.write_text('{"test": "data"}')
    assert output_file.exists()
```

### Environment-Specific Paths

For tests that need specific environment paths (timelines, training, etc.), use the pre-configured environment variables:

```python
def test_chronos_timeline():
    """Test using CHRONOS_TIMELINES_DIR set in conftest.py."""
    # CHRONOS_TIMELINES_DIR is already redirected to test artifact dir
    from venom_core.config import SETTINGS
    timeline_dir = Path(SETTINGS.CHRONOS_TIMELINES_DIR)
    # Artifacts written here will be managed by artifact mode
```

### Marking Test Artifacts

Test artifacts should be marked with metadata to identify them:

```json
{
  "type": "test_artifact",
  "test_name": "test_example",
  "session_id": "session-20260214-191230",
  "timestamp": "2026-02-14T19:12:30Z"
}
```

## Make Targets

### `make test`

Runs tests in CLEAN mode (default).

```bash
make test
```

Equivalent to:
```bash
VENOM_TEST_ARTIFACT_MODE=clean pytest
```

### `make test-data`

Runs tests in PRESERVE mode for debugging.

```bash
make test-data
```

Equivalent to:
```bash
VENOM_TEST_ARTIFACT_MODE=preserve pytest
```

After completion, displays artifact location:
```
✅ Tests completed
📁 Artifacts preserved at: test-results/tmp/session-20260214-191230
```

### `make test-artifacts-cleanup`

Manually removes old test artifacts.

```bash
# Remove artifacts older than 7 days
make test-artifacts-cleanup

# Remove all artifacts
make test-artifacts-cleanup CLEANUP_ALL=1
```

## CI/CD Integration

CI pipelines **always** use CLEAN mode to prevent artifact accumulation:

```yaml
- name: Run tests
  run: make test
  env:
    VENOM_TEST_ARTIFACT_MODE: clean
```

## Runtime Directory Protection

The following directories are protected from test pollution:

- `data/timelines/` - Chronos checkpoints
- `data/synthetic_training/` - Dream engine outputs
- `data/training/` - Academy training data
- `logs/` - Application logs
- `workspace/` - User workspaces

Tests writing to these directories will automatically be redirected to the test artifact directory.

## Artifact Cleanup Strategy

### CLEAN Mode
- Artifacts removed immediately after test session completion
- Uses pytest `autouse` fixtures for automatic cleanup
- Temporary directories fully removed
- No manual intervention required

### PRESERVE Mode
- Artifacts remain in `test-results/tmp/session-{timestamp}/`
- Old sessions are not automatically removed
- Manual cleanup via `make test-artifacts-cleanup` when needed
- TTL-based cleanup (7 days default) for old artifacts

## Exclusions and Filters

### Panel/UI Filtering

Test artifacts are excluded from operational panels:
- Timeline list views filter out test artifacts
- Training job listings exclude test sessions
- Dashboard metrics ignore test data

### Filter Implementation

```python
def is_test_artifact(metadata: dict) -> bool:
    """Check if artifact is from test session."""
    return (
        metadata.get("type") == "test_artifact"
        or metadata.get("session_id", "").startswith("test_")
    )
```

## Troubleshooting

### Tests are polluting runtime directories

**Symptom**: Test data appears in `data/timelines/`, `data/training/`, etc.

**Solution**:
1. Verify test uses proper fixtures (`test_artifact_dir`)
2. Check that `tests/conftest.py` is loaded
3. Ensure environment variables are set correctly

### Artifacts not preserved in PRESERVE mode

**Symptom**: Artifacts are deleted even with `VENOM_TEST_ARTIFACT_MODE=preserve`

**Solution**:
1. Verify environment variable is set: `echo $VENOM_TEST_ARTIFACT_MODE`
2. Check fixture implementation in `tests/conftest.py`
3. Review test cleanup logic

### Old artifacts consuming disk space

**Symptom**: `test-results/tmp/` directory growing large

**Solution**:
```bash
# Remove artifacts older than 7 days
make test-artifacts-cleanup

# Remove all artifacts
make test-artifacts-cleanup CLEANUP_ALL=1
```

## Migration Guide

### For Existing Tests

1. **Tests using `tmp_path`**: No changes needed, already isolated
2. **Tests writing to `data/*`**: Verify environment variables are redirected in `conftest.py`
3. **Tests with custom cleanup**: Can remove manual cleanup, handled by fixture

### Example Migration

**Before**:
```python
def test_example():
    output_dir = Path("data/training")
    output_dir.mkdir(parents=True, exist_ok=True)
    # ... test logic ...
    # Manual cleanup
    shutil.rmtree(output_dir)
```

**After**:
```python
def test_example(test_artifact_dir):
    # Environment already redirected, or use fixture directly
    output_dir = test_artifact_dir / "training"
    output_dir.mkdir(parents=True, exist_ok=True)
    # ... test logic ...
    # Automatic cleanup handled by fixture
```

## Quality Gates

Tests are considered compliant when:

1. ✅ `make test` completes without polluting runtime directories
2. ✅ No new entries in `data/timelines/`, `data/training/`, `logs/` after test run
3. ✅ `make pr-fast` passes
4. ✅ `make check-new-code-coverage` passes
5. ✅ Test artifacts properly marked with metadata
6. ✅ PRESERVE mode retains artifacts with correct paths logged

## References

- Testing Policy: `docs/TESTING_POLICY.md`
- Security Policy: `docs/SECURITY_POLICY.md`
- Agent Guidelines: `docs/AGENTS.md`
