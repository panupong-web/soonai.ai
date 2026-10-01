[CmdletBinding()]
param(
    [ValidateRange(1, 3)]
    [int]$MaxDevices = 3,
    [string]$ExpiresAt = ""
)

$ErrorActionPreference = "Stop"
$serviceUrl = $env:SOONAI_LICENSE_API_URL
if ([string]::IsNullOrWhiteSpace($serviceUrl)) {
    $serviceUrl = "https://soonai-license.soonai-2026.workers.dev"
}
$serviceUrl = $serviceUrl.TrimEnd('/')
if (-not $serviceUrl.StartsWith("https://", [StringComparison]::OrdinalIgnoreCase)) {
    throw "License service URL must use HTTPS. Set SOONAI_LICENSE_API_URL to the deployed Worker URL."
}

$secureToken = Read-Host "Admin API token (hidden input)" -AsSecureString
$adminToken = [Net.NetworkCredential]::new("", $secureToken).Password
if ([string]::IsNullOrWhiteSpace($adminToken)) {
    throw "Admin API token is required."
}

$headers = @{ Authorization = "Bearer $adminToken" }
$body = @{ max_devices = $MaxDevices }
if ($ExpiresAt) {
    $body.expires_at = $ExpiresAt
}

try {
    $result = Invoke-RestMethod -Method Post `
        -Uri "$serviceUrl/admin/licenses" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body ($body | ConvertTo-Json -Compress)

    if (-not $result.license_key) {
        throw "License service response did not contain a license key."
    }

    Write-Host "License created for $($result.max_devices) devices." -ForegroundColor Green
    Write-Host "Copy this key into the user's terminal; it is shown only once:" -ForegroundColor Yellow
    Write-Host $result.license_key
} catch {
    Write-Error "License issuance failed: $($_.Exception.Message)"
    exit 1
} finally {
    $adminToken = $null
    $secureToken = $null
    $headers = $null
}
