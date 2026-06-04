param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [ValidateSet("connected", "proxied", "air-gapped")]
    [string]$Type = "connected"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$sourceConfig = Join-Path $repoRoot "configs\environments\$Type.example.yaml"
$targetConfig = Join-Path $repoRoot "configs\environments\$Name.yaml"
$sourceSecrets = Join-Path $repoRoot "configs\secrets\lab-$($Type -replace '-', '').secrets.example.yaml"
$targetSecrets = Join-Path $repoRoot "configs\secrets\$Name.secrets.yaml"

if (Test-Path -LiteralPath $targetConfig) {
    throw "Environment config already exists: $targetConfig"
}

Copy-Item -LiteralPath $sourceConfig -Destination $targetConfig

if (Test-Path -LiteralPath $sourceSecrets) {
    Copy-Item -LiteralPath $sourceSecrets -Destination $targetSecrets
}

Write-Host "Created environment config: $targetConfig"
Write-Host "Created local secrets file: $targetSecrets"
Write-Host "Edit both files before running validate/apply phases."
