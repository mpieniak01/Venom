# Vast.ai: GPU environment operations

Shared backend service + terminal interface, independent of Venom frontend,
production inference routing and Rider control. Nothing starts at application
boot. Uses existing dependencies; no SDK or global package installation.

## Configuration

Store VAST_API_KEY in the existing .env.dev (SecretStr). From another checkout,
pass --env-file /absolute/path/to/.env.dev. Never copy the key to a rented machine,
startup script, report, argument or another secret store.

Reuse secrets/ssh/vast/connection.json with identity_file and known_hosts pointing
to existing absolute paths. Its public fingerprint must be registered in Vast.
No account keys are created/deleted. Recommended scopes: misc, user_read,
instance_read, instance_write, billing_read; verify permissions per endpoint.

Plans, records and exports live in ignored .venom_runtime/vast, with private
atomic files and a per-plan process lock. Keep them after deletion for billing.
CLI calls the shared Environments service; future adapters must reuse it.

Copy config/cloud/vast/inspect.example.json or ollama.example.json into an ignored
local directory. Replace the image placeholder with a verified immutable digest
compatible with cpu_arch. Ollama also requires an exact model name and digest.
Examples intentionally cannot rent until edited. No engine image is declared a
stable default after the observed CUDA errors. Template hashes are not digests.

- disk_gb: native provider field labeled GB, default 150; the identical value
  goes into search allocated_storage and creation disk. Historical GB/GiB
  ambiguity is not hidden by conversion: inspect actual bytes after allocation.
  Container disk cannot be resized in place.
- min_free_disk_bytes: measured free space required after allocation.
- RAM requirements use native MB fields. CPU and GPU memory are not added;
  GB10 shares physical memory.
- download_gb / upload_gb: explicit decimal-GB transfer budgets.
- duration_minutes: planned rental time including provisioning and downloads.
- Host bandwidth, OS and CUDA declarations are not facts about the container.
- Country codes filter search; unclear response location stays unknown.

Inspect startup only writes a completion marker. Ollama reuses the image tools
and an answering service, starting its own process only when absent. No Docker
inside Docker, drivers, Nginx or Venom installation. Own files are isolated under
/workspace/venom-vast. Existing supervisor/portal configuration is untouched.
Startup is versioned, hashed and locked.

A positive download budget explicitly permits ollama pull at startup/provision;
zero forbids downloads. Free space is checked first. Transfer budgets are estimates,
not enforced traffic caps. Gated/private models are outside this bootstrap profile.

## Host location, link and ranking

Poland is preferred by default (preferred_countries: ["PL"]), with other countries
as fallback. This is a preference, not a hard restriction. countries: ["PL"] or
--country PL restricts the search to Poland. Country codes are normalized.
Preferred countries are queried separately so that a global top 100 does not hide
Polish offers. Queries remain bounded: one global plus at most eight country
queries; rankings describe those candidates, not an exhaustive marketplace scan.

All sort modes put eligible offers first, then preferred countries in their
configured order. Within each group:

- balanced: reliability descending, weakest link direction descending, total cost ascending;
- price: quoted experiment total ascending, reliability, then link;
- network: min(download, upload) descending, reliability, then cost;
- reliability: provider reliability descending, cost, then link.

Use --no-country-preference for a global ranking without the Poland-first group.
Unknown metrics stay unknown and sort after known metrics for that criterion.
Invalid/missing required metrics cannot make an offer eligible. Rank alone never
rents a host and never changes the offer of an existing plan.

Recommended example profiles require at least 500 Mbps download, 200 Mbps upload
and 0.99 reliability, plus verified status. Change these explicit minima if needed.
Reliability is the provider's availability indicator, not customer reviews.
The API contract does not expose a customer-review count or star rating; reports
say user_reviews=not_provided. Verification also does not prove real application
performance, low latency or an uncongested route from the operator.

Network values are Mbps, matching Net Mbps in the maintained official CLI.
The endpoint reference currently labels inet_up/inet_down MB/s inconsistently;
raw fields are preserved and no implicit factor-of-eight conversion is applied.
Disk bandwidth remains MB/s. Country proximity is a preference, not measured RTT.
Host signals in each assessment show country, both link directions and reliability
in percent, alongside provider-declared provenance.

    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort price
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort network --country PL
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort reliability --min-reliability 0.99
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort price --no-country-preference
    python scripts/cloud/vast/vast.py --json plan --profile .venom_runtime/inspect.json --offer OFFER_ID --min-download-mbps 500 --min-upload-mbps 200 --max-hourly 0.50 --max-total 1.00

The same overrides apply to offers, assess and plan. A plan stores its effective
profile, so create rechecks the exact saved minima and hard country restrictions.
Changing a search never silently changes a saved plan.

## Terminal flow

From repository root:

    source .venv/bin/activate
    python scripts/cloud/vast/vast.py --json account
    python scripts/cloud/vast/vast.py --json list
    python scripts/cloud/vast/vast.py --json volumes
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json
    python scripts/cloud/vast/vast.py --json assess --profile .venom_runtime/inspect.json --offer OFFER_ID
    python scripts/cloud/vast/vast.py --json plan --profile .venom_runtime/inspect.json --offer OFFER_ID --max-hourly 0.50 --max-total 1.00 --finish destroy

Offers, assess and plan do not rent. Assessment is eligible/ineligible/unknown,
with missing fields and reasons. Performance remains unknown before measurement.

Inspect the returned plan_id. Plan records the exact offer/host/machine, profile,
image/model digests, startup hash, SSH reference, budgets and finish policy.
Plans expire after ten minutes.

**Create starts a paid rental.** This is the single explicit approval of the plan;
it never silently changes offers or starts a second resource.

    python scripts/cloud/vast/vast.py --json create --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json wait --plan PLAN_ID --timeout 120
    python scripts/cloud/vast/vast.py --json inspect --plan PLAN_ID --accept-new-host-key
    python scripts/cloud/vast/vast.py --json status --plan PLAN_ID

Create rechecks capacity, price, budget, registered SSH key and startup hash.
Price increases require a new plan. Mutations are never automatically retried.
Timeout/malformed creation response leaves outcome_unknown: run reconcile,
including later if visibility is delayed. Empty listings do not justify another
rental. A lost observation does not mean a resource was stopped or destroyed.

First SSH trust is explicit through --accept-new-host-key (OpenSSH TOFU).
Compare the fingerprint independently when possible. Later calls use strict
known hosts; changed keys fail. Agent forwarding and shared config are disabled.
SSH coordinates come from the API; model ports are not exposed publicly.

For an Ollama profile:

    python scripts/cloud/vast/vast.py --json provision --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json ready --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json benchmark --plan PLAN_ID > .venom_runtime/run-a.json
    python scripts/cloud/vast/vast.py --json compare .venom_runtime/run-a.json .venom_runtime/run-b.json

Provision explicitly repeats the same startup, including approved downloads.
Ready/benchmark never pull, install or restart managed services. Temporary private
SSH tunnels close on success/failure. Readiness checks installed digest and actual
generation. The bounded suite covers natural first load, three short cases, two
medium, two long, two concurrent requests, JSON, a synthetic image and a fictitious
tool that is never executed. Reports preserve context, engine/model versions,
prompt hashes, TTFT, prefill/decode and errors. OS/prefix cache may already be warm.
A CUDA error rejects this stack, not the GPU hardware. Incomplete runs are inconclusive.
Different suites/engines/models/settings are explicitly marked non-comparable.

## Costs and cleanup

    python scripts/cloud/vast/vast.py --json costs --plan PLAN_ID --from-utc 2026-10-16T00:00:00+00:00 --to-utc 2026-10-17T00:00:00+00:00
    python scripts/cloud/vast/vast.py --json export --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json stop --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json start --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json destroy --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json reconcile --plan PLAN_ID

Amounts use Decimal and separate:

1. Quote: search totalHour/dph_total for selected disk, plus explicit USD/TB
   transfer rates. Never add disk twice. Ambiguous legacy rates stay unknown.
2. Estimate: continuous quoted exposure since submission, not measured usage;
   may overestimate stopped time and does not prove a final bill.
3. Provider reported: paginated charges, UTC window, source=instance-ID.
   Sum parent amounts once, not parent plus nested items.

Invoices describe payments, not resource charges. Account credit and balance
are distinct fields. Credit changes cannot attribute one experiment's costs.
If Vast reports that host accounts cannot retrieve instance charges, or denies\nbilling access, the report is unavailable while quote/estimate remain available.\nThis is not a zero bill. Missing charges are pending. Present charges are provisional: provider
finalization timing is unknown.

Stop retains billable storage. Destroy requires a saved export and a subsequent
read to confirm removal; journal remains. Volumes is read-only inventory.
Cleanup never deletes unrelated instances, shared volumes or SSH keys.

    python scripts/cloud/vast/vast.py --json cleanup --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json monitor --plan PLAN_ID --timeout 600

Cleanup exports and uses the selected stop/destroy policy. Manual needs an
explicit operator action. Monitor is a bounded foreground process: on planned
duration expiry, it executes that policy. It is not a server-side TTL or hard
billing cap. WSL exit, network failure or early monitor exit may leave a paid
resource running. Confirm cleanup in the provider console. No daemon is installed.

## Validation

Tests use HTTP/SSH fixtures and never rent: ambiguous creation, price drift,
v0/v1 pagination, 403/410/429, stopped storage, delayed deletion, startup/backend
errors and partial billing. Live creation/SSH/bootstrap/deletion needs a separately
approved paid acceptance run. Read success does not verify write permissions.

Fixed REST origin: https://console.vast.ai. Redirects never forward Authorization.
Exports use allowlists: private SSH fields, instance tokens and environment are
excluded. JSON output has ok/result or ok/error; summaries support PL/EN/DE.
Local reports may include private host coordinates; sanitize before publication.

## Primary references

- [Authentication](https://docs.vast.ai/api-reference/authentication)
- [Offers and native units](https://docs.vast.ai/api-reference/search/search-offers)
- [Create/startup](https://docs.vast.ai/api-reference/instances/create-instance)
- [Instance pagination](https://docs.vast.ai/api-reference/instances/show-instances)
- [Charges](https://docs.vast.ai/api-reference/billing/show-charges)
- [Volume inventory](https://docs.vast.ai/api-reference/volumes/list-volumes)
- [Billing](https://docs.vast.ai/guides/reference/billing)
\n- [Official CLI network labels](https://github.com/vast-ai/vast-cli/blob/master/vast.py)\n- [Provider verification](https://docs.vast.ai/host/verification-stages)\n
