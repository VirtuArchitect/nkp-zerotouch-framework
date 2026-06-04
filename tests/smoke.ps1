param(
    [string]$Config = ".\configs\environments\connected.example.yaml"
)

$ErrorActionPreference = "Stop"
$null = [scriptblock]::Create((Get-Content -Raw .\scripts\zt.ps1))
.\scripts\zt.ps1 validate -Config $Config
.\scripts\zt.ps1 prepare -Config $Config
.\scripts\zt.ps1 generate -Config $Config
.\scripts\zt.ps1 registry -Config $Config
.\scripts\zt.ps1 deploy -Config $Config
.\scripts\zt.ps1 verify -Config $Config
.\scripts\zt.ps1 runs -Config $Config
Write-Host "PowerShell smoke test completed."
