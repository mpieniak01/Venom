param(
    [string]$Distribution = 'Ubuntu-Venom',
    [string]$LinuxRepository = '/home/ubuntu/venom'
)
$ErrorActionPreference = 'Stop'
$credential = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY', 'Process')
if ([string]::IsNullOrWhiteSpace($credential)) {
    $credential = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY', 'User')
}
if ([string]::IsNullOrWhiteSpace($credential)) { throw 'OPENROUTER_API_KEY is not configured on Windows.' }
try {
    $credential | & wsl.exe -d $Distribution -u ubuntu --cd $LinuxRepository -- .venv/bin/python scripts/openrouter_credential_bridge.py
    if ($LASTEXITCODE -ne 0) { throw 'OpenRouter credential bridge failed.' }
} finally {
    $credential = $null
}
