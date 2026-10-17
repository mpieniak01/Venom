# Configuration integration topology

Open `/config?tab=topology` to inspect Venom, integration APIs/modules, and their
inventoried resources. The existing **Integrations and nodes** tab remains the
configuration and connection-detail entry point.

- Edges express inventory ownership, not measured traffic or physical networking.
- Local/LAN integrations appear left of Venom; cloud integrations appear right.
  Only internal APIs collapse into the core group. Modules remain visible.
- IDs establish ownership and selection; matching names never create edges.
- Environment visibility and **All supported** use the existing inventory filter.
- Four resources per integration appear initially. **Show more resources** adds
  eight at a time. The text list provides equivalent keyboard selection.
- Configuration, activation and connectivity remain independent. Observation
  timestamps and age relative to the inventory snapshot identify old evidence.
  Failed refreshes retain previous inventory and display a warning.
- Missing observations, incomplete lists and observed zero counts remain distinct.
- The view uses the shared inventory subscription and its existing refresh cycle.
  It does not probe integrations, start services, rent instances or control robots.

Pan and zoom are local view state; polling preserves them. Wheel scrolling does
not zoom the canvas. Use the translated zoom and fit controls explicitly. Nodes
and edges cannot be dragged, reconnected or deleted. Enter/Space selects a focused
node; the text list offers the same selection without navigating the canvas.

`integration` and optional validated `resource` query parameters retain selection
across reload and browser history. Removed IDs produce a local explanation.
Renderer/loading failures are isolated with a link back to the integration list.
