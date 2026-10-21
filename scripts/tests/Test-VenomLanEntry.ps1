#Requires -Version 5.1
# Contract tests use only fixtures: no firewall, netsh, WSL or HTTP mutations.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'Manage-VenomLanEntry.ps1'
$taskTempRoot = Join-Path ([IO.Path]::GetTempPath()) ("venom-lan-test-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskTempRoot | Out-Null
$global:VenomLanFixtureRows = @()
$global:VenomLanFixtureIdentity = $true
$global:VenomLanFixtureWrites = 0
$global:VenomLanFixtureAddress = '192.168.50.10'
$global:VenomLanFixtureRule = $null
function netsh.exe {
    $global:LASTEXITCODE = 0
    if ($args -join ' ' -eq 'interface portproxy show v4tov4') {
        Write-Output $global:VenomLanFixtureRows
        return
    }
    $global:VenomLanFixtureWrites += 1
    $values = @{}
    foreach ($value in $args) {
        if ($value -like '*=*') {
            $pair = $value.Split('=', 2)
            $values[$pair[0]] = $pair[1]
        }
    }
    $prefix = "$($values.listenaddress) $($values.listenport) "
    $global:VenomLanFixtureRows = @($global:VenomLanFixtureRows | Where-Object { -not $_.StartsWith($prefix) })
    if ($args[2] -eq 'add') {
        $global:VenomLanFixtureRows += "$prefix$($values.connectaddress) $($values.connectport)"
    } elseif ($args[2] -ne 'delete') { throw 'Unexpected fixture native command.' }
}
function New-Object {
    param([string]$TypeName, [object[]]$ArgumentList)
    if ($TypeName -eq 'Security.Principal.WindowsPrincipal') {
        # This object is only a fixture. Every network mutation below is mocked.
        $principal = [pscustomobject]@{}
        $principal | Add-Member -MemberType ScriptMethod -Name IsInRole -Value { param($Role) return $true }
        return $principal
    }
    return Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
}
function Get-NetFirewallRule { param($Name, $ErrorAction) return $global:VenomLanFixtureRule }
function Remove-NetFirewallRule { param($Name) $global:VenomLanFixtureRule = $null }
function New-NetFirewallRule {
    param($Name, $DisplayName, $Description, $Direction, $Action, $Protocol, $LocalPort, $LocalAddress, $RemoteAddress, $Profile, $InterfaceAlias)
    if ($Profile -ne 'Private' -or $RemoteAddress -ne 'LocalSubnet') { throw 'Unsafe fixture firewall scope.' }
    $global:VenomLanFixtureRule = [pscustomobject]@{ Name = $Name; Description = $Description }
}
function Get-ScheduledTask { param($TaskName, $ErrorAction) return $null }
function Get-NetConnectionProfile { param($InterfaceAlias) return [pscustomobject]@{ NetworkCategory = 'Private' } }
function Get-NetIPAddress { param($InterfaceAlias, $AddressFamily) return [pscustomobject]@{ AddressState = 'Preferred'; IPAddress = $global:VenomLanFixtureAddress } }
function Get-Service { param($Name) return [pscustomobject]@{ Status = 'Running' } }
function Invoke-RestMethod {
    param($Uri, $TimeoutSec, $Headers)
    if (-not $global:VenomLanFixtureIdentity) { throw 'Fixture identity unavailable.' }
    return [pscustomobject]@{ protocol_version = 1; service_role = 'venom'; peer_id = 'fixture-peer'; operator_access = 'trusted_lan' }
}
function Assert-Equal {
    param($Actual, $Expected, $Message)
    if ($Actual -ne $Expected) { throw "$Message Expected=$Expected Actual=$Actual" }
}
function Inspect-Fixture {
    param([string]$StateFile)
    return (& $scriptPath -Mode Inspect -Distribution Fixture-WSL -InterfaceAlias Fixture-LAN -StateFile $StateFile -ExpectedPeerId fixture-peer -Json | ConvertFrom-Json)
}
try {
    $stateFile = Join-Path $taskTempRoot 'entry.json'
    $result = Inspect-Fixture $stateFile
    Assert-Equal $result.identity_verified $true 'Paired identity is verified.'
    Assert-Equal $result.mapping_conflict $false 'No conflict on empty fixture.'
    Assert-Equal $result.desired_mapping.target_address '127.0.0.1' 'Relay avoids WSL target lookup.'
    Assert-Equal (Test-Path -LiteralPath $stateFile) $false 'Inspect must not create state.'
    $global:VenomLanFixtureRows = @('192.168.50.10 3300 127.0.0.1 3300', '0.0.0.0 8080 172.20.0.8 8080')
    $result = Inspect-Fixture $stateFile
    Assert-Equal $result.mapping_conflict $true 'Unmanaged matching entry remains a conflict.'
    Assert-Equal @($result.unmanaged_mappings).Count 2 'Unrelated entry remains visible.'
    $state = @{ owner = 'Venom HTTP LAN entry v1'; entry_name = 'panel'; mapping = @{
        listen_address = '192.168.50.10'; listen_port = 3300; target_address = '127.0.0.1'; target_port = 3300
    } }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8
    $result = Inspect-Fixture $stateFile
    Assert-Equal $result.mapping_conflict $false 'Recorded own mapping can be reconciled.'
    Assert-Equal @($result.unmanaged_mappings).Count 1 'Unrelated mapping never becomes owned.'
    $global:VenomLanFixtureIdentity = $false
    $result = Inspect-Fixture $stateFile
    Assert-Equal $result.identity_verified $false 'Unavailable identity is reported without exposure.'
    Assert-Equal $global:VenomLanFixtureWrites 0 'Inspect performs no native writes.'
    # Apply/Reconcile/Remove below use a fake admin object and fake native cmdlets.
    $global:VenomLanFixtureIdentity = $true
    $global:VenomLanFixtureRows = @('0.0.0.0 8080 172.20.0.8 8080')
    Remove-Item -LiteralPath $stateFile
    & $scriptPath -Mode Apply -Distribution Fixture-WSL -InterfaceAlias Fixture-LAN -StateFile $stateFile -ExpectedPeerId fixture-peer | Out-Null
    Assert-Equal (Test-Path -LiteralPath $stateFile) $true 'Apply records ownership.'
    Assert-Equal $global:VenomLanFixtureWrites 1 'Apply creates one fixture mapping.'
    $global:VenomLanFixtureAddress = '192.168.50.11'
    & $scriptPath -Mode Reconcile -Distribution Fixture-WSL -InterfaceAlias Fixture-LAN -StateFile $stateFile -ExpectedPeerId fixture-peer | Out-Null
    $recorded = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    Assert-Equal $recorded.mapping.listen_address '192.168.50.11' 'DHCP reconcile updates owned address.'
    Assert-Equal $global:VenomLanFixtureWrites 3 'Reconcile deletes old and adds new only.'
    Assert-Equal ($global:VenomLanFixtureRows -contains '0.0.0.0 8080 172.20.0.8 8080') $true 'Foreign entry remains.'
    & $scriptPath -Mode Remove -Distribution Fixture-WSL -InterfaceAlias Fixture-LAN -StateFile $stateFile | Out-Null
    Assert-Equal (Test-Path -LiteralPath $stateFile) $false 'Remove clears owned state.'
    Assert-Equal $global:VenomLanFixtureWrites 4 'Remove deletes owned mapping only.'
    Assert-Equal $global:VenomLanFixtureRows.Count 1 'Foreign entry survives rollback.'
    Assert-Equal ($null -eq $global:VenomLanFixtureRule) $true 'Owned firewall fixture is removed.'
    Write-Output 'PASS: Windows LAN inspect, pairing, ownership, DHCP reconcile and rollback (all native operations mocked).'
} finally {
    # Resolve the exact fixture directory before removing only its known files.
    $resolved = [IO.Path]::GetFullPath($taskTempRoot)
    if (-not $resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Unexpected fixture path.'
    }
    $fixtureFile = Join-Path $resolved 'entry.json'
    if (Test-Path -LiteralPath $fixtureFile) { Remove-Item -LiteralPath $fixtureFile }
    Remove-Item -LiteralPath $resolved
    Remove-Variable -Name VenomLanFixtureRows,VenomLanFixtureIdentity,VenomLanFixtureWrites,VenomLanFixtureAddress,VenomLanFixtureRule -Scope Global
}
