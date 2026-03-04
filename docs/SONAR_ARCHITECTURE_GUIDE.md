# Sonar Architecture Guide

This document describes how Venom configures architecture analysis for Sonar.

## Goals

1. Keep architecture checks aligned with Sonar standard workflow.
2. Keep architecture config versioned in repository.
3. Avoid duplicated architecture gates.

## Configuration Files

1. Runtime architecture import rules guard:
   - `config/architecture/contracts.yaml`
   - validated by `scripts/check_architecture_contracts.py`
2. Sonar architecture model:
   - `config/architecture/sonar-architecture.yaml`
   - validated by `scripts/validate_sonar_architecture.py`

## Local Validation

Run existing architecture gate:

```bash
make architecture-drift-check
```

It validates both:
1. Python import contracts (`venom_core`),
2. Sonar architecture config structure.

Optional summary export for manual Sonar UI sync:

```bash
make architecture-sonar-export
```

Output:
1. `test-results/sonar/architecture-summary.json`

## Sonar Integration

Venom passes Sonar architecture file path through:

```properties
sonar.architecture.configpath=./config/architecture/sonar-architecture.yaml
```

The property is configured in `sonar-project.properties`.

### Optional Sonar run modes

This repository uses `sonar-scanner`/GitHub Actions (not Maven). Local examples:

Explicit config path:

```bash
sonar-scanner -Dsonar.architecture.configpath=./config/architecture/sonar-architecture.yaml
```

No config (comparison/debug):

```bash
sonar-scanner -Dsonar.architecture.noconfig=true
```

CI path:

1. `.github/workflows/ci.yml` runs `SonarSource/sonarqube-scan-action`.
2. `sonar-project.properties` keeps the default `sonar.architecture.configpath`.

## Update Workflow

1. Update `config/architecture/sonar-architecture.yaml`.
2. Run `make architecture-drift-check`.
3. Run `make pr-fast`.
4. Synchronize the same model in Sonar Intended Architecture UI (Sonar-first governance).

## Notes

1. Keep one active architecture config per analysis run.
2. Do not introduce a parallel, conflicting architecture gate.
