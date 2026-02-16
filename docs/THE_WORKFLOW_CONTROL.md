# THE WORKFLOW CONTROL - Visual Composer & Safe Change Flow

## Overview

THE WORKFLOW CONTROL is Venom's operator interface for composing and applying stack configuration safely.
It combines:
1. A visual graph composer (nodes, edges, swimlanes).
2. A property inspector for the selected element.
3. Plan/apply execution with compatibility validation and audit trail.

Use this document as the operator guide.
For payload-level API details, see `docs/WORKFLOW_CONTROL_PLANE_API.md`.

## What The Screen Does

The Workflow screen is not only a status map. It is an interactive control plane:
1. You select or edit nodes in the composer.
2. Changes are reflected in the property panel (single source of truth).
3. The system builds a plan, validates compatibility, then applies safely.

## Composer Model

### Swimlanes (Domain Sections)

The graph is split by domain:
1. **Decision / Intent**
2. **Kernel / Embedding**
3. **Runtime / Provider**
4. **Execution / Workflow Ops** (optional, depending on feature set)

This prevents "all-to-all" chaos and makes allowed paths explicit.

### Node Semantics

Typical node groups:
1. Decision strategy / intent mode.
2. Kernel/runtime services.
3. Embedding and provider selection.

Nodes may expose state badges such as:
1. Dirty (local change not yet applied).
2. Conflict / blocked.
3. Restart required.
4. Source tags (for example local vs cloud where applicable).

### Connection Rules

Connections are policy-driven, not free-form.
If a connection is forbidden, the UI should show a rejection reason code.

Examples:
1. `decision_strategy -> intent_mode` allowed.
2. `runtime -> provider` allowed under compatibility constraints.
3. Unsupported combinations are blocked with explicit feedback.

## Local vs Cloud Source Awareness

Where source selection exists (for example embedding/provider domains), the operator should always see whether the active choice is local or cloud:
1. In inspector form fields.
2. On relevant "current" nodes via a small badge/tag.
3. In validation messages when a chosen source has no compatible options.

If a domain is auto-resolved (for example runtime services), avoid misleading "missing" labels. Prefer an explicit `auto` state when user selection is not expected.

## Safe Execution Flow (Plan -> Apply)

Recommended operator flow:
1. Edit values in node or inspector.
2. Run **Plan**.
3. Review compatibility report and reason codes.
4. Apply only valid changes.
5. Confirm restart-required operations when needed.

Key outcomes:
1. `hot_swap` - immediate change.
2. `restart_required` - accepted but needs restart.
3. `rejected` - blocked by policy or compatibility.

## Operator Best Practices

1. Prefer incremental edits instead of large multi-domain flips.
2. Resolve conflicts in the inspector before apply.
3. Treat source labels (local/cloud/auto) as operational truth.
4. Use audit trail after each major apply.
5. Keep frontend i18n parity (PL/EN/DE) for user-facing workflow messages.

## Troubleshooting

### "I changed source to local/cloud but options look wrong"
1. Refresh workflow state.
2. Re-open the node inspector.
3. Check compatibility report for filtering reason.
4. Confirm backend returned options for selected source.

### "Node shows unknown translation key"
1. Missing i18n key for model/provider label.
2. Add key in translation dictionaries.
3. Keep fallback readable (never raw key in final UX).

### "Plan passed but apply needs restart"
This is expected when apply mode is `restart_required`.
The change is valid, but service lifecycle must complete before effect is visible.

## Related Docs

1. `docs/WORKFLOW_CONTROL_PLANE_API.md` - endpoint and schema contract.
2. `docs/OPERATOR_MANUAL.md` - broader daily operations.
3. `docs/FRONTEND_NEXT_GUIDE.md` - UI conventions and frontend context.
