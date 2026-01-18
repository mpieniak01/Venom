# Security fixes and dependency hygiene

This file documents changes and decisions regarding security and dependency hygiene (version updates, accepted risks, project limitations). It serves as a maintenance note for the experimental project.

## Recent actions (2025-01-18)

- Based on Snyk findings, bumped dependencies flagged as high-severity CVE:
  - `aiohttp>=3.13.3` – throttling/resource limits
  - `urllib3>=2.6.3` – compressed data handling
  - `transformers>=4.57.6` – potential deserialization of untrusted data
  - `azure-core>=1.38.0` – potential deserialization of untrusted data
  - `pydantic` raised to `>=2.12,<3.0` to keep compatibility with vLLM 0.12.x and remove version conflict warning.

## Tooling and control scope

- **Snyk**
  Used manually to analyze dependency vulnerabilities.
  Not integrated into CI pipeline.

- **pre-commit + Ruff**
  Used for code quality/consistency.
  Do not cover dependency CVE scanning.

- **GitHub Security (Dependabot / GitGuardian)**
  Using GitHub defaults:
  - dependency alerts,
  - secret scanning.
  This is not a full security audit system.

### Dependency version policy (Python)

- `semantic-kernel >= 1.39.1` – works with `pydantic 2.12.x` using a `Url` shim (added in `venom_core/__init__.py`).
- `pydantic 2.12.x` – required by vLLM 0.12.x (pip warns because SK declares `<2.12`, but it works with the shim).
- Expected set to keep: SK 1.39.1+, Pydantic 2.12.x, vLLM 0.12.x; if any of these are bumped, verify SK imports (Url) and run smoke tests.

The project currently does **not** have:
- SonarQube / SonarCloud,
- a recurring CVE scanner in CI,
- automated verification of model artifacts.

## Risk notes

- HuggingFace stack (`transformers`, `accelerate`, `tokenizers`) has reports of *deserialization of untrusted data* with no complete upstream fixes yet.

- Risk is mitigated organizationally:
  - only trusted models and artifacts are used,
  - no dynamic model downloads at runtime.

## Risk register

- **Model and artifact provenance**
  Venom is experimental software.
  The system does not automatically verify integrity or origin of models.
  Responsibility for choosing sources rests with the user.
