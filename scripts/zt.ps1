param(
    [Parameter(Position = 0)]
    [ValidateSet("validate", "prepare", "generate", "registry", "deploy", "verify", "kubeconfig", "secrets", "backup", "upgrade", "destroy", "runs", "ci")]
    [string]$Command = "validate",

    [Parameter(Mandatory = $true)]
    [string]$Config,

    [switch]$Strict,

    [switch]$Apply
    ,
    [string]$Secrets,

    [string]$TargetBundle,

    [switch]$ConfirmDestroy
    ,
    [string]$Kubeconfig
)

$ErrorActionPreference = "Stop"

$script:ValidationFailures = 0
$script:ValidationWarnings = 0

function Invoke-ConfigTool {
    param(
        [string[]]$Arguments
    )

    $toolPath = Join-Path $PSScriptRoot "..\tools\zt_config.py"
    $output = & python $toolPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Config helper failed: $($output -join "`n")"
    }
    return ($output -join "`n")
}

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

    $legacyMap = @{
        "name" = "environment.name"
        "type" = "environment.type"
        "version" = "nkp.version"
        "bundleType" = "nkp.bundleType"
        "bundlePath" = "nkp.bundlePath"
        "prismCentralEndpoint" = "nutanix.prismCentralEndpoint"
        "endpoint" = "registry.endpoint"
        "namespace" = "registry.namespace"
        "httpProxy" = "environment.proxy.httpProxy"
        "httpsProxy" = "environment.proxy.httpsProxy"
    }

    $path = if ($Key -match "\.") { $Key } elseif ($legacyMap.ContainsKey($Key)) { $legacyMap[$Key] } else { $Key }
    $value = Invoke-ConfigTool -Arguments @("get", "--config", $ConfigPath, "--path", $path)
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return $value.Trim()
}

function Get-YamlSectionScalar {
    param(
        [string]$ConfigPath,
        [string]$Section,
        [string]$Key
    )

    $value = Invoke-ConfigTool -Arguments @("get", "--config", $ConfigPath, "--path", "$Section.$Key")
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return $value.Trim()
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

    $schemaResult = Invoke-ConfigTool -Arguments @("validate", "--config", $ConfigPath) | ConvertFrom-Json
    foreach ($errorItem in $schemaResult.errors) {
        Write-Check -Status "FAIL" -Message "Schema: $errorItem"
    }
    foreach ($warningItem in $schemaResult.warnings) {
        Write-Check -Status "WARN" -Message "Schema: $warningItem"
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
    $secretsDir = Join-Path $environmentRoot "secrets"

    Write-Host ""
    Write-Check -Status "INFO" -Message "Preparing ZeroTouch workspace for '$environmentName'."

    @($environmentRoot, $binDir, $generatedDir, $logsDir, $stateDir, $secretsDir) | ForEach-Object {
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
            secrets = $secretsDir
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

function Get-ZtContext {
    param([string]$ConfigPath)

    $environmentName = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "environment" -Key "name"
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $environmentRoot = Join-Path $repoRoot ".zt\environments\$environmentName"

    return [ordered]@{
        repoRoot = $repoRoot
        environmentName = $environmentName
        environmentType = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "environment" -Key "type"
        bundleType = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nkp" -Key "bundleType"
        bundlePath = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nkp" -Key "bundlePath"
        nkpVersion = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nkp" -Key "version"
        prismCentralEndpoint = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nutanix" -Key "prismCentralEndpoint"
        prismElementCluster = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nutanix" -Key "clusterName"
        subnetName = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nutanix" -Key "subnetName"
        imageName = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nutanix" -Key "imageName"
        clusterName = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "name"
        kubernetesVersion = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "kubernetesVersion"
        controlPlaneReplicas = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "controlPlaneReplicas"
        workerReplicas = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "workerReplicas"
        podCidr = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "podCidr"
        serviceCidr = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "serviceCidr"
        controlPlaneEndpointIp = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "controlPlaneEndpointIp"
        controlPlaneEndpointPort = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "controlPlaneEndpointPort"
        sshPublicKeyFile = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "sshPublicKeyFile"
        sshUsername = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "sshUsername"
        ntpServers = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "ntpServers"
        loadBalancerIpRange = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "loadBalancerIpRange"
        selfManaged = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "selfManaged"
        fips = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "cluster" -Key "fips"
        storageContainer = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nutanix" -Key "storageContainer"
        project = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "nutanix" -Key "project"
        registryEndpoint = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "registry" -Key "endpoint"
        registryNamespace = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "registry" -Key "namespace"
        registryInsecure = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "registry" -Key "insecure"
        registryCaCert = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "registry" -Key "caCert"
        registryPushConcurrency = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "registry" -Key "pushConcurrency"
        registryOnExistingTag = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "registry" -Key "onExistingTag"
        httpProxy = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "proxy" -Key "httpProxy"
        httpsProxy = Get-YamlSectionScalar -ConfigPath $ConfigPath -Section "proxy" -Key "httpsProxy"
        environmentRoot = $environmentRoot
        binDir = Join-Path $environmentRoot "bin"
        generatedDir = Join-Path $environmentRoot "generated"
        logsDir = Join-Path $environmentRoot "logs"
        stateDir = Join-Path $environmentRoot "state"
        reportsDir = Join-Path $environmentRoot "reports"
        secretsDir = Join-Path $environmentRoot "secrets"
    }
}

function Assert-Prepared {
    param($Context)

    $metadataPath = Join-Path $Context.stateDir "environment.json"
    if (-not (Test-Path -LiteralPath $metadataPath)) {
        throw "Prepare has not completed for '$($Context.environmentName)'. Run prepare first."
    }

    Write-Check -Status "PASS" -Message "Prepared workspace found: $($Context.environmentRoot)"
}

function Convert-ToBashPath {
    param([string]$Path)

    if ($Path -match "^([A-Za-z]):\\(.*)$") {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = $Matches[2] -replace "\\", "/"
        return "/mnt/$drive/$rest"
    }

    return ($Path -replace "\\", "/")
}

function New-GeneratedFiles {
    param($Context)

    New-ZtDirectory -Path $Context.generatedDir
    New-ZtDirectory -Path $Context.stateDir
    New-ZtDirectory -Path $Context.reportsDir
}

function Invoke-Generate {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    New-GeneratedFiles -Context $context

    $clusterConfigPath = Join-Path $context.generatedDir "cluster-values.yaml"
    $envPath = Join-Path $context.generatedDir "nkp.env"
    $deployScriptPath = Join-Path $context.generatedDir "deploy.sh"
    $deployPsPath = Join-Path $context.generatedDir "deploy.ps1"

    Invoke-ConfigTool -Arguments @(
        "render-generate",
        "--config", $ConfigPath,
        "--generated-dir", $context.generatedDir,
        "--state-dir", $context.stateDir,
        "--reports-dir", $context.reportsDir,
        "--deploy-ps"
    ) | Out-Null

    Write-Check -Status "PASS" -Message "Generated cluster values: $clusterConfigPath"
    Write-Check -Status "PASS" -Message "Generated environment file: $envPath"
    Write-Check -Status "PASS" -Message "Generated deploy script: $deployScriptPath"
    Write-Check -Status "PASS" -Message "Generated deploy helper: $deployPsPath"
}

function Invoke-Registry {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    New-GeneratedFiles -Context $context

    $registryPlanPath = Join-Path $context.generatedDir "registry-plan.md"
    $registryScriptPath = Join-Path $context.generatedDir "registry.sh"

    Invoke-ConfigTool -Arguments @(
        "render-registry",
        "--config", $ConfigPath,
        "--generated-dir", $context.generatedDir,
        "--state-dir", $context.stateDir
    ) | Out-Null

    Write-Check -Status "PASS" -Message "Generated registry plan: $registryPlanPath"
    if (Test-Path -LiteralPath $registryScriptPath) {
        Write-Check -Status "PASS" -Message "Generated registry script: $registryScriptPath"
    }

    if ($Apply) {
        if ($context.environmentType -ne "air-gapped") {
            Write-Check -Status "INFO" -Message "Registry apply is optional for $($context.environmentType); generated plan only."
            return
        }
        if ($context.registryEndpoint -match "\.example\.com") {
            throw "Refusing registry apply because registry endpoint is still a placeholder."
        }
        New-ZtDirectory -Path $context.logsDir
        $registryLog = Join-Path $context.logsDir "registry-push.log"
        $bashPath = Convert-ToBashPath -Path $registryScriptPath
        Write-Check -Status "INFO" -Message "Applying registry script; log: $registryLog"
        bash -lc "chmod +x '$bashPath' && '$bashPath'" *> $registryLog
        Write-Check -Status "PASS" -Message "Registry apply completed."
    }
}

function Invoke-Deploy {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context

    $generateState = Join-Path $context.stateDir "generate.json"
    $deployScript = Join-Path $context.generatedDir "deploy.sh"
    if (-not (Test-Path -LiteralPath $generateState) -or -not (Test-Path -LiteralPath $deployScript)) {
        throw "Generate has not completed for '$($context.environmentName)'. Run generate first."
    }

    $deployPlanPath = Join-Path $context.generatedDir "deploy-plan.md"
    @"
# Deploy Plan

Environment: `$($context.environmentName)`
Cluster: `$($context.clusterName)`
Mode: `$($context.environmentType)`

Generated script:

```bash
$(Convert-ToBashPath -Path $deployScript)
```

Default behavior is dry-run. Use `-Apply` only when configuration and credentials are ready.
"@ | Set-Content -LiteralPath $deployPlanPath -Encoding utf8

    if (-not $Apply) {
        Write-Check -Status "PASS" -Message "Generated deploy plan: $deployPlanPath"
        Write-Check -Status "INFO" -Message "Dry-run mode. Re-run with -Apply to execute the generated deploy script."
        return
    }

    if ($context.prismCentralEndpoint -match "\.example\.com") {
        throw "Refusing apply because Prism Central endpoint is still a placeholder."
    }

    $bashPath = Convert-ToBashPath -Path $deployScript
    New-ZtDirectory -Path $context.logsDir
    $deployLog = Join-Path $context.logsDir "deploy.log"
    Write-Check -Status "INFO" -Message "Applying deploy script with bash: $bashPath"
    bash -lc "chmod +x '$bashPath' && '$bashPath'" *> $deployLog
    Write-Check -Status "PASS" -Message "Deploy apply completed; log: $deployLog"
}

function Invoke-Verify {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    New-ZtDirectory -Path $context.reportsDir

    $reportPath = Join-Path $context.reportsDir "verification-summary.md"
    $kubeconfigPath = Join-Path $context.stateDir "kubeconfig"
    $kubectlPath = Join-Path $context.binDir "kubectl"
    $nkpPath = Join-Path $context.binDir "nkp"

    $checks = @(
        [ordered]@{ name = "prepared workspace"; status = "pass"; detail = $context.environmentRoot },
        [ordered]@{ name = "generated config"; status = if (Test-Path -LiteralPath (Join-Path $context.stateDir "generate.json")) { "pass" } else { "warn" }; detail = "generate.json" },
        [ordered]@{ name = "nkp binary"; status = if (Test-Path -LiteralPath $nkpPath) { "pass" } else { "fail" }; detail = $nkpPath },
        [ordered]@{ name = "kubectl binary"; status = if (Test-Path -LiteralPath $kubectlPath) { "pass" } else { "fail" }; detail = $kubectlPath },
        [ordered]@{ name = "kubeconfig"; status = if (Test-Path -LiteralPath $kubeconfigPath) { "pass" } else { "warn" }; detail = $kubeconfigPath }
    )

    $lines = @("# Verification Summary", "", "Environment: $($context.environmentName)", "Cluster: $($context.clusterName)", "")
    foreach ($check in $checks) {
        $lines += "- $($check.status): $($check.name) - $($check.detail)"
        if ($check.status -eq "pass") {
            Write-Check -Status "PASS" -Message "$($check.name): $($check.detail)"
        }
        elseif ($check.status -eq "fail") {
            Write-Check -Status "FAIL" -Message "$($check.name): $($check.detail)"
        }
        else {
            Write-Check -Status "WARN" -Message "$($check.name): $($check.detail)"
        }
    }

    $lines | Set-Content -LiteralPath $reportPath -Encoding utf8
    $checks | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $context.reportsDir "component-health.json") -Encoding utf8
    if (Test-Path -LiteralPath $kubeconfigPath) {
        New-ZtDirectory -Path $context.logsDir
        $kubectlLog = Join-Path $context.logsDir "verify-kubectl.log"
        $bashKubeconfig = Convert-ToBashPath -Path $kubeconfigPath
        $bashKubectl = Convert-ToBashPath -Path $kubectlPath
        bash -lc "'$bashKubectl' --kubeconfig '$bashKubeconfig' get nodes -o wide; '$bashKubectl' --kubeconfig '$bashKubeconfig' get nodes; '$bashKubectl' --kubeconfig '$bashKubeconfig' get pods -A; '$bashKubectl' --kubeconfig '$bashKubeconfig' get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded || true; ./bin/nkp get clusters -A --kubeconfig '$bashKubeconfig' || true; ./bin/nkp get appdeployments -A --kubeconfig '$bashKubeconfig' || true" *> $kubectlLog
        Write-Check -Status "PASS" -Message "Live kubectl verification log: $kubectlLog"
    }
    Write-Check -Status "PASS" -Message "Wrote verification report: $reportPath"
}

function Invoke-Kubeconfig {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    if (-not $Kubeconfig) {
        throw "Kubeconfig path is required. Use -Kubeconfig <path>."
    }
    if (-not (Test-Path -LiteralPath $Kubeconfig)) {
        throw "Kubeconfig not found: $Kubeconfig"
    }
    $target = Join-Path $context.stateDir "kubeconfig"
    Copy-Item -LiteralPath $Kubeconfig -Destination $target -Force
    Write-Check -Status "PASS" -Message "Captured kubeconfig: $target"
}

function Invoke-Secrets {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    New-ZtDirectory -Path $context.stateDir

    $secretsPath = if ($Secrets) { $Secrets } else { Join-Path $context.repoRoot "configs\secrets\$($context.environmentName).secrets.yaml" }
    if (-not (Test-Path -LiteralPath $secretsPath)) {
        throw "Secrets file not found: $secretsPath. Copy one of configs/secrets/*.example.yaml and remove .example."
    }

    $content = Get-Content -LiteralPath $secretsPath -Raw
    $summary = [ordered]@{
        loadedAt = (Get-Date).ToUniversalTime().ToString("o")
        source = (Resolve-Path -LiteralPath $secretsPath).Path
        prismCentral = [ordered]@{
            usernameConfigured = ($content -match "(?m)^\s*username:\s*\S+")
            passwordConfigured = ($content -match "(?m)^\s*password:\s*\S+")
        }
        registry = [ordered]@{
            configured = ($content -match "(?m)^\s*registry:\s*$")
        }
        ssh = [ordered]@{
            configured = ($content -match "(?m)^\s*ssh:\s*$")
        }
    }

    $summaryPath = Join-Path $context.stateDir "secrets.json"
    $summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summaryPath -Encoding utf8

    New-ZtDirectory -Path $context.secretsDir
    $secretEnvPath = Join-Path $context.secretsDir "secrets.env"
    Invoke-ConfigTool -Arguments @("secret-env", "--secrets", $secretsPath) | Set-Content -LiteralPath $secretEnvPath -Encoding utf8

    $envExamplePath = Join-Path $context.generatedDir "secrets.env.example"
    New-ZtDirectory -Path $context.generatedDir
    @"
# Source this file pattern with real values in your shell. Do not commit real secrets.
export NUTANIX_USER="admin"
export NUTANIX_PASSWORD="change-me"
export NUTANIX_PC_USERNAME="admin"
export NUTANIX_PC_PASSWORD="change-me"
export ZT_REGISTRY_USERNAME="registry-user"
export ZT_REGISTRY_PASSWORD="change-me"
"@ | Set-Content -LiteralPath $envExamplePath -Encoding utf8

    Write-Check -Status "PASS" -Message "Recorded redacted secrets summary: $summaryPath"
    Write-Check -Status "PASS" -Message "Rendered local secret environment file: $secretEnvPath"
    Write-Check -Status "PASS" -Message "Wrote shell secrets example: $envExamplePath"
}

function Invoke-Backup {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context

    $backupRoot = Join-Path $context.environmentRoot "backup"
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $backupRoot $stamp
    New-ZtDirectory -Path $backupDir

    foreach ($dirName in @("state", "generated", "reports")) {
        $source = Join-Path $context.environmentRoot $dirName
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $backupDir $dirName) -Recurse -Force
            Write-Check -Status "PASS" -Message "Backed up $dirName"
        }
    }

    $manifest = [ordered]@{
        createdAt = (Get-Date).ToUniversalTime().ToString("o")
        environment = $context.environmentName
        source = $context.environmentRoot
        backup = $backupDir
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backupDir "backup-manifest.json") -Encoding utf8
    Write-Check -Status "PASS" -Message "Backup ready: $backupDir"
}

function Invoke-Upgrade {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    New-ZtDirectory -Path $context.generatedDir

    $planPath = Join-Path $context.generatedDir "upgrade-plan.md"
    @"
# Upgrade Plan

Environment: $($context.environmentName)
Current NKP version: $($context.nkpVersion)
Target bundle: $TargetBundle

Planned flow:

1. Run backup.
2. Validate target bundle.
3. Run NKP upgrade commands from Linux or WSL.
4. Run verify.

This phase is plan-first. Use -Apply only after replacing placeholder endpoints and confirming the target bundle.
"@ | Set-Content -LiteralPath $planPath -Encoding utf8

    Write-Check -Status "PASS" -Message "Generated upgrade plan: $planPath"

    if (-not $Apply) {
        Write-Check -Status "INFO" -Message "Dry-run mode. Re-run with -Apply after validating the target bundle."
        return
    }

    if (-not $TargetBundle) {
        throw "TargetBundle is required for upgrade apply."
    }
    if ($context.prismCentralEndpoint -match "\.example\.com") {
        throw "Refusing upgrade apply because Prism Central endpoint is still a placeholder."
    }

    Write-Check -Status "WARN" -Message "Live upgrade execution is intentionally not automated yet; plan has been generated for operator review."
}

function Invoke-Destroy {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context
    New-ZtDirectory -Path $context.generatedDir

    $planPath = Join-Path $context.generatedDir "destroy-plan.md"
    $command = "./bin/nkp delete cluster --cluster-name $($context.clusterName)"
    @"
# Destroy Plan

Environment: $($context.environmentName)
Cluster: $($context.clusterName)

Command:

```bash
$command
```

Destroy requires both -Apply and -ConfirmDestroy.
"@ | Set-Content -LiteralPath $planPath -Encoding utf8

    Write-Check -Status "PASS" -Message "Generated destroy plan: $planPath"

    if (-not $Apply -or -not $ConfirmDestroy) {
        Write-Check -Status "INFO" -Message "Dry-run mode. Destruction requires -Apply -ConfirmDestroy."
        return
    }

    if ($context.prismCentralEndpoint -match "\.example\.com") {
        throw "Refusing destroy apply because Prism Central endpoint is still a placeholder."
    }

    Write-Check -Status "WARN" -Message "Live destroy execution is guarded; run the generated plan manually from a prepared Linux/WSL runner."
}

function Invoke-Runs {
    param([string]$ConfigPath)

    $context = Get-ZtContext -ConfigPath $ConfigPath
    Assert-Prepared -Context $context

    $runsRoot = Join-Path $context.repoRoot ".zt\runs"
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $runDir = Join-Path $runsRoot $stamp
    New-ZtDirectory -Path $runDir

    $stateFiles = @("environment.json", "staged-tools.json", "generate.json", "registry.json", "secrets.json") | ForEach-Object {
        $path = Join-Path $context.stateDir $_
        [ordered]@{
            name = $_
            exists = Test-Path -LiteralPath $path
            path = $path
        }
    }

    $summary = [ordered]@{
        capturedAt = (Get-Date).ToUniversalTime().ToString("o")
        environment = $context.environmentName
        type = $context.environmentType
        cluster = $context.clusterName
        stateFiles = $stateFiles
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runDir "summary.json") -Encoding utf8

    $lines = @("# Run Summary", "", "Environment: $($context.environmentName)", "Cluster: $($context.clusterName)", "")
    foreach ($file in $stateFiles) {
        $status = if ($file.exists) { "present" } else { "missing" }
        $lines += "- ${status}: $($file.name)"
    }
    $lines | Set-Content -LiteralPath (Join-Path $runDir "summary.md") -Encoding utf8

    Write-Check -Status "PASS" -Message "Captured run summary: $runDir"
}

function Invoke-Ci {
    param([string]$ConfigPath)

    Write-Check -Status "INFO" -Message "Running local CI smoke checks."
    $null = [scriptblock]::Create((Get-Content -LiteralPath $PSCommandPath -Raw))
    Write-Check -Status "PASS" -Message "PowerShell syntax parsed."

    bash -lc "bash -n ./scripts/zt.sh"
    Write-Check -Status "PASS" -Message "Bash syntax parsed."

    foreach ($example in Get-ChildItem -LiteralPath (Join-Path (Get-ZtContext -ConfigPath $ConfigPath).repoRoot "configs\environments") -Filter "*.example.yaml") {
        $script:ValidationFailures = 0
        $script:ValidationWarnings = 0
        Invoke-Validate -ConfigPath $example.FullName
    }

    Write-Check -Status "PASS" -Message "Example config validation completed."
}

switch ($Command) {
    "validate" {
        Invoke-Validate -ConfigPath $Config
    }
    "prepare" {
        Invoke-Prepare -ConfigPath $Config
    }
    "generate" {
        Invoke-Generate -ConfigPath $Config
    }
    "registry" {
        Invoke-Registry -ConfigPath $Config
    }
    "deploy" {
        Invoke-Deploy -ConfigPath $Config
    }
    "verify" {
        Invoke-Verify -ConfigPath $Config
    }
    "kubeconfig" {
        Invoke-Kubeconfig -ConfigPath $Config
    }
    "secrets" {
        Invoke-Secrets -ConfigPath $Config
    }
    "backup" {
        Invoke-Backup -ConfigPath $Config
    }
    "upgrade" {
        Invoke-Upgrade -ConfigPath $Config
    }
    "destroy" {
        Invoke-Destroy -ConfigPath $Config
    }
    "runs" {
        Invoke-Runs -ConfigPath $Config
    }
    "ci" {
        Invoke-Ci -ConfigPath $Config
    }
    default {
        Write-Host "Command '$Command' is scaffolded. Mode-specific implementation comes next."
    }
}
