# Security fixes and dependency hygiene

This file documents changes and decisions related to security and dependency
hygiene (version updates, risk acceptance, project constraints).
It is a maintenance note for the experimental project.

## Recent actions (2025-01-18)

Based on signals from **Snyk**, dependency versions identified as vulnerable
(CVE - high) were updated:

- `aiohttp>=3.13.3` - throttling and resource limits
- `urllib3>=2.6.3` - handling of compressed data
- `transformers>=4.57.6` - potential deserialization of untrusted data
- `azure-core>=1.38.0` - potential deserialization of untrusted data
- `pydantic` bumped to `>=2.12,<3.0` to maintain compatibility with vLLM 0.12.x
  and eliminate the version conflict (runtime warning).

## Tools and scope of checks

- **Snyk**
  Used manually for dependency vulnerability analysis.
  Not integrated with the CI pipeline.

- **pre-commit + Ruff**
  Used for code quality and consistency checks.
  Do not cover dependency CVE scanning.

- **GitHub Security (Dependabot / GitGuardian)**
  Default GitHub mechanisms are used:
  - dependency alerts,
  - secret scanning.
  This is not a full security audit system.

### Dependency version policy (Python)

- `semantic-kernel >= 1.39.1` - works with `pydantic 2.12.x` with the `Url` shim
  (added in `venom_core/__init__.py`).
- `pydantic 2.12.x` - required by vLLM 0.12.x (pip warns because SK declares
  `<2.12`, but it works with the shim).
- The expected set is: SK 1.39.1+, Pydantic 2.12.x, vLLM 0.12.x; if any of
  these packages are bumped, verify SK imports (Url) and run smoke tests.

The project currently **does not have**:
- SonarQube / SonarCloud,
- a cyclic CVE scanner in CI,
- automatic verification of model artifacts.

## Risk notes

- In the HuggingFace ecosystem (`transformers`, `accelerate`, `tokenizers`)
  there are reports of *deserialization of untrusted data* for which there are
  no complete upstream fixes.

- Risk is reduced organizationally:
  - only trusted models and artifacts are used,
  - no dynamic model downloads at runtime.

## Risk register

- **Model and artifact sources**
  Venom is experimental software.
  The system does not automatically verify integrity or provenance of models.
  Responsibility for choosing sources rests with the user.
