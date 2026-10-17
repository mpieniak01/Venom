# Integration inventory

Configuration > Integrations and nodes uses GET /api/v1/system/api-map, schema
version 2. Existing internal_connections and external_connections remain for
compatibility. The integrations array describes core APIs, optional modules,
external providers and their resources. Local module manifests remain visible even
when their API has not been registered. It does not grant robot motion consent.

The default view shows this environment; All supported includes integrations known
from core declarations and configured module manifests, including unconfigured
services. It does not discover arbitrary uninstalled modules or scan a marketplace.
The Services, Parameters, Audit and Permissions tabs keep their existing behavior.

Configuration, module activation, API connectivity and resource state are separate.
A registered route or present API key never establishes healthy connectivity.
Unknown resource totals are null. Confirmed empty inventories have total 0.
Services without nodes are marked not applicable. Each observation identifies its
source and time; historical Vast records are not current provider state.

The map reads local observations only. It never starts a camera, model, robot or
rental. The explicit Vast check POST /api/v1/system/integrations/vast/probe uses
the existing client's account and instance GET operations. It never creates,
starts, stops or destroys resources. Checks are coalesced, have a bounded wait
and a short cooldown. Credentials stay on the server; no account balance or
private provider response is returned. Provider observations older than 60 seconds
are marked stale and do not establish current totals. Config changes invalidate
the credential-specific cached observation. Other provider checks remain separate.

The frontend refreshes every 10 seconds while visible, with one request in flight.
It retains selection and previous data when refreshing fails. Configuration errors
and unavailable optional modules are isolated; strict module authoring validation
continues to report invalid manifests. A module failing data policy is never loaded.

## Optional observation provider

Existing modules need no changes. A loaded module may opt into
backend.integration_provider_import in module.json, in package.module:function
format. The async function receives the application and returns
venom_core.api.schemas.integrations.IntegrationObservation or matching JSON:

```json
{
  "observed_at": "2026-10-17T12:00:00+00:00",
  "connectivity": "unknown",
  "resources_complete": false,
  "resources": []
}
```

Resource fields are id, label, kind, state and optional observed_at. Kinds are
robot, worker, instance, runtime or device; states are connected, offline, stale
or unverified. The host namespaces IDs, validates the result, isolates exceptions
and bounds its wait to 0.5 s. Results are reused for 10 seconds. Complete totals
require an observation timestamp; observations older than 60 s are stale.

Hooks must reuse existing observations, perform no control actions and cooperate
with cancellation. They must not change the active device, ARM, session or camera.
They must not include secrets in labels or IDs. Without a hook the host shows the
module's activation metadata and explicitly unknown device state. Full Rider
observations belong to the independent module increment, not the core inventory.

Optional router startup and cleanup have a two-second host wait. A failure marks
that module unavailable and its routes return a controlled 503; unrelated core
routes remain available. A shared module router retains its original lifecycle
context for other host applications. Core application errors are not swallowed.

## Configuration navigation

/config?tab=integrations selects the inventory. The previous tab=apiMap and
section= parameters remain accepted. integration, scope, visibility and q retain
the selected integration, filters and search in the URL. Unknown tabs fall back
to Services; missing integrations are reported instead of showing a healthy
replacement. Browser Back restores the previous selection.

Integration configuration keys link to the existing Parameters editor via
parameter=KEY_NAME. Search covers names and descriptions, never secret values.
Unavailable keys have an explicit message; this change does not expand the
backend's editable-key allowlist. Draft parameter edits survive local tab switches;
a full page reload still discards unsaved edits. Save, Reset, service profiles,
Audit and Permissions use the existing endpoints and semantics. Search results
open their sections automatically.

The older ENABLE_IOT_BRIDGE / RIDER_PI_* bridge remains independent of the Rider
module and is still consumed by core bootstrap. It is not migrated or removed.
Cockpit links use the same inventory IDs and observations, not service-name
heuristics. Models link to the runtime entry; optional modules expose only the
navigation declared in their manifest. Hidden tabs do not poll the inventory.

Optional resource context includes configuration, selected, mode (demo/device),
source, reason_code and supported/reported/available capabilities. Missing
capability evidence is null. Being online never grants motion consent. A complete
configured-device inventory can establish a total while the active count remains
unknown until every resource state is observed. The optional observation-level
configuration and reason_code distinguish missing devices from invalid config.
Old hooks omitting these additive fields continue to work.

Release core inventory 263 first, navigation/context 264 next, then the optional
Rider observation adapter 263R. Older core ignores the opt-in manifest hook and
keeps normal Rider controls working; the adapter is not imported on that path.
