# Run with CC5 closed. Installation under Program Files may require elevation.
[CmdletBinding(SupportsShouldProcess)]
param([string]$CC5Root = "C:\Program Files\Reallusion\Character Creator 5")
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'cc5-plugin'
$destination = Join-Path $CC5Root 'Bin64\OpenPlugin\CC5_MCP_Bridge'
if (Get-Process -Name CharacterCreator -ErrorAction SilentlyContinue) {
    throw 'Close CC5 before installing the bridge.'
}
if (!(Test-Path -LiteralPath (Join-Path $CC5Root 'Bin64\CharacterCreator.exe'))) {
    throw 'CC5 executable not found. Supply -CC5Root for your installation.'
}
if ($PSCmdlet.ShouldProcess($destination, 'Copy MCP plugin modules and configuration')) {
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Get-ChildItem -LiteralPath $source -File | Where-Object {
        $_.Extension -in '.py', '.json', '.xml'
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $destination -Force }
    Write-Output "Installed to $destination. Set CC5_BRIDGE_TOKEN before launching CC5."
}
