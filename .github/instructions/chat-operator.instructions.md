---
applyTo: "**"
---

# Chat Operator Instruction

Default response language for workspace agents is Polish unless the user explicitly asks for English or an external format requires it.

Canonical references:

- `../../docs/CHAT_OPERATOR.md`
- `../../docs/PL/CHAT_OPERATOR.md`

Rules:

1. Keep chat-specific behavior, configuration, runtime lifecycle, and make targets out of `OPERATOR_MANUAL.md`; link to `CHAT_OPERATOR.md` instead.
2. Update both EN and PL chat operator docs whenever chat routing, memory, calendar, session, or runtime management changes.
3. Use the supported `make` targets for local-first lifecycle and validation; do not introduce ad-hoc shell workflows as the documented contract.
4. Do not mix chat operator scope with code generation, research, or release policy; those belong to dedicated tools and workflow docs.
5. Default chat topics are repository state, git branch status, API contract scope, documentation remodeling, and script remodeling.
6. Calendar and small talk are secondary or explicit-user-request topics, not the default workflow.
