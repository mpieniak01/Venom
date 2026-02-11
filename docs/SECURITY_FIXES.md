# Security fixes and dependency hygiene

This file documents changes and decisions related to security and dependency hygiene (version updates, risk acceptance, project constraints). It is a maintenance note for the experimental project.

Official runtime and autonomy security policy is defined in `docs/SECURITY_POLICY.md`.

## Recent actions (2025-01-18)

Based on signals from **Snyk**, dependency versions identified as vulnerable (CVE - high) were updated:

- `aiohttp>=3.13.3` - throttling and resource limits
- `urllib3>=2.6.3` - handling of compressed data
- `transformers>=4.57.6` - potential deserialization of untrusted data
- `azure-core>=1.38.0` - potential deserialization of untrusted data
- `pydantic` bumped to `>=2.12,<3.0` according to the "newer versions" policy.
- `openai` bumped to `>=2.8.0` (requirement for `litellm>=1.81.3`).
- `openapi-core` bumped to `>=0.22.0` to unlock `werkzeug>=3.1.5`.
- `graphrag` and `lancedb` pinned to stable versions in `requirements.txt` (resolver backtracking limit).

## Status after latest scan (current)

- Bumping `pypdf`, `filelock`, `litellm`, `marshmallow`, `pyasn1`, and `werkzeug` reduces the number of vulnerabilities but **breaks** dependencies:
  - `semantic-kernel` declares `openai<2` and `pydantic<2.12` (requires verification and potential patches/overrides for newer versions).
  - `semantic-kernel` expects `openapi-core<0.20`, while the project uses `>=0.22`.
  The decision was made: **we go with newer versions despite conflicts** – regression tests and potential runtime fixes are required.

## Tools and scope of checks

- **Snyk**
  Used manually for dependency vulnerability analysis. Not integrated with the CI pipeline.

- **pre-commit + Ruff**
  Used for code quality and consistency checks. Do not cover dependency CVE scanning.

- **GitHub Security (Dependabot / GitGuardian)**
  Default GitHub mechanisms are used:
  - dependency alerts,
  - secret scanning.
  This is not a full security audit system.

### Dependency version policy (Python)

- `semantic-kernel >= 1.39.2` – declares `pydantic <2.12` and `openai<2`, but the project maintains newer versions contrary to metadata. Requires runtime validation.
- `pydantic >=2.12,<3.0` – target range compliant with update policy.
- The expected set is: SK 1.39.2+, Pydantic 2.12+ (with override), OpenAI 2.x. Smoke tests required after every update.

The project currently **does not have**:
- SonarQube / SonarCloud,
- a cyclic CVE scanner in CI,
- automatic verification of model artifacts.

## Risk notes

- In the HuggingFace ecosystem (`transformers`, `accelerate`, `tokenizers`) there are reports of *deserialization of untrusted data* for which there are no complete upstream fixes.

- Risk is reduced organizationally:
  - only trusted models and artifacts are used,
  - no dynamic model downloads at runtime.

## Risk register

- **Model and artifact sources**
  Venom is experimental software. The system does not automatically verify integrity or provenance of models. Responsibility for choosing sources rests with the user.
