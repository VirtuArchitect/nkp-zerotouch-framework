$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$patterns = @(
    "BEGIN .*PRIVATE KEY",
    "password:\s*(?!change-?me|changeme)\S+",
    "token:\s*\S+",
    "secret:\s*\S+",
    "client-key-data:",
    "kubeconfig"
)

$excluded = @("\\.zt\\", "\\dist\\", "\\.git\\")
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

Get-ChildItem -LiteralPath $repoRoot -Recurse -File -Force | ForEach-Object {
    $path = $_.FullName
    foreach ($exclude in $excluded) {
        if ($path -match $exclude) {
            return
        }
    }
    if ($excludedFiles -contains $_.Extension) {
        return
    }
    if ($excludedNames -contains $_.Name) {
        return
    }

    $matches = Select-String -LiteralPath $path -Pattern $patterns -CaseSensitive:$false -ErrorAction SilentlyContinue
    foreach ($match in $matches) {
        if ($match.Line -match "github\.token") {
            continue
        }
        $findings += [ordered]@{
            file = $path.Substring($repoRoot.Path.Length + 1)
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
