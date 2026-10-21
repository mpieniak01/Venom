# Trusted HTTP LAN entry

The default transport profile remains `secure`. Enable `trusted_lan` only for
an explicitly paired installation on a trusted Private LAN. HTTP does not encrypt
tokens or authenticate a peer cryptographically. Existing route tokens, deadlines,
size limits, environment mutation policy and command deduplication still apply.

## Contract and configuration

The passive unauthenticated `GET /api/v1/transport/identity` returns:

```json
{"protocol_version":1,"peer_id":"0123456789abcdef0123456789abcdef","service_role":"venom","operator_access":"trusted_lan"}
```

The v1 peer ID is a UUID represented by exactly 32 lowercase hexadecimal digits,
without hyphens. The installation creates its peer ID once in `data/transport/identity.json`, under
the existing `STORAGE_PREFIX` namespace. `VENOM_TRANSPORT_IDENTITY_FILE` can point
to an existing persistent location. Keep it across restarts and IP changes.
A corrupt, oversized or symlink identity is rejected, never silently replaced.
Read identity before sending a peer token and compare the explicitly paired
`expected_peer_id`; a boot/session ID is not an installation ID.

Configure the same values for API and the frontend launcher:

```dotenv
VENOM_OPERATOR_ACCESS=trusted_lan
VENOM_LAN_ORIGINS=http://localhost:3300,http://127.0.0.1:3300,http://venom-host:3300
API_PROXY_TARGET=http://127.0.0.1:8800
```

Origins are exact, without trailing slash, credentials, paths or wildcards.
Add only names/IPs actually used by operators. Names here are examples. Qualify
the router DNS name from Windows, WSL, Pi and the phone; do not assume `.local`
works on all four. The API listener stays private; publish only the shared panel
entry. Never expose port 8800 through Windows portproxy or another relay.

The standard `npm run dev`, `dev:turbo` and `start` use
`scripts/serve-with-proxy.mjs`. It binds the configured panel port, starts Next
on a private ephemeral loopback port, and streams `/api/*` and `/ws/*` directly to
`API_PROXY_TARGET`. Next frontend rewrites are no longer the proxy. Keep this
entry in production; do not publish the private Next child listener.
In development Next allowedDevOrigins contains only hostnames from explicit
VENOM_LAN_ORIGINS in trusted_lan, without wildcards, covering fonts and HMR.

`NEXT_PUBLIC_TRANSPORT_PROFILE` is derived from `VENOM_OPERATOR_ACCESS` by Next
configuration. Set the profile during a production build as well as startup.
In LAN mode browser API calls use relative URLs, and event/audio WS use the
panel origin even if an old public API/WS URL remains configured. The server API
fallback is port 8800. `VENOM_PROXY_MAX_BODY_BYTES` defaults to 64 MiB; both declared
and chunked request bodies are bounded without buffering the whole upload.

## Operator access and localhost administration

The entry removes supplied forwarded/client-identity headers and writes its own
transport metadata. The API accepts that metadata only from its loopback proxy.
Unknown Host/Origin and public source addresses are rejected in LAN mode.
MJPEG, SSE and WS are streamed with backpressure and upstream cancellation;
JPEG is not transcoded. No POST/job/ARM/movement is retried by this proxy.

Windows portproxy loses the original TCP client address. Therefore **every
request through a shared LAN entry, including localhost:3300, is operator traffic**.
It cannot use configuration, backups or other localhost-only administration.
Use the unexposed local API for administration. Host/Origin spoofing and a supplied
`X-Forwarded-For: 127.0.0.1` never turn the shared entry into an administrator.

Optional modules can import
`venom_core.api.transport_access.require_operator_request(request)` for explicit
operator admission. Keep their existing token and environment mutation guards.
Unmigrated localhost-only operations remain blocked through the shared entry;
this setting does not grant global remote administration.

Public frontend ABI:

```ts
import { createBrowserUuid, getMicrophoneCapability } from "@/lib/optional-modules/transport";
```

The UUID helper preserves RFC 4122 v4 format using CSPRNG `getRandomValues` when
HTTP lacks `randomUUID`; it never uses `Math.random`. Browser microphone capture
needs HTTPS or localhost. On HTTP LAN the voice UI shows that capability limit
in PL/EN/DE and disables browser recording; panels, robot JPEG/MJPEG and the
separate device audio path remain usable.

## Managed Windows / WSL NAT exposure

Run `scripts/Manage-VenomLanEntry.ps1` in Windows PowerShell. It does not change
global WSL networking, restart services, scan the subnet or install anything.
Choose the existing distribution and the active **Private** adapter explicitly.
`Inspect` is read-only:

```powershell
.\scripts\Manage-VenomLanEntry.ps1 -Mode Inspect -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi -ExpectedPeerId 0123456789abcdef0123456789abcdef -Json
```

The preferred `TargetMode localhost_relay` forwards to the verified Windows
localhost relay, avoiding changes to WSL listeners and target IP after a WSL
restart. If that relay is unavailable, `-TargetMode wsl_ip` resolves only the
configured, already-running distribution and requires a reachable WSL listener.
The helper refuses ambiguous addresses and verifies identity, role, version,
profile and the expected peer before exposure.

`Apply`, `Reconcile`, `Remove` and task registration require an elevated
PowerShell. A successful Inspect is not an elevation or a successful LAN test.
An existing unmanaged mapping, including a matching old mapping, is a conflict;
review it explicitly outside this helper. Unrelated mappings/rules are preserved.
The helper never starts IP Helper or changes a network category implicitly.

```powershell
.\scripts\Manage-VenomLanEntry.ps1 -Mode Apply -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi -ExpectedPeerId 0123456789abcdef0123456789abcdef
.\scripts\Manage-VenomLanEntry.ps1 -Mode Reconcile -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi -ExpectedPeerId 0123456789abcdef0123456789abcdef
.\scripts\Manage-VenomLanEntry.ps1 -Mode Remove -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi
```

State defaults to `%LOCALAPPDATA%\Venom\lan-entry\panel.json`. Ownership is scoped
by `EntryName`, exact state mapping and a named firewall rule. The rule permits
only the configured local address/interface, TCP port, Private profile and
LocalSubnet clients. Reconcile updates a recorded LAN address after DHCP, and
the target WSL IP when using `wsl_ip`. It never removes an altered foreign mapping.

For automatic reconciliation, keep a reviewed copy of this script at a stable
Windows path and use `-RegisterTask` with Apply/Reconcile. It registers one
current-user, elevated, interactive task every minute with overlapping runs
disabled. The task does no application work and opens nothing until the paired
LAN-profile identity is reachable. Remove unregisters only this owned task.
Keep the same StateFile/EntryName when reconciling or rolling back.

Verify an actual listening Windows socket, then identity/UI from a separate
LAN client by the stable name. Check PC localhost, PC LAN, phone, Pi compute,
fresh MJPEG/SSE, real WS and spoofed headers. Reconcile after a controlled LAN or
WSL address change and measure recovery; mock success is not physical acceptance.
A tab opened at an old numeric IP must be reopened by the stable name.

## Rollback

Stop exposing only the recorded LAN entry with Remove, restore the previous
transport URLs/profiles, and reconnect with new sessions. Preserve identity,
token TTLs, operator selections and storage. Do not replay pending commands,
start a model/camera or re-arm a robot as part of reconnect.
