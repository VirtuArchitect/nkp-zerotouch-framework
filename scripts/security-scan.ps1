$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$patterns = @(
    "BEGIN .*PRIVATE KEY",
    "password:\s*(?!change-?me|changeme)\S+",
    "token:\s*\S+",
    "secret:\s*\S+",
    "client-key-data:"
)

$excludedFiles = @(
    ".md",
    ".gitignore",
    ".ps1",
    ".sh",
    ".py"
)
$excludedNames = @(
    "security-scan.ps1",
    "security-scan.sh"
)
$findings = @()

$trackedFiles = git -C $repoRoot.Path ls-files
foreach ($relativePath in $trackedFiles) {
    $path = Join-Path $repoRoot.Path $relativePath
    $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
    if (-not $item) {
        continue
    }
    if ($excludedFiles -contains $item.Extension) {
        continue
    }
    if ($excludedNames -contains $item.Name) {
        continue
    }

    $matches = Select-String -LiteralPath $path -Pattern $patterns -CaseSensitive:$false -ErrorAction SilentlyContinue
    foreach ($match in $matches) {
        if ($match.Line -match "github\.token") {
            continue
        }
        if ($match.Line -match "ZT_BOOTSTRAP_TOKEN:\s*\$\{ZT_BOOTSTRAP_TOKEN:") {
            continue
        }
        $findings += [ordered]@{
            file = $relativePath
            line = $match.LineNumber
            text = $match.Line.Trim()
        }
    }
}

if ($findings.Count -gt 0) {
    $findings | ConvertTo-Json -Depth 4
    throw "Security scan found possible sensitive content."
}

Write-Host "Security scan passed."
