param(
    [Parameter(Position = 0)]
    [ValidateSet("validate", "prepare", "deploy", "verify")]
    [string]$Command = "validate",

    [Parameter(Mandatory = $true)]
    [string]$Config,

    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$script:ValidationFailures = 0
$script:ValidationWarnings = 0

function Write-Check {
    param(
        [ValidateSet("PASS", "WARN", "FAIL", "INFO")]
        [string]$Status,
        [string]$Message
    )

    switch ($Status) {
        "PASS" { Write-Host "[PASS] $Message" -ForegroundColor Green }
        "WARN" {
            $script:ValidationWarnings++
            Write-Host "[WARN] $Message" -ForegroundColor Yellow
        }
        "FAIL" {
            $script:ValidationFailures++
            Write-Host "[FAIL] $Message" -ForegroundColor Red
        }
        "INFO" { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
    }
}

function Get-YamlScalar {
    param(
        [string]$ConfigPath,
        [string]$Key
    )

    $match = Select-String -LiteralPath $ConfigPath -Pattern "^\s*$([regex]::Escape($Key)):\s*(.+?)\s*$" | Select-Object -First 1
    if (-not $match) {
        return $null
    }

    return $match.Matches[0].Groups[1].Value.Trim(" '""")
}

function Convert-WslPathToWindowsPath {
    param([string]$Path)

    if (-not $Path) {
        return $Path
    }

    if ($Path -match "^/mnt/([a-zA-Z])/(.*)$") {
        $drive = $Matches[1].ToUpperInvariant()
        $rest = $Matches[2] -replace "/", "\"
        return "${drive}:\$rest"
    }

    return $Path
}

function Join-BundlePath {
    param(
        [string]$BundlePath,
        [string]$RelativePath
    )

    $localBundlePath = Convert-WslPathToWindowsPath -Path $BundlePath
    return Join-Path -Path $localBundlePath -ChildPath $RelativePath
}

function Test-AllowedValue {
    param(
        [string]$Name,
        [string]$Value,
        [string[]]$Allowed
    )

    if (-not $Value) {
        Write-Check -Status "FAIL" -Message "$Name is required."
        return
    }

    if ($Allowed -notcontains $Value) {
        Write-Check -Status "FAIL" -Message "$Name '$Value' is unsupported. Expected one of: $($Allowed -join ', ')."
        return
    }

    Write-Check -Status "PASS" -Message "$Name is '$Value'."
}

function Test-RequiredScalar {
    param(
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Check -Status "FAIL" -Message "$Name is required."
    }
    else {
        Write-Check -Status "PASS" -Message "$Name is set."
    }
}

function Test-PathExists {
    param(
        [string]$DisplayPath,
        [string]$LocalPath,
        [string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($DisplayPath)) {
        Write-Check -Status "FAIL" -Message "$Description path is required."
        return $false
    }

    if (Test-Path -LiteralPath $LocalPath) {
        Write-Check -Status "PASS" -Message "$Description found: $DisplayPath"
        return $true
    }

    Write-Check -Status "FAIL" -Message "$Description not found: $DisplayPath"
    return $false
}

function Test-CommandAvailable {
    param(
        [string]$CommandName,
        [switch]$Required
    )

    $commandInfo = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($commandInfo) {
        Write-Check -Status "PASS" -Message "Tool available: $CommandName"
        return
    }

    if ($Required) {
        Write-Check -Status "FAIL" -Message "Required tool missing from PATH: $CommandName"
    }
    else {
        Write-Check -Status "WARN" -Message "Optional tool missing from PATH: $CommandName"
    }
}

function Test-TcpEndpoint {
    param(
        [string]$Endpoint,
        [string]$Name,
        [int]$DefaultPort
    )

    if ([string]::IsNullOrWhiteSpace($Endpoint)) {
        Write-Check -Status "WARN" -Message "$Name endpoint is not configured."
        return
    }

    try {
        $uri = if ($Endpoint -match "^\w+://") { [uri]$Endpoint } else { [uri]"tcp://$Endpoint" }
        $hostName = $uri.Host
        $port = if ($uri.Port -gt 0) { $uri.Port } else { $DefaultPort }

        if ($hostName -match "\.example\.com$") {
            Write-Check -Status "WARN" -Message "$Name uses placeholder endpoint: $Endpoint"
            return
        }

        $result = Test-NetConnection -ComputerName $hostName -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($result) {
            Write-Check -Status "PASS" -Message "$Name reachable at ${hostName}:${port}"
        }
        else {
            Write-Check -Status "WARN" -Message "$Name not reachable at ${hostName}:${port}"
        }
    }
    catch {
        Write-Check -Status "WARN" -Message "Could not parse or test $Name endpoint '$Endpoint': $($_.Exception.Message)"
    }
}

function Test-NkpBundle {
    param(
        [string]$BundlePath,
        [string]$BundleType,
        [string]$Version
    )

    $localBundlePath = Convert-WslPathToWindowsPath -Path $BundlePath
    $bundleExists = Test-PathExists -DisplayPath $BundlePath -LocalPath $localBundlePath -Description "NKP bundle"
    if (-not $bundleExists) {
        return
    }

    $requiredFiles = @(
        @{ Path = "cli\nkp"; Name = "nkp CLI" },
        @{ Path = "kubectl"; Name = "kubectl" },
        @{ Path = "konvoy-bootstrap-image-$Version.tar"; Name = "Konvoy bootstrap image" },
        @{ Path = "nkp-image-builder-image-$Version.tar"; Name = "NKP image builder image" },
        @{ Path = "application-repositories\kommander-applications-$Version.tar.gz"; Name = "Kommander application repository" },
        @{ Path = "container-images\konvoy-image-bundle-$Version.tar"; Name = "Konvoy image bundle" },
        @{ Path = "container-images\kommander-image-bundle-$Version.tar"; Name = "Kommander image bundle" }
    )

    foreach ($file in $requiredFiles) {
        $displayPath = "$BundlePath/$($file.Path -replace '\\', '/')"
        $localPath = Join-BundlePath -BundlePath $BundlePath -RelativePath $file.Path
        Test-PathExists -DisplayPath $displayPath -LocalPath $localPath -Description $file.Name | Out-Null
    }

    $imageArtifactDir = Join-BundlePath -BundlePath $BundlePath -RelativePath "image-artifacts"
    if (Test-Path -LiteralPath $imageArtifactDir) {
        $artifactCount = (Get-ChildItem -LiteralPath $imageArtifactDir -File -Recurse | Measure-Object).Count
        Write-Check -Status "PASS" -Message "Image artifact files discovered: $artifactCount"
    }
    else {
        Write-Check -Status "FAIL" -Message "Image artifacts directory missing: $BundlePath/image-artifacts"
    }

    if ($BundleType -eq "air-gapped") {
        Write-Check -Status "PASS" -Message "Air-gapped bundle workflow selected."
    }
    elseif ($BundleType -eq "standard") {
        Write-Check -Status "PASS" -Message "Standard bundle workflow selected."
    }
}

function Invoke-Validate {
    param([string]$ConfigPath)

    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Config file not found: $ConfigPath"
    }

    $environmentName = Get-YamlScalar -ConfigPath $ConfigPath -Key "name"
    $environmentType = Get-YamlScalar -ConfigPath $ConfigPath -Key "type"
    $bundleType = Get-YamlScalar -ConfigPath $ConfigPath -Key "bundleType"
    $bundlePath = Get-YamlScalar -ConfigPath $ConfigPath -Key "bundlePath"
    $nkpVersion = Get-YamlScalar -ConfigPath $ConfigPath -Key "version"
    $prismCentralEndpoint = Get-YamlScalar -ConfigPath $ConfigPath -Key "prismCentralEndpoint"
    $registryEndpoint = Get-YamlScalar -ConfigPath $ConfigPath -Key "endpoint"
    $registryNamespace = Get-YamlScalar -ConfigPath $ConfigPath -Key "namespace"
    $httpProxy = Get-YamlScalar -ConfigPath $ConfigPath -Key "httpProxy"
    $httpsProxy = Get-YamlScalar -ConfigPath $ConfigPath -Key "httpsProxy"

    Write-Check -Status "INFO" -Message "ZeroTouch command: validate"
    Write-Check -Status "INFO" -Message "Config: $ConfigPath"

    Test-RequiredScalar -Name "environment.name" -Value $environmentName
    Test-AllowedValue -Name "environment.type" -Value $environmentType -Allowed @("connected", "proxied", "air-gapped")
    Test-RequiredScalar -Name "nkp.version" -Value $nkpVersion

    if ($bundleType) {
        Test-AllowedValue -Name "nkp.bundleType" -Value $bundleType -Allowed @("standard", "air-gapped")
    }
    else {
        Write-Check -Status "WARN" -Message "nkp.bundleType is not set; bundle discovery will be skipped."
    }

    if ($environmentType -eq "air-gapped" -and $bundleType -ne "air-gapped") {
        Write-Check -Status "FAIL" -Message "Air-gapped environments must use nkp.bundleType: air-gapped."
    }
    elseif (($environmentType -eq "connected" -or $environmentType -eq "proxied") -and $bundleType -eq "air-gapped") {
        Write-Check -Status "WARN" -Message "$environmentType environment is using an air-gapped bundle."
    }

    if ($bundlePath) {
        Test-NkpBundle -BundlePath $bundlePath -BundleType $bundleType -Version $nkpVersion
    }
    elseif ($environmentType -eq "air-gapped") {
        Write-Check -Status "FAIL" -Message "nkp.bundlePath is required for air-gapped environments."
    }
    else {
        Write-Check -Status "WARN" -Message "nkp.bundlePath is not set; online tooling must provide NKP binaries."
    }

    Test-TcpEndpoint -Endpoint $prismCentralEndpoint -Name "Prism Central" -DefaultPort 9440

    if ($environmentType -eq "air-gapped") {
        Test-RequiredScalar -Name "registry.endpoint" -Value $registryEndpoint
        Test-RequiredScalar -Name "registry.namespace" -Value $registryNamespace
        Test-TcpEndpoint -Endpoint $registryEndpoint -Name "Registry" -DefaultPort 443
    }

    if ($environmentType -eq "proxied") {
        Test-RequiredScalar -Name "environment.proxy.httpProxy" -Value $httpProxy
        Test-RequiredScalar -Name "environment.proxy.httpsProxy" -Value $httpsProxy
    }

    Test-CommandAvailable -CommandName "ssh" -Required
    Test-CommandAvailable -CommandName "docker"
    Test-CommandAvailable -CommandName "podman"
    Test-CommandAvailable -CommandName "openssl"

    if ($Strict -and $script:ValidationWarnings -gt 0) {
        Write-Check -Status "FAIL" -Message "Strict mode treats warnings as failures."
    }

    Write-Host ""
    Write-Host "Validation summary: $script:ValidationFailures failure(s), $script:ValidationWarnings warning(s)."

    if ($script:ValidationFailures -gt 0) {
        exit 1
    }
}

function New-ZtDirectory {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Copy-ZtTool {
    param(
        [string]$SourcePath,
        [string]$DestinationPath,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "$Name source was not found: $SourcePath"
    }

    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
    Write-Check -Status "PASS" -Message "Staged $Name to $DestinationPath"
}

function Invoke-Prepare {
    param([string]$ConfigPath)

    $script:ValidationFailures = 0
    $script:ValidationWarnings = 0
    Invoke-Validate -ConfigPath $ConfigPath

    $environmentName = Get-YamlScalar -ConfigPath $ConfigPath -Key "name"
    $environmentType = Get-YamlScalar -ConfigPath $ConfigPath -Key "type"
    $bundleType = Get-YamlScalar -ConfigPath $ConfigPath -Key "bundleType"
    $bundlePath = Get-YamlScalar -ConfigPath $ConfigPath -Key "bundlePath"
    $nkpVersion = Get-YamlScalar -ConfigPath $ConfigPath -Key "version"
    $prismCentralEndpoint = Get-YamlScalar -ConfigPath $ConfigPath -Key "prismCentralEndpoint"
    $registryEndpoint = Get-YamlScalar -ConfigPath $ConfigPath -Key "endpoint"
    $registryNamespace = Get-YamlScalar -ConfigPath $ConfigPath -Key "namespace"
    $configFullPath = (Resolve-Path -LiteralPath $ConfigPath).Path

    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $environmentRoot = Join-Path $repoRoot ".zt\environments\$environmentName"
    $binDir = Join-Path $environmentRoot "bin"
    $generatedDir = Join-Path $environmentRoot "generated"
    $logsDir = Join-Path $environmentRoot "logs"
    $stateDir = Join-Path $environmentRoot "state"

    Write-Host ""
    Write-Check -Status "INFO" -Message "Preparing ZeroTouch workspace for '$environmentName'."

    @($environmentRoot, $binDir, $generatedDir, $logsDir, $stateDir) | ForEach-Object {
        New-ZtDirectory -Path $_
        Write-Check -Status "PASS" -Message "Directory ready: $_"
    }

    if ($bundlePath) {
        $nkpSource = Join-BundlePath -BundlePath $bundlePath -RelativePath "cli\nkp"
        $kubectlSource = Join-BundlePath -BundlePath $bundlePath -RelativePath "kubectl"
        Copy-ZtTool -SourcePath $nkpSource -DestinationPath (Join-Path $binDir "nkp") -Name "nkp CLI"
        Copy-ZtTool -SourcePath $kubectlSource -DestinationPath (Join-Path $binDir "kubectl") -Name "kubectl"
    }
    else {
        Write-Check -Status "WARN" -Message "No bundlePath was configured; skipping local tool staging."
    }

    $metadata = [ordered]@{
        preparedAt = (Get-Date).ToUniversalTime().ToString("o")
        environment = [ordered]@{
            name = $environmentName
            type = $environmentType
        }
        nkp = [ordered]@{
            version = $nkpVersion
            bundleType = $bundleType
            bundlePath = $bundlePath
        }
        nutanix = [ordered]@{
            prismCentralEndpoint = $prismCentralEndpoint
        }
        registry = [ordered]@{
            endpoint = $registryEndpoint
            namespace = $registryNamespace
        }
        paths = [ordered]@{
            config = $configFullPath
            environmentRoot = $environmentRoot
            bin = $binDir
            generated = $generatedDir
            logs = $logsDir
            state = $stateDir
        }
    }

    $metadataPath = Join-Path $stateDir "environment.json"
    $metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $metadataPath -Encoding utf8
    Write-Check -Status "PASS" -Message "Wrote environment metadata: $metadataPath"

    $manifestPath = Join-Path $stateDir "staged-tools.json"
    $tools = @()
    foreach ($toolName in @("nkp", "kubectl")) {
        $toolPath = Join-Path $binDir $toolName
        if (Test-Path -LiteralPath $toolPath) {
            $item = Get-Item -LiteralPath $toolPath
            $tools += [ordered]@{
                name = $toolName
                path = $item.FullName
                sizeBytes = $item.Length
                lastWriteTimeUtc = $item.LastWriteTimeUtc.ToString("o")
            }
        }
    }
    $tools | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    Write-Check -Status "PASS" -Message "Wrote staged tool manifest: $manifestPath"

    Write-Host ""
    Write-Host "Prepare summary: workspace ready at $environmentRoot"
}

switch ($Command) {
    "validate" {
        Invoke-Validate -ConfigPath $Config
    }
    "prepare" {
        Invoke-Prepare -ConfigPath $Config
    }
    default {
        Write-Host "Command '$Command' is scaffolded. Mode-specific implementation comes next."
    }
}
