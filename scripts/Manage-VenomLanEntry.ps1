#Requires -Version 5.1
<#
.SYNOPSIS
Manage one opt-in Private LAN HTTP entry to the configured WSL distribution.
.DESCRIPTION
Inspect is read-only. Apply/Reconcile/Remove require an elevated PowerShell.
Only mappings recorded in this entry's state are replaced/removed. Other portproxy
and firewall entries are never adopted, changed or deleted. No WSL global setting
is changed. Run Reconcile from an operator-owned scheduled task after DHCP/WSL changes.
#>
[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Apply', 'Reconcile', 'Remove')]
    [string]$Mode = 'Inspect',
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]{1,64}$')]
    [string]$Distribution,
    [Parameter(Mandatory = $true)]
    [string]$InterfaceAlias,
    [ValidatePattern('^[A-Za-z0-9-]{1,40}$')]
    [string]$EntryName = 'panel',
    [ValidateRange(1, 65535)]
    [int]$ListenPort = 3300,
    [ValidateRange(1, 65535)]
    [int]$TargetPort = 3300,
    [ValidateSet('localhost_relay', 'wsl_ip')]
    [string]$TargetMode = 'localhost_relay',
    [ValidatePattern('^[A-Za-z0-9._:-]{0,64}$')]
    [string]$ExpectedPeerId = '',
    [string]$StateFile = '',
    [switch]$RegisterTask,
    [switch]$Json
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$owner = 'Venom HTTP LAN entry v1'
$ruleName = "Venom.HttpLan.$EntryName"
$taskName = "Venom-HttpLan-$EntryName"
if (-not $StateFile) {
    $StateFile = Join-Path $env:LOCALAPPDATA "Venom\lan-entry\$EntryName.json"
}
$statePath = [IO.Path]::GetFullPath($StateFile)
$state = $null
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state.owner -ne $owner -or $state.entry_name -ne $EntryName) {
        throw 'State ownership mismatch. Choose this entry own state file.'
    }
}
function Invoke-PortProxy {
    param([string[]]$Arguments)
    $nativeOutput = & netsh.exe interface portproxy @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "netsh failed: $nativeOutput" }
}
function Get-PortMappings {
    $nativeOutput = & netsh.exe interface portproxy show v4tov4
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect portproxy mappings.' }
    $rows = @()
    foreach ($line in $nativeOutput) {
        if ($line -match '^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)\s*$') {
            $rows += [pscustomobject]@{
                listen_address = $Matches[1]; listen_port = [int]$Matches[2]
                target_address = $Matches[3]; target_port = [int]$Matches[4]
            }
        }
    }
    return $rows
}
function Test-SameMapping {
    param($First, $Second)
    return ($First.listen_address -eq $Second.listen_address -and
        $First.listen_port -eq $Second.listen_port -and
        $First.target_address -eq $Second.target_address -and
        $First.target_port -eq $Second.target_port)
}
function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Apply/Reconcile/Remove require elevated PowerShell; Inspect remains read-only.'
    }
}
function Remove-RecordedMapping {
    param($Recorded, $Mappings)
    $existing = @($Mappings | Where-Object { $_.listen_address -eq $Recorded.listen_address -and $_.listen_port -eq $Recorded.listen_port })
    if ($existing.Count -gt 0 -and -not (Test-SameMapping $existing[0] $Recorded)) {
        throw 'Recorded mapping changed outside this helper; refusing to remove it.'
    }
    if ($existing.Count -gt 0) {
        Invoke-PortProxy -Arguments @('delete', 'v4tov4', "listenaddress=$($Recorded.listen_address)", "listenport=$($Recorded.listen_port)")
    }
}
$mappings = @(Get-PortMappings)
$ownedRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($ownedRule -and $ownedRule.Description -ne $owner) {
    throw 'Firewall rule ownership mismatch.'
}
if ($Mode -eq 'Remove') {
    Assert-Admin
    if ($state) {
        Remove-RecordedMapping $state.mapping $mappings
        if ($ownedRule) { Remove-NetFirewallRule -Name $ruleName }
        $ownedTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($ownedTask) {
            if ($ownedTask.Description -ne $owner) { throw 'Scheduled task ownership mismatch.' }
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
        Remove-Item -LiteralPath $statePath
    }
    Write-Output 'Removed recorded Venom HTTP LAN entry only.'
    return
}
$profile = @(Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias)
if ($profile.Count -ne 1 -or $profile[0].NetworkCategory -ne 'Private') {
    throw 'Select one active Private interface; this helper never changes its network category.'
}
$addresses = @(Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 |
    Where-Object {
        $_.AddressState -eq 'Preferred' -and
        ($_.IPAddress -like '10.*' -or $_.IPAddress -like '192.168.*' -or
            ($_.IPAddress -match '^172\.(1[6-9]|2[0-9]|3[01])\.'))
    })
if ($addresses.Count -ne 1) { throw 'Interface must have exactly one preferred RFC1918 IPv4 address.' }
$listenAddress = $addresses[0].IPAddress
$targetAddress = '127.0.0.1'
if ($TargetMode -eq 'wsl_ip') {
    $running = @(& wsl.exe --list --running --quiet) -replace "`0", ''
    if (-not ($running | Where-Object { $_.Trim() -eq $Distribution })) {
        throw 'Configured WSL distribution must already be running; no implicit start.'
    }
    $wslAddresses = & wsl.exe -d $Distribution -- hostname -I
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect configured WSL address.' }
    $ipv4 = @($wslAddresses.Trim().Split(' ') | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' })
    if ($ipv4.Count -ne 1) { throw 'Ambiguous WSL IPv4; inspect the configured distribution.' }
    $targetAddress = $ipv4[0]
}
$desired = [pscustomobject]@{
    listen_address = $listenAddress; listen_port = $ListenPort
    target_address = $targetAddress; target_port = $TargetPort
}
$conflicts = @($mappings | Where-Object {
    $_.listen_port -eq $ListenPort -and ($_.listen_address -eq $listenAddress -or $_.listen_address -eq '0.0.0.0')
})
$mappingConflict = $false
foreach ($mapping in $conflicts) {
    if (-not $state -or -not (Test-SameMapping $mapping $state.mapping)) {
        $mappingConflict = $true
    }
}
$identity = $null
$identityError = $null
try {
    $identity = Invoke-RestMethod -Uri "http://$targetAddress`:$TargetPort/api/v1/transport/identity" -TimeoutSec 5 -Headers @{ Host = "127.0.0.1:$TargetPort" }
    if ($identity.protocol_version -ne 1 -or $identity.service_role -ne 'venom' -or
        $identity.operator_access -ne 'trusted_lan' -or
        ($ExpectedPeerId -and $identity.peer_id -ne $ExpectedPeerId)) {
        throw 'Entry identity/profile mismatch.'
    }
} catch { $identityError = $_.Exception.Message }
$ipHelper = Get-Service -Name iphlpsvc
$summary = [pscustomobject]@{
    mode = $Mode; owner = $owner; distribution = $Distribution; target_mode = $TargetMode
    desired_mapping = $desired; owned_mapping = $(if ($state) { $state.mapping } else { $null })
    firewall_rule = $ruleName; firewall_profile = 'Private'; remote_scope = 'LocalSubnet'
    interface_alias = $InterfaceAlias; ip_helper_status = [string]$ipHelper.Status
    identity_verified = ($null -ne $identity -and -not $identityError); identity_error = $identityError
    unmanaged_mappings = @($mappings | Where-Object { -not $state -or -not (Test-SameMapping $_ $state.mapping) })
    state_file = $statePath; mapping_conflict = $mappingConflict
}
if ($Mode -eq 'Inspect') {
    if ($Json) { $summary | ConvertTo-Json -Depth 6 } else { $summary | Format-List }
    return
}
Assert-Admin
if ($mappingConflict) { throw 'Port is owned by an existing unmanaged mapping; this helper never adopts or replaces it.' }
if (-not $ExpectedPeerId) { throw 'Apply/Reconcile require ExpectedPeerId from explicit pairing.' }
if ($identityError -or -not $identity) { throw "Refusing exposure: $identityError" }
if ($ipHelper.Status -ne 'Running') {
    throw 'IP Helper service is not running. Diagnose it explicitly; this helper does not change service configuration.'
}
$mutex = New-Object Threading.Mutex($false, "Local\Venom.HttpLan.$ListenPort")
if (-not $mutex.WaitOne(0)) { throw 'Another owner is reconciling this entry.' }
try {
    # Check again under the port lock; concurrent entries may have changed ownership.
    $currentMappings = @(Get-PortMappings)
    foreach ($mapping in $currentMappings) {
        if ($mapping.listen_port -eq $ListenPort -and
            ($mapping.listen_address -eq $listenAddress -or $mapping.listen_address -eq '0.0.0.0') -and
            (-not $state -or -not (Test-SameMapping $mapping $state.mapping))) {
            throw 'Mapping ownership changed during reconciliation.'
        }
    }
    if ($RegisterTask) {
        if ($PSCommandPath.StartsWith('\\wsl.localhost\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Copy the reviewed helper to a stable Windows path before registering a task.'
        }
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($existingTask -and $existingTask.Description -ne $owner) { throw 'Scheduled task ownership mismatch.' }
        if ($InterfaceAlias.Contains('"') -or $statePath.Contains('"')) { throw 'Invalid task argument.' }
    }
    # State is written before mutation so an interrupted apply remains removable.
    $stateDirectory = Split-Path -Parent $statePath
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $newState = [ordered]@{ owner = $owner; entry_name = $EntryName; mapping = $desired }
    if ($state -and -not (Test-SameMapping $state.mapping $desired)) {
        Remove-RecordedMapping $state.mapping $currentMappings
    }
    $newState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
    Invoke-PortProxy -Arguments @('add', 'v4tov4', "listenaddress=$listenAddress", "listenport=$ListenPort", "connectaddress=$targetAddress", "connectport=$TargetPort")
    if ($ownedRule) { Remove-NetFirewallRule -Name $ruleName }
    New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Description $owner -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ListenPort -LocalAddress $listenAddress -RemoteAddress LocalSubnet -Profile Private -InterfaceAlias $InterfaceAlias | Out-Null
    if ($RegisterTask) {
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($existingTask -and $existingTask.Description -ne $owner) { throw 'Scheduled task ownership mismatch.' }
        $taskArguments = "-NoProfile -NonInteractive -File `"$PSCommandPath`" -Mode Reconcile -Distribution `"$Distribution`" -InterfaceAlias `"$InterfaceAlias`" -EntryName `"$EntryName`" -ListenPort $ListenPort -TargetPort $TargetPort -TargetMode $TargetMode -ExpectedPeerId `"$ExpectedPeerId`" -StateFile `"$statePath`""
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArguments
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $taskName -Description $owner -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    }
    if ($Json) { $summary | ConvertTo-Json -Depth 6 } else { Write-Output 'Applied owned Private LAN entry. Verify its actual listener and access from a separate LAN client.' }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
