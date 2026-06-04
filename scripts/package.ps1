param(
    [string]$Version = "dev"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$dist = Join-Path $repoRoot "dist"
$staging = Join-Path $dist "nkp-zerotouch-framework-$Version"
$archive = Join-Path $dist "nkp-zerotouch-framework-$Version.zip"

if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Path $staging | Out-Null

foreach ($item in @("configs", "docs", "scripts", "templates", "tests", "tools", "README.md", "LICENSE", ".gitignore")) {
    Copy-Item -LiteralPath (Join-Path $repoRoot $item) -Destination $staging -Recurse -Force
}

if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $archive
Write-Host "Package created: $archive"
