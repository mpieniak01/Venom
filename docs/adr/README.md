# Architecture Decision Records (ADR)

This directory contains Architecture Decision Records (ADRs) for the Venom system. ADRs document important architectural decisions made during the project's evolution.

## What is an ADR?

An Architecture Decision Record captures a single architecture decision such as choice of technologies, design patterns, or system-wide conventions. Each ADR includes:
- **Context**: The situation that requires a decision
- **Decision**: The chosen solution
- **Status**: Proposed, Accepted, Deprecated, or Superseded
- **Consequences**: The positive and negative impacts of the decision

## ADR Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-001](./ADR-001-runtime-strategy-llm-first.md) | Runtime Strategy: LLM-First with ONNX Fallback | Accepted | 2026-02-18 |

## ADR Naming Convention

ADRs follow the naming pattern: `ADR-XXX-short-title.md`
- **XXX**: Three-digit sequential number (001, 002, etc.)
- **short-title**: Brief kebab-case description

## References

- [Architecture Decision Records (ADR) by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub Organization](https://adr.github.io/)
