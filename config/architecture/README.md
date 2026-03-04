# Architecture Config (Sonar-first)

This directory stores architecture governance files used by local gates and Sonar integration.

## Files

1. `contracts.yaml`
   - Python import-level architecture contracts (`venom_core`).
   - validated by `scripts/check_architecture_contracts.py`.
2. `sonar-architecture.yaml`
   - Sonar architecture model (perspectives/groups/constraints).
   - validated by `scripts/validate_sonar_architecture.py`.

## Validation

Run:

```bash
make architecture-drift-check
```

It validates both files above.

## Sonar binding

The Sonar analysis points to:

```properties
sonar.architecture.configpath=./config/architecture/sonar-architecture.yaml
```

in `sonar-project.properties`.

## Operational rule

1. Keep one active Sonar architecture file for analysis.
2. Do not introduce duplicate/parallel architecture gate definitions.
