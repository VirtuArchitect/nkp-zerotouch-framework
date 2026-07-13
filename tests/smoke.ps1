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
$kubeconfig = New-TemporaryFile
@"
apiVersion: v1
kind: Config
clusters: []
contexts: []
users: []
"@ | Set-Content -LiteralPath $kubeconfig -Encoding utf8
.\scripts\zt.ps1 kubeconfig -Config $Config -Kubeconfig $kubeconfig
Remove-Item -LiteralPath $kubeconfig -Force
.\scripts\zt.ps1 verify -Config $Config
if (-not (Get-ChildItem -Path ".\.zt\environments" -Recurse -Filter "kubeconfig.json" -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw "Expected kubeconfig metadata was not written."
}
if (-not (Get-ChildItem -Path ".\.zt\environments" -Recurse -Filter "verification-evidence.json" -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw "Expected verification evidence was not written."
}
.\scripts\zt.ps1 runs -Config $Config
Write-Host "PowerShell smoke test completed."
